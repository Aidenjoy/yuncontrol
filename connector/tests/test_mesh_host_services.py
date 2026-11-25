from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from connector.mesh.host import mount_host_services
from connector.runtimes.dsh import provider_config
from connector.runtimes.dsh.bridge import host as bridge_host_module
from connector.runtimes.dsh.bridge.host import BridgeHost, SyncService, host_for


class RecordingHub:
    """Mounts like ``LocalHub``: services are registered first, then served."""

    def __init__(self, *, serving: bool = False) -> None:
        self.serving = serving
        self.instance_id = "test-instance"
        self.mounts: list[tuple[object, ...]] = []
        self.services: list[object] = []
        # "register": registering fails; "serve": registered, but serving fails.
        self.fail: str | None = None
        self.on_mount: Callable[[], None] | None = None

    async def mount(self, *services: object) -> None:
        if self.on_mount is not None:
            self.on_mount()
        self.mounts.append(services)
        if self.fail == "register":
            raise RuntimeError("router unavailable")
        self.services.extend(services)
        if self.fail == "serve":
            self.serving = False
            raise RuntimeError("serving failed")
        self.serving = True

    def has_service(self, service: object) -> bool:
        return any(mounted is service for mounted in self.services)

    def on_stop(self, _cleanup: Callable[[], Awaitable[None]]) -> None:
        pass

    def descriptor(self, _role: str) -> dict[str, Any]:
        return {
            "instanceId": self.instance_id,
            "pid": 1,
            "endpoint": {"pipe": "test-pipe"},
            "key": "test-key",
        }


@pytest.fixture
def rendezvous(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "connector.json"
    monkeypatch.setattr(provider_config, "endpoint_path", lambda: path)
    monkeypatch.setattr(bridge_host_module, "_hosts", {})
    async def no_yunwork_for_recording_hub(_hub):
        return None
    monkeypatch.setattr(bridge_host_module, "start_yunwork_bridge", no_yunwork_for_recording_hub)
    return path


def test_dsh_sync_is_mounted_with_control_and_logs_in_one_go(rendezvous: Path) -> None:
    hub = RecordingHub()
    # The plugin must not find the rendezvous before the services are served.
    hub.on_mount = lambda: assert_absent(rendezvous)

    asyncio.run(mount_host_services(hub, "control", "logs"))  # type: ignore[arg-type]

    assert len(hub.mounts) == 1
    sync, *rest = hub.mounts[0]
    assert isinstance(sync, SyncService)
    assert rest == ["control", "logs"]
    assert rendezvous.exists()


def test_enabling_dsh_later_reuses_the_mounted_bridge(rendezvous: Path) -> None:
    hub = RecordingHub()

    async def scenario() -> None:
        await mount_host_services(hub, "control")  # type: ignore[arg-type]
        rendezvous.unlink()
        # What a probe or the DSH runtime does once the user turns DSH on.
        await host_for(hub).start()  # type: ignore[arg-type]

    asyncio.run(scenario())
    assert len(hub.mounts) == 1, "turning DSH on must not restart serving"
    assert rendezvous.exists()


def test_a_mount_whose_serving_failed_still_counts_the_bridge_as_mounted(rendezvous: Path) -> None:
    # The hub's supervisor serves registered services once the Router recovers;
    # DSH must use them then instead of refusing to start for good.
    hub = RecordingHub()
    hub.fail = "serve"

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="serving failed"):
            await mount_host_services(hub, "control")  # type: ignore[arg-type]
        hub.fail = None
        hub.serving = True
        await host_for(hub).start()  # type: ignore[arg-type]

    asyncio.run(scenario())
    assert len(hub.mounts) == 1
    assert rendezvous.exists()


