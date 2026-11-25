"""Validated YunWork catalog records and administrator requests; no installer behavior."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, Field, field_validator

_schema = json.loads(
    (
        Path(__file__).parent / "plugin_schemas/catalog-provider-page.schema.json"
    ).read_text()
)
_formats = FormatChecker()


@_formats.checks("date-time", raises=(ValueError, TypeError))
def valid_timestamp(value: Any) -> bool:
    """Validate RFC3339 timestamps even when jsonschema's optional format extras are absent."""
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
        value,
    ):
        return False
    return datetime.fromisoformat(value.upper()).tzinfo is not None


_validator = Draft202012Validator(_schema, format_checker=_formats)


class PluginWrite(BaseModel):
    """One upstream protocol item; publication is deliberately a separate operation."""

    item: dict[str, Any]

    @field_validator("item")
    @classmethod
    def validate_item(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject metadata the existing desktop catalog parser cannot consume."""
        errors = sorted(
            _validator.iter_errors(
                {"schemaVersion": "1.0.0", "items": [value], "page": {}}
            ),
            key=lambda e: str(e.path),
        )
        if errors:
            raise ValueError(errors[0].message)
        repository = value.get("repository")
        if repository:
            url = urlsplit(repository["url"])
            segments = [part for part in url.path.split("/") if part]
            if (
                url.scheme != "https"
                or url.username
                or url.password
                or url.query
                or url.fragment
                or not segments
            ):
                raise ValueError(
                    "repository must be a credential-free HTTPS repository URL"
                )
            if url.hostname == "github.com" and len(segments) != 2:
                raise ValueError("GitHub repository requires owner/repository")
            if "subdirectory" in repository:
                for part in repository["subdirectory"].split("/"):
                    if re.search(r"%(?![0-9a-fA-F]{2})", part):
                        raise ValueError("invalid subdirectory percent encoding")
                    decoded = unquote(part)
                    if (
                        not part
                        or decoded in (".", "..")
                        or "/" in decoded
                        or "\\" in decoded
                    ):
                        raise ValueError(
                            "repository subdirectory must be a safe relative POSIX path"
                        )
        if value.get("installSource") and (
            not repository or urlsplit(repository["url"]).hostname != "github.com"
        ):
            raise ValueError("pinned install source requires a GitHub repository")
        return value


class PluginPublication(BaseModel):
    """Explicit administrator publication decision, independent of metadata imports."""

    status: Literal["draft", "published"]


class PluginImport(BaseModel):
    """Atomic import of standard provider-page items; never imports publication state."""

    items: list[PluginWrite] = Field(min_length=1, max_length=200)


class PluginView(PluginWrite):
    """Administrator catalog entry with lossless string serialization of its bigint ID."""

    id: str
    status: Literal["draft", "published"]
    origins: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PluginList(BaseModel):
    """Administrator catalog page, using the repository's limit/offset conventions."""

    items: list[PluginView]
    total: int
    revision: str = "0"


class PluginOrigin(BaseModel):
    """Original catalog metadata retained for inspection, never an executable install plan."""

    source: Literal["1024store", "dshfind", "custom"]
    url: str
    itemId: str
    metadata: dict[str, Any]


class PluginSyncEntry(PluginWrite):
    """Validated public item plus its original provider metadata."""

    origin: PluginOrigin


class PluginSyncRequest(BaseModel):
    """Choose built-in catalogs or an explicit public HTTPS metadata endpoint."""

    url: str | None = Field(default=None, max_length=2048)

    @field_validator("url")
    @classmethod
    def catalog_url(cls, value: str | None) -> str | None:
        """Reject ambiguous URLs before the background worker resolves the public host."""
        if value is None:
            return None
        value = value.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.fragment
            or any(c.isspace() for c in value)
        ):
            raise ValueError("目录地址必须是无账号凭据的 HTTPS 443 地址")
        return value

    sources: list[Literal["1024store", "dshfind"]] = Field(
        default_factory=lambda: ["1024store", "dshfind"], min_length=1, max_length=2
    )

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, value):
        """Reject duplicate provider requests within one job."""
        if len(value) != len(set(value)):
            raise ValueError("duplicate catalog sources")
        return value


class PluginSyncState(BaseModel):
    """Shared job progress persisted in existing instance settings across server workers."""

    jobId: str | None = None
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    sources: list[Literal["1024store", "dshfind", "custom"]] = Field(
        default_factory=list
    )
    source: str | None = None
    total: int = 0
    processed: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
    startedAt: str | None = None
    updatedAt: str | None = None
    leaseUntil: float = 0


class PluginCatalogSummary(BaseModel):
    """Global live catalog counts and distinct server-side filter options."""

    total: int
    published: int
    draft: int
    sourceCount: int
    categories: list[str]
    sources: dict[str, str]


class PluginBulkPublication(PluginPublication):
    """Explicit publication decision for up to one hundred existing catalog records."""

    ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def valid_ids(cls, value: list[int]) -> list[int]:
        """Reject duplicates and IDs outside PostgreSQL bigint before any writes."""
        if len(set(value)) != len(value) or any(
            v < 1 or v > 9223372036854775807 for v in value
        ):
            raise ValueError("invalid or duplicate plugin IDs")
        return value


class PluginBulkResult(BaseModel):
    """Number of records whose explicit bulk publication request completed."""

    updated: int
