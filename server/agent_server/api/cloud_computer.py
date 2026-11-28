from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from agent_server.core.cloud_computer import (
    CloudComputerResponse,
    CloudInstance,
    cloud_connector_id,
    cloud_installation_id,
)
from agent_server.core.models import UserView
from agent_server.deps import (
    current_user,
    get_cloud_computer_client,
    get_rpc,
    get_session_runtime_state_cache,
    get_store,
    get_terminal_broker,
    get_timeline_broker,
    get_timeline_write_buffer,
)
from agent_server.infra.cloud_computer import CloudComputerClient, CloudComputerError
from agent_server.infra.connector_rpc import ConnectorRpcManager
from agent_server.infra.repositories.facade import Store
from agent_server.infra.terminal_broker import TerminalBroker
from agent_server.infra.timeline_broker import TimelineBroker
from agent_server.services.connector_deletion import delete_connector_data
from agent_server.services.dashboard_events import publish_dashboard_changed
from agent_server.services.session_runtime_state_cache import SessionRuntimeStateCache
from agent_server.services.timeline_write_buffer import TimelineWriteBuffer

router = APIRouter(prefix="/cloud-computer", tags=["cloud-computer"])


def _disabled(*, configured: bool) -> CloudComputerResponse:
    return CloudComputerResponse(configured=configured, phase="disabled")


def _response(instance: CloudInstance) -> CloudComputerResponse:
    return CloudComputerResponse(
        configured=True,
        phase=instance.phase,
        containerState=instance.containerState,
        connectorId=instance.connectorId,
        displayName=instance.displayName,
        updatedAt=instance.updatedAt,
        error=instance.error,
    )


def _raise(error: CloudComputerError) -> None:
    raise HTTPException(status_code=error.status_code, detail=str(error)) from None


@router.get("", response_model=CloudComputerResponse)
async def get_cloud_computer(
    user: UserView = Depends(current_user),
    store: Store = Depends(get_store),
    client: CloudComputerClient = Depends(get_cloud_computer_client),
) -> CloudComputerResponse:
    if not client.configured:
        return _disabled(configured=False)
    try:
        instance = await client.get(client.instance_id(user.userId))
    except CloudComputerError as exc:
        _raise(exc)
    if instance is None:
        return _disabled(configured=True)
    return await _owned_instance(instance, user.userId, store)


@router.post("", response_model=CloudComputerResponse)
async def enable_cloud_computer(
    user: UserView = Depends(current_user),
    store: Store = Depends(get_store),
    client: CloudComputerClient = Depends(get_cloud_computer_client),
    broker: TimelineBroker = Depends(get_timeline_broker),
    manager: ConnectorRpcManager = Depends(get_rpc),
    terminals: TerminalBroker = Depends(get_terminal_broker),
    timeline_buffer: TimelineWriteBuffer = Depends(get_timeline_write_buffer),
    runtime_state_cache: SessionRuntimeStateCache = Depends(get_session_runtime_state_cache),
) -> CloudComputerResponse:
    if not client.configured:
        raise HTTPException(status_code=503, detail="云电脑尚未配置，请联系管理员完成部署")
    lock = await store.timeline_lock(f"cloud-computer:{user.userId}")
    async with lock:
        instance_id = client.instance_id(user.userId)
        try:
            existing = await client.get(instance_id)
            if existing is not None:
                return await _owned_instance(existing, user.userId, store)
            connector, connector_token, _ = await store.create_connector(
                name="云电脑",
                user_id=user.userId,
                connector_kind="cli",
                installation_id=cloud_installation_id(user.userId),
            )
            try:
                subject = await store.utoken_subject_for_user(
                    user_id=user.userId,
                    origin=client.settings.utoken_url,
                )
                if subject is None:
                    raise CloudComputerError("当前账号未绑定 utoken 身份", 409)
                key = await client.language_key(subject)
                instance = await client.create(
                    user_id=user.userId,
                    display_name=user.displayName or "云电脑",
                    connector_id=connector.id,
                    connector_token=connector_token,
                    yunwork_api_key=key,
                )
            except Exception:
                await _cleanup_failed_create(
                    client,
                    instance_id,
                    connector.id,
                    user.userId,
                    store,
                    manager,
                    terminals,
                    timeline_buffer,
                    runtime_state_cache,
                    broker,
                )
                raise
        except CloudComputerError as exc:
            _raise(exc)
        except KeyError:
            raise HTTPException(status_code=409, detail="云电脑 Connector 创建冲突，请重试") from None
        await publish_dashboard_changed(
            store,
            broker,
            user_id=user.userId,
            connector_id=connector.id,
            reason="connector.created",
        )
        return _response(instance)


