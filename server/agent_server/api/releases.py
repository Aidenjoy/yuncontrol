"""Administrator release registry and the public version check."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from agent_server.core.models import UserView
from agent_server.core.release_files import (
    Platform,
    PublicReleaseList,
    ReleaseCheck,
    ReleaseList,
    ReleaseView,
    ReleaseWrite,
    compare_versions,
)
from agent_server.deps import get_store, require_admin
from agent_server.infra.repositories.facade import Store
from agent_server.infra.repositories.release_files import (
    DuplicateReleaseError,
    ReleaseFileRepository,
    ReleaseNotFoundError,
)

router = APIRouter(prefix="/releases", tags=["releases"])
admin_router = APIRouter(
    prefix="/admin/releases", tags=["admin"], dependencies=[Depends(require_admin)]
)


def repository(store: Annotated[Store, Depends(get_store)]) -> ReleaseFileRepository:
    """Reuse the server database; release files themselves stay wherever they are hosted."""
    return ReleaseFileRepository(store._engine)


RepoDep = Annotated[ReleaseFileRepository, Depends(repository)]
AdminDep = Annotated[UserView, Depends(require_admin)]


def _duplicate_detail(exc: DuplicateReleaseError) -> str:
    """Explain which build already occupies the platform."""
    if exc.version:
        return f"{exc.platform} already has {exc.version}; edit that record instead"
    return f"{exc.platform} already has a release; edit that record instead"


@router.get("/lates", response_model=PublicReleaseList)
@router.get("/latest", response_model=PublicReleaseList)
async def latest_releases(
    response: Response,
    repo: RepoDep,
    platform: Annotated[Platform | None, Query()] = None,
    release_type: Annotated[Platform | None, Query(alias="type")] = None,
) -> PublicReleaseList:
    """Return published version/download metadata, accepting type or the existing platform parameter."""
    response.headers["Cache-Control"] = "no-store"
    if platform is not None and release_type is not None and platform != release_type:
        raise HTTPException(422, "type and platform must identify the same platform")
    selected = release_type or platform
    if selected is not None:
        item = await repo.latest(selected)
        return PublicReleaseList(items=[item] if item is not None else [])
    return PublicReleaseList(items=await repo.latest_all())


@router.get("/check", response_model=ReleaseCheck)
async def check_release(
    response: Response,
    repo: RepoDep,
    platform: Annotated[Platform, Query()],
    current_version: Annotated[str, Query(alias="currentVersion", max_length=64)] = "",
) -> ReleaseCheck:
    """Tell one client whether a newer build exists and where to download it."""
    response.headers["Cache-Control"] = "no-store"
    latest = await repo.latest(platform)
    available = True
    if latest is not None and current_version.strip():
        try:
            available = compare_versions(latest.version, current_version) > 0
        except ValueError:
            raise HTTPException(
                400, "currentVersion must look like 1.2.3 or 1.2.3-beta.1"
            ) from None
    return ReleaseCheck(
        platform=platform,
        currentVersion=current_version.strip(),
        latestVersion=latest.version if latest else None,
        updateAvailable=available if latest else False,
        downloadUrl=latest.downloadUrl if latest else None,
        fileName=latest.fileName if latest else "",
        notes=latest.notes if latest else "",
        publishedAt=latest.publishedAt if latest else None,
    )


@admin_router.get("", response_model=ReleaseList)
async def list_releases(
    repo: RepoDep,
    platform: Annotated[Platform | None, Query()] = None,
    q: Annotated[str, Query(max_length=160)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReleaseList:
    """List drafts and published records for the administration table."""
    items, total = await repo.list(platform=platform, q=q, limit=limit, offset=offset)
    return ReleaseList(items=items, total=total)


@admin_router.post("", response_model=ReleaseView, status_code=201)
async def create_release(
    payload: ReleaseWrite, repo: RepoDep, admin: AdminDep
) -> ReleaseView:
    """Register a new build; publishing stays an explicit field."""
    try:
        return await repo.create(payload, admin.userId)
    except DuplicateReleaseError as exc:
        raise HTTPException(409, _duplicate_detail(exc)) from exc


@admin_router.put("/{release_id}", response_model=ReleaseView)
async def update_release(
    release_id: int, payload: ReleaseWrite, repo: RepoDep, admin: AdminDep
) -> ReleaseView:
    """Replace a record so a corrected URL or version takes effect immediately."""
    try:
        return await repo.update(release_id, payload, admin.userId)
    except ReleaseNotFoundError as exc:
        raise HTTPException(404, "release not found") from exc
    except DuplicateReleaseError as exc:
        raise HTTPException(409, _duplicate_detail(exc)) from exc


@admin_router.delete("/{release_id}", status_code=204)
async def delete_release(release_id: int, repo: RepoDep, admin: AdminDep) -> Response:
    """Soft-delete a record so the same version can be registered again."""
    try:
        await repo.delete(release_id, admin.userId)
    except ReleaseNotFoundError as exc:
        raise HTTPException(404, "release not found") from exc
    return Response(status_code=204)