def test_a_mount_that_registered_nothing_lets_dsh_mount_later(rendezvous: Path) -> None:
    hub = RecordingHub()
    hub.fail = "register"

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="router unavailable"):
            await mount_host_services(hub, "logs")  # type: ignore[arg-type]
        assert not hub.serving
        hub.fail = None
        await host_for(hub).start()  # type: ignore[arg-type]

    asyncio.run(scenario())
    assert len(hub.mounts) == 2
    assert isinstance(hub.mounts[1][0], SyncService)
    assert rendezvous.exists()


def test_bridge_host_refuses_to_mount_after_serving_starts(rendezvous: Path) -> None:
    hub = RecordingHub(serving=True)
    host = BridgeHost(hub)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="before the local router starts serving"):
        asyncio.run(host.start())

    assert hub.mounts == []
    assert not rendezvous.exists()


def test_bridge_host_does_not_mount_twice(rendezvous: Path) -> None:
    hub = RecordingHub()
    host = BridgeHost(hub)  # type: ignore[arg-type]

    async def scenario() -> None:
        await host.start()
        await host.start()

    asyncio.run(scenario())
    assert len(hub.mounts) == 1


def assert_absent(path: Path) -> None:
    assert not path.exists()


@pytest.mark.parametrize("branded_home", [False, True])
def test_first_start_publishes_both_isolated_bridges_without_runtime_probe(tmp_path, monkeypatch, branded_home):
    """Both fresh-install rendezvous files exist before any runtime is configured."""
    from connector.mesh.hub import LocalHub
    monkeypatch.setattr(bridge_host_module, "_hosts", {})
    monkeypatch.setattr(bridge_host_module, "_yunwork_hosts", {})
    if branded_home:
        monkeypatch.setenv("DSH_HOME", str(tmp_path / "work-home"))
    else:
        monkeypatch.delenv("DSH_HOME", raising=False)
    monkeypatch.setenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", "yunwork")
    dsh_path = provider_config.endpoint_path()
    work_path = provider_config.endpoint_path("yunwork")
    assert dsh_path != work_path

    async def scenario():
        hub = LocalHub(directory=tmp_path / "router")
        try:
            await hub.start()
            await mount_host_services(hub)
            assert dsh_path.exists() and work_path.exists()
            dsh = bridge_host_module.read_rendezvous(dsh_path)
            work = bridge_host_module.read_rendezvous(work_path)
            assert dsh["instanceId"] != work["instanceId"]
            assert dsh["key"] != work["key"]
            assert dsh["endpoint"] != work["endpoint"]
            parent_server = hub._server
            child = await bridge_host_module.start_yunwork_bridge(hub)
            assert child.hub is not hub
            assert hub._server is parent_server, "starting YunWork must not remount DSH/Control"
            assert (await bridge_host_module.start_yunwork_bridge(hub)) is child
        finally:
            await hub.stop()
        assert not dsh_path.exists() and not work_path.exists()

    asyncio.run(scenario())


def test_yunwork_start_failure_does_not_disable_dsh_or_control(rendezvous, monkeypatch):
    """An optional independent Router failure leaves the original served services intact."""
    async def fail(_hub):
        raise RuntimeError("fixture YunWork startup failure")
    monkeypatch.setenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", "yunwork")
    monkeypatch.setattr(bridge_host_module, "start_yunwork_bridge", fail)
    hub = RecordingHub()
    asyncio.run(mount_host_services(hub, "control", "logs"))
    assert len(hub.mounts) == 1
    assert hub.mounts[0][1:] == ("control", "logs")
    assert rendezvous.exists()


def test_plain_dsh_start_does_not_take_over_yunwork_rendezvous(rendezvous, monkeypatch):
    """Only the selected branded launcher eagerly starts its separate Router."""
    from unittest.mock import AsyncMock
    monkeypatch.delenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", raising=False)
    start = AsyncMock()
    monkeypatch.setattr(bridge_host_module, "start_yunwork_bridge", start)
    hub = RecordingHub()
    asyncio.run(mount_host_services(hub, "control", "logs"))
    start.assert_not_awaited()
    assert rendezvous.exists()
    assert len(hub.mounts) == 1
