"""Catalog persistence: serialize writers and audit publication changes atomically."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import Text, cast, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_server.core.plugin_catalog import PluginList, PluginView, PluginWrite
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
    ) -> PluginList:
        """Filter publication before counting/paging; category and search are literal input."""
        conditions = [info.c.deleted == 0]
        if public:
            conditions.append(info.c.status == "published")
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
                PluginView(id=str(r["id"]), item=r["item"], status=r["status"])
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

            entries = items if items is not None else [None]
            for entry in entries:
                condition = (
                    info.c.id == identifier
                    if identifier is not None
                    else info.c.plugin_key == entry.item["id"]
                )
                old = (
                    (await conn.execute(select(info).where(condition)))
                    .mappings()
                    .first()
                )
                if identifier is not None and (not old or old["deleted"]):
                    raise KeyError("plugin not found")
                item = entry.item if entry else old["item"]
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
                    PluginView(id=str(row_id), item=item, status=current_status)
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
