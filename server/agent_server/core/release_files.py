"""Validated release records and version comparison; no download or storage behavior."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

Platform = Literal[
    "desktop-macos-arm64",
    "desktop-macos-x64",
    "desktop-windows",
    "android",
    "ios",
]

_VERSION = re.compile(r"^[vV]?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?$")


class ReleaseWrite(BaseModel):
    """One installer record submitted by an administrator."""

    model_config = ConfigDict(extra="forbid", strict=True)

    platform: Platform
    version: str = Field(min_length=1, max_length=64)
    downloadUrl: str = Field(min_length=1, max_length=2048)
    fileName: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=4000)
    published: bool = False

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Keep the registry comparable: dotted numbers with an optional suffix."""
        text = value.strip()
        if not _VERSION.fullmatch(text):
            raise ValueError("version must look like 1.2.3 or 1.2.3-beta.1")
        return text.lstrip("vV")

    @field_validator("downloadUrl")
    @classmethod
    def validate_download_url(cls, value: str) -> str:
        """Public clients download directly, so keep credentials out of the URL."""
        text = value.strip()
        url = urlsplit(text)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
        ):
            raise ValueError("downloadUrl must be a credential-free HTTP(S) URL")
        return text

    @field_validator("fileName", "notes")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ReleaseView(BaseModel):
    """Administrator-facing record, including unpublished drafts."""

    id: str
    platform: str
    version: str
    downloadUrl: str
    fileName: str
    notes: str
    published: bool
    updatedAt: str
    updatedBy: str


class ReleaseList(BaseModel):
    items: list[ReleaseView]
    total: int


class PublicRelease(BaseModel):
    """Published record exposed to clients checking for updates."""

    platform: str
    version: str
    downloadUrl: str
    fileName: str
    notes: str
    publishedAt: str | None

    @computed_field
    @property
    def type(self) -> str:
        """Expose the selected platform as type while preserving the existing platform field."""
        return self.platform


class PublicReleaseList(BaseModel):
    items: list[PublicRelease]


class ReleaseCheck(BaseModel):
    """Answer for one client: newest release plus whether it is newer."""

    platform: str
    currentVersion: str
    latestVersion: str | None
    updateAvailable: bool
    downloadUrl: str | None
    fileName: str
    notes: str
    publishedAt: str | None


def version_key(value: str) -> tuple[tuple[int, ...], bool, str]:
    """Split a version into numbers, a release flag, and a pre-release suffix."""
    match = _VERSION.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid version: {value!r}")
    numbers = tuple(int(part) for part in match.group(1).split("."))
    suffix = match.group(2)
    # A final release sorts above its own pre-releases (1.2.3 > 1.2.3-rc.1).
    return numbers, suffix is None, suffix or ""


def compare_versions(left: str, right: str) -> int:
    """Return 1, 0, or -1; missing numeric segments count as zero (1.2 == 1.2.0)."""
    left_numbers, left_final, left_suffix = version_key(left)
    right_numbers, right_final, right_suffix = version_key(right)
    size = max(len(left_numbers), len(right_numbers))
    padded_left = left_numbers + (0,) * (size - len(left_numbers))
    padded_right = right_numbers + (0,) * (size - len(right_numbers))
    if padded_left != padded_right:
        return 1 if padded_left > padded_right else -1
    if left_final != right_final:
        return 1 if left_final else -1
    if left_suffix == right_suffix:
        return 0
    return 1 if left_suffix > right_suffix else -1
