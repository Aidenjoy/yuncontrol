"""Release registry persistence; the newest published row per platform wins."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_server.core.release_files import (
    Platform,
    PublicRelease,
    ReleaseView,
    ReleaseWrite,
)
from agent_server.infra.db.schema import release_files as table


class ReleaseNotFoundError(KeyError):
    """The requested release is missing or already deleted."""


class DuplicateReleaseError(ValueError):
    """This platform already holds a live record; edit it instead."""

    def __init__(self, platform: str, version: str | None = None) -> None:
        self.platform = platform
        self.version = version
        super().__init__(f"{platform} already has a release")


def _view(row) -> ReleaseView:
    return ReleaseView(
        id=str(row["id"]),
        platform=row["platform"],
        version=row["version"],
        downloadUrl=row["download_url"],
        fileName=row["file_name"],
        notes=row["notes"],
        published=bool(row["published"]),
        updatedAt=row["update_time"].isoformat(),
        updatedBy=row["update_by"],
    )


def _public(row) -> PublicRelease:
    return PublicRelease(
        platform=row["platform"],
        version=row["version"],
        downloadUrl=row["download_url"],
        fileName=row["file_name"],
        notes=row["notes"],
        publishedAt=row["update_time"].isoformat(),
    )


def _like(value: str) -> str:
    return (
        "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    )


class ReleaseFileRepository:
    """Read and write release rows on the existing async engine."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list(
        self,
        *,
        platform: str | None = None,
        q: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ReleaseView], int]:
        """Return live records newest-first, with the total before paging."""
        conditions = [table.c.deleted == 0, table.c.platform != "desktop-linux"]
        if platform:
            conditions.append(table.c.platform == platform)
        if q:
            needle = _like(q)
            conditions.append(
                or_(
                    table.c.version.ilike(needle, escape="\\"),
                    table.c.file_name.ilike(needle, escape="\\"),
                    table.c.download_url.ilike(needle, escape="\\"),
                )
            )
        async with self._engine.connect() as conn:
            total = await conn.scalar(
                select(func.count()).select_from(table).where(*conditions)
            )
            rows = (
                (
                    await conn.execute(
                        select(table)
                        .where(*conditions)
                        .order_by(table.c.update_time.desc(), table.c.id.desc())
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .mappings()
                .all()
            )
        return [_view(row) for row in rows], int(total or 0)

    async def get(self, release_id: int) -> ReleaseView:
        """Read one live record; missing or deleted rows raise."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        select(table).where(
                            table.c.id == release_id, table.c.deleted == 0
                        )
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ReleaseNotFoundError(str(release_id))
        return _view(row)

    async def create(self, payload: ReleaseWrite, actor: str) -> ReleaseView:
        """Insert one record; the actor is recorded on both audit fields."""
        now = datetime.now(UTC)
        values = {
            "platform": payload.platform,
            "version": payload.version,
            "download_url": payload.downloadUrl,
            "file_name": payload.fileName,
            "notes": payload.notes,
            "published": int(payload.published),
            "create_time": now,
            "update_time": now,
            "create_by": actor,
            "update_by": actor,
        }
        try:
            async with self._engine.begin() as conn:
                release_id = await conn.scalar(
                    insert(table).values(**values).returning(table.c.id)
                )
        except IntegrityError as exc:
            # Only known publication-identity constraints represent a duplicate platform.
            # Other failures (e.g. a stale CHECK constraint) must retain their real cause.
            constraint = getattr(exc.orig, "constraint_name", None)
            if constraint is None:
                constraint = getattr(
                    getattr(exc.orig, "__cause__", None), "constraint_name", None
                )
            if constraint not in {
                "uk_release_files_active_platform",
                "uk_release_files_active_version",
            }:
                raise
            raise DuplicateReleaseError(
                payload.platform, await self._live_version(payload.platform)
            ) from exc
        return await self.get(int(release_id))

    async def update(
        self, release_id: int, payload: ReleaseWrite, actor: str
    ) -> ReleaseView:
        """Replace a record; deleted rows are not editable."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(
                    update(table)
                    .where(table.c.id == release_id, table.c.deleted == 0)
                    .values(
                        platform=payload.platform,
                        version=payload.version,
                        download_url=payload.downloadUrl,
                        file_name=payload.fileName,
                        notes=payload.notes,
                        published=int(payload.published),
                        update_time=datetime.now(UTC),
                        update_by=actor,
                    )
                )
                if not result.rowcount:
                    raise ReleaseNotFoundError(str(release_id))
        except IntegrityError as exc:
            # Only known publication-identity constraints represent a duplicate platform.
            # Other failures (e.g. a stale CHECK constraint) must retain their real cause.
            constraint = getattr(exc.orig, "constraint_name", None)
            if constraint is None:
                constraint = getattr(
                    getattr(exc.orig, "__cause__", None), "constraint_name", None
                )
            if constraint not in {
                "uk_release_files_active_platform",
                "uk_release_files_active_version",
            }:
                raise
            raise DuplicateReleaseError(
                payload.platform, await self._live_version(payload.platform)
            ) from exc
        return await self.get(release_id)

    async def delete(self, release_id: int, actor: str) -> None:
        """Soft-delete one record so its version can be registered again."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                update(table)
                .where(table.c.id == release_id, table.c.deleted == 0)
                .values(deleted=1, update_time=datetime.now(UTC), update_by=actor)
            )
            if not result.rowcount:
                raise ReleaseNotFoundError(str(release_id))

    async def latest(self, platform: str) -> PublicRelease | None:
        """Return the platform's published build; there is at most one."""
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        select(table)
                        .where(
                            table.c.platform == platform,
                            table.c.published == 1,
                            table.c.deleted == 0,
                        )
                        .limit(1)
                    )
                )
                .mappings()
                .first()
            )
        return _public(row) if row is not None else None

    async def latest_all(self) -> list[PublicRelease]:
        """Return the published build of every platform that has one."""
        async with self._engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        select(table)
                        .where(
                            table.c.published == 1,
                            table.c.deleted == 0,
                            table.c.platform.in_(get_args(Platform)),
                        )
                        .order_by(table.c.platform)
                    )
                )
                .mappings()
                .all()
            )
        return [_public(row) for row in rows]

    async def _live_version(self, platform: str) -> str | None:
        """Read the version already registered for a platform, for error text."""
        async with self._engine.connect() as conn:
            return await conn.scalar(
                select(table.c.version).where(
                    table.c.platform == platform, table.c.deleted == 0
                )
            )
