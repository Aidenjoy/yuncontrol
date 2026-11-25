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
    return (
        datetime.fromisoformat(value.upper()).tzinfo is not None
    )


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


class PluginList(BaseModel):
    """Administrator catalog page, using the repository's limit/offset conventions."""

    items: list[PluginView]
    total: int
    revision: str = "0"