@router.delete("", response_model=CloudComputerResponse)
async def disable_cloud_computer(
    user: UserView = Depends(current_user),
    store: Store = Depends(get_store),
    client: CloudComputerClient = Depends(get_cloud_computer_client),
    broker: TimelineBroker = Depends(get_timeline_broker),
    manager: ConnectorRpcManager = Depends(get_rpc),
    terminals: TerminalBroker = Depends(get_terminal_broker),
    timeline_buffer: TimelineWriteBuffer = Depends(get_timeline_write_buffer),
    runtime_state_cache: SessionRuntimeStateCache = Depends(get_session_runtime_state_cache),
) -> CloudComputerResponse:
    if not client.configured:
        raise HTTPException(status_code=503, detail="云电脑尚未配置，请联系管理员完成部署")
    lock = await store.timeline_lock(f"cloud-computer:{user.userId}")
    async with lock:
        try:
            await client.delete(client.instance_id(user.userId))
        except CloudComputerError as exc:
            _raise(exc)
        connector_id = cloud_connector_id(user.userId)
        try:
            connector = await store.get_connector(connector_id)
            if connector.userId != user.userId:
                raise KeyError(connector_id)
            await delete_connector_data(
                connector_id,
                user.userId,
                store,
                manager,
                terminals,
                timeline_buffer,
                runtime_state_cache,
            )
        except KeyError:
            return _disabled(configured=True)
        await publish_dashboard_changed(
            store,
            broker,
            user_id=user.userId,
            connector_id=connector_id,
            reason="connector.deleted",
        )
        return _disabled(configured=True)


async def _owned_instance(
    instance: CloudInstance, user_id: str, store: Store
) -> CloudComputerResponse:
    try:
        connector = await store.get_connector(instance.connectorId)
        if connector.userId != user_id:
            raise KeyError(instance.connectorId)
    except KeyError:
        return CloudComputerResponse(
            configured=True,
            phase="error",
            containerState=instance.containerState,
            displayName=instance.displayName,
            updatedAt=instance.updatedAt,
            error="云电脑 Connector 不可用，请联系管理员检查实例状态",
        )
    return _response(instance)


async def _cleanup_failed_create(
    client: CloudComputerClient,
    instance_id: str,
    connector_id: str,
    user_id: str,
    store: Store,
    manager: ConnectorRpcManager,
    terminals: TerminalBroker,
    timeline_buffer: TimelineWriteBuffer,
    runtime_state_cache: SessionRuntimeStateCache,
    broker: TimelineBroker,
) -> None:
    try:
        await client.delete(instance_id)
    except Exception:  # noqa: BLE001 - preserve the safe creation error
        logger.warning("cloud computer creation cleanup deferred instance_id={}", instance_id)
    try:
        await delete_connector_data(
            connector_id,
            user_id,
            store,
            manager,
            terminals,
            timeline_buffer,
            runtime_state_cache,
        )
    except KeyError:
        return
    await publish_dashboard_changed(
        store,
        broker,
        user_id=user_id,
        connector_id=connector_id,
        reason="connector.deleted",
    )
