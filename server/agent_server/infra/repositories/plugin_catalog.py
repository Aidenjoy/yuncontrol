"""Catalog persistence: serialize writers and audit publication changes atomically."""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger
from sqlalchemy import Text, bindparam, cast, func, insert, or_, select, true, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_server.core.plugin_catalog import (
    PluginCatalogSummary,
    PluginList,
    PluginSyncEntry,
    PluginSyncState,
    PluginView,
    PluginWrite,
)
from agent_server.infra.db.schema import instance_settings
from agent_server.infra.db.schema import plugin_catalog_flow as flow
from agent_server.infra.db.schema import plugin_catalog_info as info


class PluginCatalogRepository:
    """Read live publication state on every query; no cached draft or published index."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Use the existing async engine; all catalog writes share a database lock."""
        self._engine = engine

    async def list(
        self,
        q: str = "",
        category: str | list[str] = "",
        limit: int = 50,
        offset: int = 0,
        public: bool = False,
        status: str | None = None,
        source: str = "",
    ) -> PluginList:
        """Filter publication before counting/paging; category and search are literal input."""
        conditions = [info.c.deleted == 0]
        if public:
            conditions.append(info.c.status == "published")
        if not public and status:
            conditions.append(info.c.status == status)
        if not public and source:
            origins = func.coalesce(info.c.item["_origins"], cast({}, JSONB))
            conditions.append(
                origins == cast({}, JSONB)
                if source == "manual"
                else origins.op("?")(source)
            )
        if q:
            needle = (
                "%"
                + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            conditions.append(
                or_(
                    info.c.plugin_key.ilike(needle, escape="\\"),
                    info.c.item["name"].astext.ilike(needle, escape="\\"),
                    info.c.item["package"]["name"].astext.ilike(needle, escape="\\"),
                    cast(info.c.item["keywords"], Text).ilike(needle, escape="\\"),
                    info.c.item["displayName"].astext.ilike(needle, escape="\\"),
                    info.c.item["summary"].astext.ilike(needle, escape="\\"),
                )
            )
        for selected in (
            [category] if isinstance(category, str) and category else category or []
        ):
            conditions.append(info.c.item["categories"].contains([selected]))
        async with self._engine.connect() as conn:
            await conn.execution_options(isolation_level="REPEATABLE READ")
            async with conn.begin():
                revision = await conn.scalar(
                    select(instance_settings.c.value).where(
                        instance_settings.c.key == "plugin-catalog-clock"
                    )
                )
                rows = (
                    (
                        await conn.execute(
                            select(info)
                            .where(*conditions)
                            .order_by(info.c.id)
                            .limit(limit)
                            .offset(offset)
                        )
                    )
                    .mappings()
                    .all()
                )
                total = await conn.scalar(
                    select(func.count()).select_from(info).where(*conditions)
                )
        return PluginList(
            items=[
                PluginView(
                    id=str(r["id"]),
                    item={k: v for k, v in r["item"].items() if k != "_origins"},
                    status=r["status"],
                    origins=r["item"].get("_origins", {}),
                )
                for r in rows
            ],
            total=total,
            revision=revision or "0",
        )

    async def mutate(
        self,
        actor: str,
        items: list[PluginWrite] | None = None,
        identifier: int | None = None,
        status: str | None = None,
        delete: bool = False,
        identifiers: list[int] | None = None,
    ) -> list[PluginView]:
        """Serialize upserts, allocate Snowflake IDs, and write history in the same transaction."""
        now = datetime.now(UTC)
        result = []
        async with self._engine.begin() as conn:
            # 步骤1：数据库行锁统一分配时间戳+序列ID，跨进程导入也不会重复创建。
            await conn.execute(
                pg_insert(instance_settings)
                .values(
                    key="plugin-catalog-clock", value="0", updated_at=now.isoformat()
                )
                .on_conflict_do_nothing()
            )
            last = int(
                await conn.scalar(
                    select(instance_settings.c.value)
                    .where(instance_settings.c.key == "plugin-catalog-clock")
                    .with_for_update()
                )
            )

            def next_id():
                """Allocate a monotonic timestamp/sequence ID, tolerating clock rollback."""
                nonlocal last
                timestamp = max(int(time.time() * 1000) - 1704067200000, last >> 22)
                sequence = (last & 4095) + 1 if timestamp == last >> 22 else 0
                if sequence > 4095:
                    timestamp += 1
                    sequence = 0
                # Database serialization permits a fixed worker ID (zero).
                last = (timestamp << 22) | sequence
                return last

            bulk_rows = {}
            if identifiers:
                bulk_rows = {
                    r["id"]: r
                    for r in (
                        await conn.execute(
                            select(info).where(
                                info.c.id.in_(identifiers), info.c.deleted == 0
                            )
                        )
                    )
                    .mappings()
                    .all()
                }
                if len(bulk_rows) != len(identifiers):
                    raise KeyError("plugin not found")
            entries = (
                items
                if items is not None
                else [None] * (len(identifiers) if identifiers else 1)
            )
            for index, entry in enumerate(entries):
                if identifiers:
                    identifier = identifiers[index]
                condition = (
                    info.c.id == identifier
                    if identifier is not None
                    else info.c.plugin_key == entry.item["id"]
                )
                old = (
                    bulk_rows[identifier]
                    if identifiers
                    else (
                        (await conn.execute(select(info).where(condition)))
                        .mappings()
                        .first()
                    )
                )
                if identifier is not None and (not old or old["deleted"]):
                    raise KeyError("plugin not found")
                item = dict(entry.item) if entry else dict(old["item"])
                if old and old["item"].get("_origins"):
                    item["_origins"] = old["item"]["_origins"]
                if identifier is not None and item["id"] != old["plugin_key"]:
                    raise ValueError("plugin ID cannot change")
                # 步骤2：导入不授予上架权限；已删除记录复用ID并恢复为草稿。
                current_status = (
                    status
                    if status is not None
                    else (old["status"] if old and not old["deleted"] else "draft")
                )
                row_id = old["id"] if old else next_id()
                values = {
                    "item": item,
                    "status": current_status,
                    "deleted": int(delete),
                    "update_time": now,
                    "update_by": actor,
                }
                if old:
                    await conn.execute(
                        update(info).where(info.c.id == row_id).values(**values)
                    )
                else:
                    await conn.execute(
                        insert(info).values(
                            id=row_id,
                            plugin_key=item["id"],
                            create_time=now,
                            create_by=actor,
                            **values,
                        )
                    )
                # 步骤3：状态与审计流程同事务写入，失败时整体回滚。
                action = (
                    "delete"
                    if delete
                    else ("publish" if status == "published" else "unpublish")
                    if status
                    else "upsert"
                )
                await conn.execute(
                    insert(flow).values(
                        id=next_id(),
                        plugin_catalog_info_id=row_id,
                        action=action,
                        status=current_status,
                        create_time=now,
                        update_time=now,
                        create_by=actor,
                        update_by=actor,
                        deleted=0,
                    )
                )
                result.append(
                    PluginView(
                        id=str(row_id),
                        item={k: v for k, v in item.items() if k != "_origins"},
                        status=current_status,
                        origins=item.get("_origins", {}),
                    )
                )
            await conn.execute(
                update(instance_settings)
                .where(instance_settings.c.key == "plugin-catalog-clock")
                .values(value=str(last), updated_at=now.isoformat())
            )
        logger.info(
            "Plugin catalog mutation actor={} action={} count={}",
            actor,
            "delete" if delete else status or "upsert",
            len(result),
        )
        return result

    async def _sync_state(self, conn):
        """Lock shared progress so duplicate starts and stale workers cannot race."""
        raw = await conn.scalar(
            select(instance_settings.c.value)
            .where(instance_settings.c.key == "plugin-catalog-sync")
            .with_for_update()
        )
        return PluginSyncState.model_validate_json(raw) if raw else PluginSyncState()

    async def _save_sync(self, conn, state):
        """Persist a heartbeat and progress in the current catalog transaction."""
        state.updatedAt = datetime.now(UTC).isoformat()
        state.leaseUntil = time.time() + 600 if state.status == "running" else 0
        await conn.execute(
            update(instance_settings)
            .where(instance_settings.c.key == "plugin-catalog-sync")
            .values(value=state.model_dump_json(), updated_at=state.updatedAt)
        )

    async def sync_status(self) -> PluginSyncState:
        """Read job progress; expired jobs become retryable rather than locking the UI forever."""
        async with self._engine.begin() as conn:
            state = await self._sync_state(conn)
            if state.status == "running" and state.leaseUntil < time.time():
                state.status = "failed"
                state.errors = [
                    *state.errors[-19:],
                    "同步进程已中断，请重新同步；已提交批次会自动去重。",
                ]
                await self._save_sync(conn, state)
            return state

    async def claim_sync(self, sources: list[str]) -> PluginSyncState:
        """Atomically start one metadata sync across all server processes."""
        async with self._engine.begin() as conn:
            await conn.execute(
                pg_insert(instance_settings)
                .values(
                    key="plugin-catalog-sync",
                    value="{}",
                    updated_at=datetime.now(UTC).isoformat(),
                )
                .on_conflict_do_nothing()
            )
            current = await self._sync_state(conn)
            if current.status == "running" and current.leaseUntil >= time.time():
                raise ValueError("插件目录正在同步，请勿重复触发")
            state = PluginSyncState(
                jobId=str(uuid4()),
                status="running",
                sources=sources,
                startedAt=datetime.now(UTC).isoformat(),
            )
            await self._save_sync(conn, state)
            return state

    async def sync_progress(
        self,
        job_id: str,
        *,
        source: str | None = None,
        total_delta: int = 0,
        finish: bool = False,
        error: str | None = None,
    ) -> PluginSyncState:
        """Update the selected source/known total or finish without overwriting another job."""
        async with self._engine.begin() as conn:
            state = await self._sync_state(conn)
            if state.jobId != job_id or state.status != "running":
                raise RuntimeError("sync job no longer owns the lease")
            if source is not None:
                state.source = source
            state.total += total_delta
            if error:
                state.errors = [*state.errors[-19:], error[:400]]
            if finish:
                state.status = "failed" if state.errors else "completed"
            await self._save_sync(conn, state)
            return state

    async def sync_batch(
        self,
        job_id: str,
        actor: str,
        entries: list[PluginSyncEntry],
        *,
        failed: int = 0,
        skipped: int = 0,
    ) -> PluginSyncState:
        """Bulk metadata upsert and audit/progress commit; preserve publication and deletions."""
        if len(entries) > 200:
            raise ValueError("catalog batch exceeds 200 entries")
        now = datetime.now(UTC)
        async with self._engine.begin() as conn:
            # 步骤1：先校验任务归属，再与手工上下架共用目录锁，防止状态竞争。
            state = await self._sync_state(conn)
            if state.jobId != job_id or state.status != "running":
                raise RuntimeError("sync job no longer owns the lease")
            await conn.execute(
                pg_insert(instance_settings)
                .values(
                    key="plugin-catalog-clock", value="0", updated_at=now.isoformat()
                )
                .on_conflict_do_nothing()
            )
            last = int(
                await conn.scalar(
                    select(instance_settings.c.value)
                    .where(instance_settings.c.key == "plugin-catalog-clock")
                    .with_for_update()
                )
            )

            def next_id():
                """Allocate IDs using the same Snowflake layout as manual edits."""
                nonlocal last
                timestamp = max(int(time.time() * 1000) - 1704067200000, last >> 22)
                sequence = (last & 4095) + 1 if timestamp == last >> 22 else 0
                if sequence > 4095:
                    timestamp += 1
                    sequence = 0
                last = (timestamp << 22) | sequence
                return last

            keys = [entry.item["id"] for entry in entries]
            rows = (
                (await conn.execute(select(info).where(info.c.plugin_key.in_(keys))))
                .mappings()
                .all()
                if keys
                else []
            )
            existing = {row["plugin_key"]: dict(row) for row in rows}
            creates, edits, history = [], [], []
            state.failed += failed
            state.skipped += skipped
            state.processed += len(entries) + failed + skipped
            for entry in entries:
                key = entry.item["id"]
                # 自定义目录按地址保留独立来源，避免多个目录互相覆盖溯源记录。
                origin_key = (
                    "custom:" + hashlib.sha256(entry.origin.url.encode()).hexdigest()
                    if entry.origin.source == "custom"
                    else entry.origin.source
                )
                old = existing.get(key)
                if old and old["deleted"]:
                    state.skipped += 1
                    continue
                # 同一来源内容未变时不重复覆盖另一来源或管理员补充的资料。
                if (
                    old
                    and old["item"].get("_origins", {}).get(origin_key)
                    == entry.origin.model_dump()
                ):
                    state.unchanged += 1
                    continue
                origins = {
                    **(old["item"].get("_origins", {}) if old else {}),
                    origin_key: entry.origin.model_dump(),
                }
                # 步骤2：补充实际存在的元数据；新源未提供的可选安装身份不被清空。
                item = {
                    **(old["item"] if old else {}),
                    **entry.item,
                    "_origins": origins,
                }
                if old and old["item"] == item:
                    state.unchanged += 1
                    continue
                row_id = old["id"] if old else next_id()
                status = old["status"] if old else "draft"
                if old:
                    edits.append(
                        {
                            "pk_id": row_id,
                            "p_item": item,
                            "p_time": now,
                            "p_actor": actor,
                        }
                    )
                    state.updated += 1
                else:
                    creates.append(
                        {
                            "id": row_id,
                            "plugin_key": key,
                            "item": item,
                            "status": "draft",
                            "deleted": 0,
                            "create_time": now,
                            "update_time": now,
                            "create_by": actor,
                            "update_by": actor,
                        }
                    )
                    state.created += 1
                existing[key] = {
                    "id": row_id,
                    "item": item,
                    "status": status,
                    "deleted": 0,
                }
                history.append(
                    {
                        "id": next_id(),
                        "plugin_catalog_info_id": row_id,
                        "action": "sync",
                        "status": status,
                        "create_time": now,
                        "update_time": now,
                        "create_by": actor,
                        "update_by": actor,
                        "deleted": 0,
                    }
                )
            # 步骤3：批量写入资料、流水和进度；整批失败时全部回滚。
            if creates:
                await conn.execute(insert(info), creates)
            if edits:
                await conn.execute(
                    update(info)
                    .where(info.c.id == bindparam("pk_id"))
                    .values(
                        item=bindparam("p_item"),
                        update_time=bindparam("p_time"),
                        update_by=bindparam("p_actor"),
                    ),
                    edits,
                )
            if history:
                await conn.execute(insert(flow), history)
                await conn.execute(
                    update(instance_settings)
                    .where(instance_settings.c.key == "plugin-catalog-clock")
                    .values(value=str(last), updated_at=now.isoformat())
                )
            await self._save_sync(conn, state)
            return state

    async def summary(self) -> PluginCatalogSummary:
        """Aggregate live counts and filter options in SQL without loading plugin documents."""
        live = info.c.deleted == 0
        origins = (
            func.jsonb_each(func.coalesce(info.c.item["_origins"], cast({}, JSONB)))
            .table_valued("key", "value")
            .lateral()
        )
        async with self._engine.connect() as conn:
            await conn.execution_options(isolation_level="REPEATABLE READ")
            async with conn.begin():
                counts = (
                    (
                        await conn.execute(
                            select(
                                func.count().label("total"),
                                func.count()
                                .filter(info.c.status == "published")
                                .label("published"),
                                func.count()
                                .filter(info.c.status == "draft")
                                .label("draft"),
                            )
                            .select_from(info)
                            .where(live)
                        )
                    )
                    .mappings()
                    .one()
                )
                categories = (
                    (
                        await conn.execute(
                            select(
                                func.jsonb_array_elements_text(
                                    func.coalesce(
                                        info.c.item["categories"], cast([], JSONB)
                                    )
                                ).label("category")
                            )
                            .where(live)
                            .distinct()
                            .order_by("category")
                        )
                    )
                    .scalars()
                    .all()
                )
                sources = (
                    (
                        await conn.execute(
                            select(
                                origins.c.key,
                                func.min(
                                    cast(origins.c.value, JSONB)["url"].astext
                                ).label("url"),
                            )
                            .select_from(info.join(origins, true()))
                            .where(live)
                            .group_by(origins.c.key)
                        )
                    )
                    .mappings()
                    .all()
                )
        return PluginCatalogSummary(
            **counts,
            categories=list(categories),
            sourceCount=len(sources),
            sources={r["key"]: r["url"] or r["key"] for r in sources},
        )
