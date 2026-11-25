"""Explicitly triggered, metadata-only catalog sync; no startup fetches or plugin execution."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import re
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx
from loguru import logger

from agent_server.core.plugin_catalog import (
    PluginOrigin,
    PluginSyncEntry,
    PluginSyncRequest,
    PluginSyncState,
    _validator,
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
        """Allow transport injection; validate and pin custom public endpoints per request."""
        self.repo = repository
        self.http_factory = http_factory or (
            lambda: httpx.AsyncClient(
                timeout=20, follow_redirects=False, trust_env=False
            )
        )

    async def _json(
        self, client: httpx.AsyncClient, url: str, params=None, *, custom=False
    ):
        """Bound decompressed metadata size/time and retry transient failures three times."""
        for attempt in range(3):
            try:
                request_url, headers, extensions = url, {}, {}
                if custom:
                    request_url, headers, extensions = await self._public_request(url)
                async with (
                    asyncio.timeout(45),
                    client.stream(
                        "GET",
                        request_url,
                        params=params,
                        headers=headers,
                        extensions=extensions,
                    ) as response,
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

    async def _ingest(
        self, job_id: str, actor: str, source: str, records: list, *, url=None
    ):
        """Validate metadata one record at a time; malformed entries cannot roll back valid batches."""
        for offset in range(0, len(records), 200):
            entries, failed, skipped = [], 0, 0
            for raw in records[offset : offset + 200]:
                try:
                    if source == "standard":
                        entry = PluginSyncEntry(
                            item=raw,
                            origin=PluginOrigin(
                                source="custom",
                                url=url,
                                itemId=str(raw.get("id", "")),
                                metadata=raw,
                            ),
                        )
                    else:
                        entry = normalize_plugin(source, raw)
                        if entry is not None and url and url != SOURCES[source]:
                            entry.origin.source = "custom"
                            entry.origin.url = url
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

    async def _source(self, client, job_id, actor, source, *, url=None, initial=None):
        """Respect dshfind's full dataset and 1024Store's checked page/total boundaries."""
        await self.repo.sync_progress(job_id, source=source)
        if source == "dshfind":
            data = (
                initial
                if initial is not None
                else await self._json(client, url or SOURCES[source], custom=bool(url))
            )
            records, total = data.get("data"), data.get("total")
            logger.info(
                "Plugin catalog metadata job={} source={} total={} records={}",
                job_id,
                source,
                total if type(total) is int else None,
                len(records) if isinstance(records, list) else None,
            )
            self._integer(total, "total", 0, 100_000)
            if not isinstance(records, list):
                raise TypeError("data: expected an array")
            self._expect(len(records), total, "data.length")
            version = data.get("data_version")
            if not isinstance(version, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", version
            ):
                raise ValueError(
                    "data_version: expected sha256:<64 lowercase hex digits>"
                )
            self._timestamp(data.get("as_of"), "as_of")
            await self.repo.sync_progress(job_id, total_delta=total)
            await self._ingest(job_id, actor, source, records, url=url)
            return
        page, total, generated = 1, None, None
        while True:
            data = (
                initial
                if page == 1 and initial is not None
                else await self._json(
                    client,
                    url or SOURCES[source],
                    {
                        **dict(parse_qsl(urlsplit(url or "").query)),
                        "page": page,
                        "limit": 200,
                    },
                    custom=bool(url),
                )
            )
            count, catalog_count = data.get("total"), data.get("catalogTotal")
            logger.info(
                "Plugin catalog metadata job={} source={} requested_page={} total={} records={}",
                job_id,
                source,
                page,
                count if type(count) is int else None,
                len(data["plugins"]) if isinstance(data.get("plugins"), list) else None,
            )
            self._integer(count, "total", 0, 100_000)
            self._integer(catalog_count, "catalogTotal", count, 100_000)
            self._expect(data.get("page"), page, "page")
            self._expect(data.get("limit"), 200, "limit")
            records = data.get("plugins")
            if not isinstance(records, list):
                raise TypeError("plugins: expected an array")
            self._expect(
                data.get("totalPages"), max(1, math.ceil(count / 200)), "totalPages"
            )
            expected_count = 0 if count == 0 else min(200, count - (page - 1) * 200)
            self._expect(len(records), expected_count, "plugins.length")
            generated_at = self._timestamp(data.get("generatedAt"), "generatedAt")
            # 上游降级时仍可返回缓存目录；保持分页快照和条数校验，不将缓存当作空目录。
            source_status = data.get("source")
            if source_status not in ("ok", "stale"):
                raise ValueError(
                    f"source: expected 'ok' or 'stale', got {str(source_status)[:80]!r}"
                )
            if source_status == "stale" and page == 1:
                logger.warning(
                    "Plugin catalog cached snapshot job={} source={} generated_at={}",
                    job_id,
                    source,
                    generated_at,
                )
            if total is None:
                total, generated = count, generated_at
                await self.repo.sync_progress(job_id, total_delta=total)
            elif count != total or generated_at != generated:
                raise ValueError(
                    "1024Store changed dataset while paging; retry the sync"
                )
            await self._ingest(job_id, actor, source, data["plugins"], url=url)
            if page >= data["totalPages"]:
                return
            page += 1

    async def run(self, state: PluginSyncState, actor: str, url: str | None = None):
        """Run only after an admin POST; an interrupted job can be safely repeated."""
        try:
            async with self.http_factory() as client:
                for source in state.sources:
                    try:
                        if source == "custom":
                            await self._custom(client, state.jobId, actor, url)
                        else:
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

    @staticmethod
    def _integer(value: object, field: str, minimum: int, maximum: int) -> None:
        """Reject invalid counts before arithmetic, reporting only bounded scalar metadata."""
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(
                f"{field}: expected integer in [{minimum}, {maximum}], got {str(value)[:80]!r}"
            )

    @staticmethod
    def _expect(actual: object, expected: object, field: str) -> None:
        """Identify a mismatched metadata field without exposing the catalog body."""
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(
                f"{field}: expected {expected!r}, got {str(actual)[:80]!r}"
            )

    @staticmethod
    def _timestamp(value: object, field: str) -> str:
        """Normalize timezone-qualified ISO timestamps locally; retain strict stored contracts."""
        if isinstance(value, str) and len(value) <= 80:
            try:
                parsed = datetime.fromisoformat(value.strip().upper())
                if parsed.tzinfo is not None:
                    return parsed.astimezone(UTC).isoformat()
            except ValueError:
                pass
        raise ValueError(
            f"{field}: expected ISO timestamp with timezone, got {str(value)[:80]!r}"
        )

    @staticmethod
    async def _public_request(url: str) -> tuple[str, dict, dict]:
        """Resolve public HTTPS hosts and pin the connection to prevent DNS rebinding."""
        PluginSyncRequest(url=url)
        parts = urlsplit(url)
        host = parts.hostname
        try:
            infos = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    host, 443, type=socket.SOCK_STREAM
                ),
                10,
            )
        except (OSError, TimeoutError) as exc:
            raise ValueError("目录域名无法解析") from exc
        addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
        if not addresses or not all(
            ipaddress.ip_address(a).is_global for a in addresses
        ):
            raise ValueError("目录地址必须解析到公网 IP，不允许访问本机或内网")
        address = addresses[0]
        netloc = f"[{address}]" if ":" in address else address
        return (
            urlunsplit(("https", netloc, parts.path, parts.query, "")),
            {"Host": parts.netloc},
            {"sni_hostname": host},
        )

    async def _custom(self, client, job_id: str, actor: str, url: str) -> None:
        """Detect supported directory formats; standard cursors stay on the supplied endpoint."""
        logger.info(
            "Plugin catalog custom sync job={} host={}", job_id, urlsplit(url).hostname
        )
        data = await self._json(client, url, custom=True)
        # 标准源配置只允许跳往同源目录接口，不接受任意远程重定向。
        if data.get("manifestVersion") == "1.0.0":
            transport = data.get("transport", {})
            endpoint = (
                transport.get("endpoint") if isinstance(transport, dict) else None
            )
            if (
                not isinstance(endpoint, str)
                or urlsplit(endpoint).netloc != urlsplit(url).netloc
                or transport.get("kind") != "https-json"
                or transport.get("method", "GET") != "GET"
            ):
                raise ValueError("标准目录配置必须提供同源 HTTPS GET 接口")
            PluginSyncRequest(url=endpoint)
            url = endpoint
            data = await self._json(client, url, custom=True)
        if "plugins" in data and "totalPages" in data:
            # 1024Store 必须从第一页、200 条开始，忽略用户地址里的分页参数。
            data = await self._json(
                client,
                url,
                {**dict(parse_qsl(urlsplit(url).query)), "page": 1, "limit": 200},
                custom=True,
            )
            await self._source(
                client, job_id, actor, "1024store", url=url, initial=data
            )
            return
        if "data" in data and "data_version" in data:
            await self._source(client, job_id, actor, "dshfind", url=url, initial=data)
            return
        seen, processed, expected_total, revision = set(), 0, None, data.get("revision")
        for _ in range(1000):
            errors = list(_validator.iter_errors(data))
            if errors:
                error = errors[0]
                field = ".".join(str(p) for p in error.path) or "root"
                raise ValueError(f"标准目录格式错误: {field} ({error.validator})")
            if data.get("revision") != revision:
                raise ValueError("标准目录同步期间版本变化，请重试")
            records = data["items"]
            total = data["page"].get("total")
            if total is not None:
                self._integer(total, "page.total", 0, 100_000)
                if expected_total is not None:
                    self._expect(total, expected_total, "page.total")
                expected_total = total
            processed += len(records)
            if processed > 100_000:
                raise ValueError("目录条目超过 100000 上限")
            await self.repo.sync_progress(job_id, total_delta=len(records))
            await self._ingest(job_id, actor, "standard", records, url=url)
            cursor = data["page"].get("nextCursor")
            if not cursor:
                if expected_total is not None:
                    self._expect(processed, expected_total, "items.length")
                return
            if cursor in seen:
                raise ValueError("标准目录返回重复分页游标")
            seen.add(cursor)
            data = await self._json(
                client,
                url,
                {**dict(parse_qsl(urlsplit(url).query)), "cursor": cursor},
                custom=True,
            )
        raise ValueError("目录分页超过 1000 页上限")
