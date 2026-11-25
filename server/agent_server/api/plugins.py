"""Administrator catalog management and the public YunWork standard HTTP adapter."""

import base64
import hashlib
import json
import os
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import Path as ApiPath

from agent_server.core.models import UserView
from agent_server.core.plugin_catalog import (
    PluginImport,
    PluginList,
    PluginPublication,
    PluginView,
    PluginWrite,
)
from agent_server.deps import get_store, require_admin
from agent_server.infra.repositories.facade import Store
from agent_server.infra.repositories.plugin_catalog import PluginCatalogRepository

router = APIRouter(prefix="/plugins", tags=["plugins"])
admin_router = APIRouter(
    prefix="/admin/plugins", tags=["admin"], dependencies=[Depends(require_admin)]
)


def repository(store: Annotated[Store, Depends(get_store)]) -> PluginCatalogRepository:
    """Reuse the server database and its lifecycle, without a separate backend."""
    return PluginCatalogRepository(store._engine)


@router.get("/config")
async def config(response: Response):
    """Return the standard source manifest; require an explicitly trusted public HTTPS origin."""
    origin = (
        os.environ.get("AGENT_SERVER_PLUGIN_ORIGIN")
        or os.environ.get("AGENT_SERVER_PUBLIC_ORIGIN", "")
    ).rstrip("/")
    try:
        parsed = urlsplit(origin)
        valid_port = parsed.port in (None, 443)
    except ValueError:
        raise HTTPException(503, "invalid plugin origin") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not valid_port
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(
            503, "AGENT_SERVER_PLUGIN_ORIGIN must be a public HTTPS origin on port 443"
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "manifestVersion": "1.0.0",
        "providerId": "com.yundashi.plugins",
        "name": "云大师",
        "attribution": {"name": "云大师", "url": origin + "/"},
        "transport": {
            "kind": "https-json",
            "endpoint": origin + "/api/v2/plugins/v1/plugins",
            "method": "GET",
        },
        "query": {
            "supported": ["q", "category", "cursor", "limit"],
            "defaultLimit": 50,
            "maxLimit": 100,
            "sorts": [],
        },
    }


@router.get("/v1/plugins")
@router.get("/search")
async def search(
    response: Response,
    q: str = Query("", max_length=200),
    category: Annotated[list[str] | None, Query(max_length=20)] = None,
    cursor: str = Query("", max_length=512),
    limit: int = Query(50, ge=1, le=100),
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """Read current published rows on every page, including requests using an older cursor."""
    category = category or []
    offset = 0
    fingerprint = hashlib.sha256(json.dumps([q, category, limit]).encode()).hexdigest()[
        :16
    ]
    if cursor:
        try:
            offset, signature = json.loads(
                base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            )
            if (
                type(offset) is not int
                or not 0 <= offset <= 1000000
                or signature != fingerprint
            ):
                raise ValueError("invalid cursor")
        except (ValueError, TypeError, UnicodeError):
            raise HTTPException(422, "invalid cursor") from None
    page = await repo.list(q, category, limit, offset, public=True)
    items = [entry.item for entry in page.items]
    revision = page.revision
    next_cursor = (
        base64.urlsafe_b64encode(
            json.dumps([offset + len(items), fingerprint]).encode()
        )
        .decode()
        .rstrip("=")
        if offset + len(items) < page.total
        else None
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "schemaVersion": "1.0.0",
        "revision": revision,
        "items": items,
        "page": {
            "total": page.total,
            **({"nextCursor": next_cursor} if next_cursor else {}),
        },
    }


@admin_router.get("", response_model=PluginList)
async def list_plugins(
    response: Response,
    q: str = Query("", max_length=200),
    category: str = Query("", max_length=160),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """List drafts and published entries for authenticated administrators only."""
    response.headers["Cache-Control"] = "no-store"
    return await repo.list(q, category, limit, offset)


@admin_router.post("", response_model=PluginView, status_code=201)
async def create_plugin(
    payload: PluginWrite,
    admin: Annotated[UserView, Depends(require_admin)] = None,
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """Create or idempotently update a provider item ID; new entries remain drafts."""
    return (await repo.mutate(admin.userId, items=[payload]))[0]


@admin_router.post("/import", response_model=list[PluginView])
async def import_plugins(
    payload: PluginImport,
    admin: Annotated[UserView, Depends(require_admin)] = None,
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """Import a validated batch atomically, preserving existing publication decisions."""
    names = [entry.item["id"] for entry in payload.items]
    if len(names) != len(set(names)):
        raise HTTPException(422, "duplicate plugin IDs in import")
    return await repo.mutate(admin.userId, items=payload.items)


@admin_router.put("/{identifier}", response_model=PluginView)
async def edit_plugin(
    identifier: Annotated[int, ApiPath(ge=1, le=9223372036854775807)],
    payload: PluginWrite,
    admin: Annotated[UserView, Depends(require_admin)] = None,
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """Edit metadata without implicitly publishing; plugin identity is immutable."""
    try:
        return (
            await repo.mutate(admin.userId, identifier=identifier, items=[payload])
        )[0]
    except KeyError:
        raise HTTPException(404, "plugin not found") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@admin_router.patch("/{identifier}", response_model=PluginView)
async def publish_plugin(
    identifier: Annotated[int, ApiPath(ge=1, le=9223372036854775807)],
    payload: PluginPublication,
    admin: Annotated[UserView, Depends(require_admin)] = None,
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """Apply the explicit publish/unpublish switch and transactional audit record."""
    try:
        return (
            await repo.mutate(
                admin.userId, identifier=identifier, status=payload.status
            )
        )[0]
    except KeyError:
        raise HTTPException(404, "plugin not found") from None


@admin_router.delete("/{identifier}", response_model=PluginView)
async def delete_plugin(
    identifier: Annotated[int, ApiPath(ge=1, le=9223372036854775807)],
    admin: Annotated[UserView, Depends(require_admin)] = None,
    repo: Annotated[PluginCatalogRepository, Depends(repository)] = None,
):
    """Soft-delete an entry and immediately exclude it from public queries."""
    try:
        return (await repo.mutate(admin.userId, identifier=identifier, delete=True))[0]
    except KeyError:
        raise HTTPException(404, "plugin not found") from None
