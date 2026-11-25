"""Explicitly triggered, metadata-only catalog sync; no startup fetches or plugin execution."""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import Callable
from typing import Protocol

import httpx
from loguru import logger

from agent_server.core.plugin_catalog import (
    PluginSyncEntry,
    PluginSyncState,
    valid_timestamp,
)
from agent_server.services.plugin_catalog_sources import SOURCES, normalize_plugin


class PluginSyncRepository(Protocol):
    """Persistence boundary shared by HTTP workers and the background importer."""

    async def sync_progress(
        self,
        job_id: str,
        *,
        source: str | None = None,
        total_delta: int = 0,
        finish: bool = False,
        error: str | None = None,
    ) -> PluginSyncState: ...
    async def sync_batch(
        self,
        job_id: str,
        actor: str,
        entries: list[PluginSyncEntry],
        *,
        failed: int = 0,
        skipped: int = 0,
    ) -> PluginSyncState: ...


class PluginCatalogSync:
    """Read only the two reviewed metadata endpoints, retry requests, and commit 200-row batches."""

    def __init__(
        self,
        repository: PluginSyncRepository,
        http_factory: Callable[[], httpx.AsyncClient] | None = None,
    ):
        """Allow test-only transport injection; production does not accept caller-supplied URLs."""
        self.repo = repository
        self.http_factory = http_factory or (
            lambda: httpx.AsyncClient(timeout=20, follow_redirects=False)
        )

    async def _json(self, client: httpx.AsyncClient, url: str, params=None):
        """Bound decompressed metadata size/time and retry transient failures three times."""
        for attempt in range(3):
            try:
                async with (
                    asyncio.timeout(45),
                    client.stream("GET", url, params=params) as response,
                ):
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > 64 * 1024 * 1024:
                            raise ValueError("catalog metadata exceeds 64 MiB")
                        data.extend(chunk)
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise TypeError("catalog response must be an object")
                    return result
            except (httpx.TransportError, httpx.HTTPStatusError, TimeoutError) as exc:
                retryable = not isinstance(
                    exc, httpx.HTTPStatusError
                ) or exc.response.status_code in (429, 500, 502, 503, 504)
                if not retryable or attempt == 2:
                    raise
                await asyncio.sleep(0.25 * (attempt + 1))
        raise RuntimeError("catalog request retry exhausted")

    async def _ingest(self, job_id: str, actor: str, source: str, records: list):
        """Validate metadata one record at a time; malformed entries cannot roll back valid batches."""
        for offset in range(0, len(records), 200):
            entries, failed, skipped = [], 0, 0
            for raw in records[offset : offset + 200]:
                try:
                    entry = normalize_plugin(source, raw)
                    if entry is None:
                        skipped += 1
                    else:
                        entries.append(entry)
                except (ValueError, TypeError, KeyError):
                    failed += 1
            state = await self.repo.sync_batch(
                job_id, actor, entries, failed=failed, skipped=skipped
            )
            logger.info(
                "Plugin catalog sync job={} source={} processed={} created={} updated={} unchanged={} failed={}",
                job_id,
                source,
                state.processed,
                state.created,
                state.updated,
                state.unchanged,
                state.failed,
            )

    async def _source(self, client, job_id, actor, source):
        """Respect dshfind's full dataset and 1024Store's checked page/total boundaries."""
        await self.repo.sync_progress(job_id, source=source)
        if source == "dshfind":
            data = await self._json(client, SOURCES[source])
            records, total = data.get("data"), data.get("total")
            if (
                type(total) is not int
                or not 0 <= total <= 20_000
                or not isinstance(records, list)
                or len(records) != total
                or not isinstance(data.get("data_version"), str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", data["data_version"])
                or not isinstance(data.get("as_of"), str)
                or not valid_timestamp(data.get("as_of"))
            ):
                raise ValueError("dshfind catalog metadata/count is inconsistent")
            await self.repo.sync_progress(job_id, total_delta=total)
            await self._ingest(job_id, actor, source, records)
            return
        page, total, generated = 1, None, None
        while True:
            data = await self._json(
                client, SOURCES[source], {"page": page, "limit": 200}
            )
            count, catalog_count = data.get("total"), data.get("catalogTotal")
            if (
                type(count) is not int
                or not 0 <= count <= 100_000
                or type(catalog_count) is not int
                or not count <= catalog_count <= 100_000
                or data.get("page") != page
                or data.get("limit") != 200
                or not isinstance(data.get("plugins"), list)
                or data.get("totalPages") != max(1, math.ceil(count / 200))
                or len(data["plugins"])
                != (0 if count == 0 else min(200, count - (page - 1) * 200))
                or not isinstance(data.get("generatedAt"), str)
                or not valid_timestamp(data.get("generatedAt"))
                or data.get("source") != "ok"
            ):
                raise ValueError("1024Store page metadata/count is inconsistent")
            if total is None:
                total, generated = count, data["generatedAt"]
                await self.repo.sync_progress(job_id, total_delta=total)
            elif count != total or data["generatedAt"] != generated:
                raise ValueError(
                    "1024Store changed dataset while paging; retry the sync"
                )
            await self._ingest(job_id, actor, source, data["plugins"])
            if page >= data["totalPages"]:
                return
            page += 1

    async def run(self, state: PluginSyncState, actor: str):
        """Run only after an admin POST; an interrupted job can be safely repeated."""
        try:
            async with self.http_factory() as client:
                for source in state.sources:
                    try:
                        await self._source(client, state.jobId, actor, source)
                    except (
                        httpx.HTTPError,
                        ValueError,
                        TypeError,
                        TimeoutError,
                    ) as exc:
                        # No response body or entire catalog is written to logs/progress.
                        message = f"{source}: {type(exc).__name__}: {str(exc)[:200]}"
                        logger.warning(
                            "Plugin catalog sync job={} {}", state.jobId, message
                        )
                        await self.repo.sync_progress(state.jobId, error=message)
            await self.repo.sync_progress(state.jobId, finish=True)
        except asyncio.CancelledError:
            await self.repo.sync_progress(
                state.jobId, finish=True, error="服务停止，同步已中断，可重新触发"
            )
            raise
        except Exception:  # noqa: BLE001 - finalize background job failures visibly
            logger.exception("Plugin catalog sync job={} failed", state.jobId)
            await self.repo.sync_progress(
                state.jobId,
                finish=True,
                error="同步进程失败，已提交批次保留，可重新触发",
            )
