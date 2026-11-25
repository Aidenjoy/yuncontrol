"""Metadata-only counterparts of YunWork dsh-community-market's two built-in adapters."""

import re
from typing import Any
from urllib.parse import urlsplit

from agent_server.core.plugin_catalog import PluginOrigin, PluginSyncEntry

SOURCES = {
    "1024store": "https://deepseek1024.com/api/v2/plugins",
    "dshfind": "https://api.dshfind.com/v1/catalog",
}
_NPM = re.compile(r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$")
_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def normalize_plugin(source: str, raw: Any) -> PluginSyncEntry | None:
    """Reuse reviewed repository/npm identities, retaining supplied install metadata as inert data."""
    if not isinstance(raw, dict):
        raise TypeError("catalog item must be an object")
    if source == "dshfind" and (
        raw.get("is_plugin") is not True or raw.get("is_risky") is True
    ):
        return None
    supplied = raw.get("repository_url" if source == "dshfind" else "url")
    if not isinstance(supplied, str):
        raise TypeError("missing repository URL")
    url = urlsplit(supplied)
    parts = [part for part in url.path.split("/") if part]
    if (
        url.scheme != "https"
        or url.hostname != "github.com"
        or url.port
        or url.username
        or url.password
        or url.query
        or url.fragment
        or len(parts) != 2
    ):
        raise ValueError("invalid GitHub repository identity")
    owner, name = parts[0], re.sub(r"\.git$", "", parts[1], flags=re.IGNORECASE)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,99}", owner) or not re.fullmatch(
        r"[a-zA-Z0-9._-]{1,100}", name
    ):
        raise ValueError("invalid repository name")
    if (
        source == "dshfind"
        and str(raw.get("full_name", "")).lower().removesuffix(".git")
        != f"{owner}/{name}".lower()
    ):
        raise ValueError("repository and full_name disagree")
    identity = f"{owner}/{name}".lower()
    subdirectory = None
    if source == "1024store" and isinstance(raw.get("id"), str):
        segments = raw["id"].split("/")
        if (
            len(segments) > 2
            and "/".join(segments[:2]).lower().removesuffix(".git") == identity
        ):
            subdirectory = "/".join(segments[2:])
            identity += "/" + subdirectory
    display = raw.get("name")
    if not isinstance(display, str) or not display:
        raise ValueError("missing plugin name")
    description = raw.get("description", "")
    if isinstance(description, dict):
        description = description.get("zh") or description.get("en") or display
    if (
        not isinstance(description, str)
        or len(description) > 5000
        or re.search(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]", description)
    ):
        description = display
    item = {
        "id": f"github:{identity}",
        "name": display,
        "displayName": display,
        "summary": description[:1000] or display,
        "repository": {"url": f"https://github.com/{owner.lower()}/{name.lower()}"},
        "publisher": {"name": owner, "url": f"https://github.com/{owner.lower()}"},
    }
    if subdirectory is not None:
        item["repository"]["subdirectory"] = subdirectory
    if description:
        item["description"] = description[:5000]
    category = raw.get("category")
    if isinstance(category, str) and re.fullmatch(r"[a-z0-9][a-z0-9._:-]*", category):
        item["categories"] = [category]
    if source == "dshfind":
        tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
        tags = [*tags, raw.get("language")]
        keywords = list(
            dict.fromkeys(
                tag for tag in tags if isinstance(tag, str) and 0 < len(tag) <= 64
            )
        )[:64]
        if keywords:
            item["keywords"] = keywords
    timestamp = raw.get("pushed_at" if source == "dshfind" else "pushedAt")
    if timestamp:
        item["updatedAt"] = timestamp
    install = raw.get("install")
    if source == "dshfind" and isinstance(install, dict):
        methods = (
            install.get("methods") if isinstance(install.get("methods"), list) else []
        )
        targets = {
            (m["spec"], m["revision"])
            for m in methods
            if isinstance(m, dict)
            and m.get("kind") == "npm"
            and m.get("verification") == "verified"
            and m.get("code") == "repository_backlink"
            and m.get("requiresBuildAllowance") is False
            and isinstance(m.get("spec"), str)
            and _NPM.fullmatch(m["spec"])
            and len(m["spec"]) <= 214
            and isinstance(m.get("revision"), str)
            and _VERSION.fullmatch(m["revision"])
            and len(m["revision"]) <= 64
            and (install.get("pkg_name") is None or install["pkg_name"] == m["spec"])
        }
        if len(targets) == 1:
            package, version = next(iter(targets))
            item.update(
                package={"registry": "npm", "name": package}, latestVersion=version
            )
    elif source == "1024store" and isinstance(install, str) and len(install) <= 1024:
        tokens = install.strip().split()
        if (
            len(tokens) == 6
            and tokens[:3] == ["dsh", "plugin", "--profile"]
            and tokens[4] == "add"
            and re.fullmatch(r"[A-Za-z0-9_-]+", tokens[3])
            and all(re.fullmatch(r"[A-Za-z0-9@:/._#+=-]+", token) for token in tokens)
        ):
            target = tokens[5]
            separator = (
                target.find("@", target.find("/") + 1)
                if target.startswith("@")
                else target.find("@")
            )
            package = target if separator < 0 else target[:separator]
            if _NPM.fullmatch(package):
                item["package"] = {"registry": "npm", "name": package}
    # Icon/download/command fields are retained, but never fetched or executed.
    metadata = {
        key: raw[key]
        for key in (
            "id",
            "name",
            "owner",
            "url",
            "repository_url",
            "full_name",
            "category",
            "description",
            "pushedAt",
            "pushed_at",
            "added",
            "stars",
            "installCount",
            "install",
            "media",
            "tags",
            "language",
            "is_plugin",
            "is_risky",
            "version",
            "downloadUrl",
            "download_url",
            "iconUrl",
            "icon_url",
        )
        if key in raw
    }
    media = raw.get("media")
    if isinstance(media, dict) and isinstance(media.get("icon"), dict):
        icon = media["icon"]
        if isinstance(icon.get("url"), str):
            icon_url = urlsplit(icon["url"])
            if (
                icon_url.scheme == "https"
                and not icon_url.username
                and not icon_url.password
                and not icon_url.port
                and not icon_url.fragment
            ):
                item["media"] = {
                    "icon": {key: icon[key] for key in ("url", "alt") if key in icon}
                }
    return PluginSyncEntry(
        item=item,
        origin=PluginOrigin(
            source=source,
            url=SOURCES[source],
            itemId=str(raw.get("full_name" if source == "dshfind" else "id", identity)),
            metadata=metadata,
        ),
    )
