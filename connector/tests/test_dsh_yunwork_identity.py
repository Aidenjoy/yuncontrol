from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from connector.runtime_protocol.models import RuntimeConfig
from connector.runtimes.dsh.bridge import models
from connector.runtimes.dsh.provider import DshProvider


@dataclass
class _DummyHost:
    connector_id: str = "test-connector"

    async def notify(self, event: str, payload: dict[str, Any]) -> None:
        return None


def test_dsh_yunwork_identity_matches_instance_binding(monkeypatch: Any) -> None:
    monkeypatch.setenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", "yunwork")
    monkeypatch.setenv("YUNWORK_SHORT_NAME", "云大师")

    provider = DshProvider()
    assert provider.runtime_type == "yunwork"
    assert provider.display_name == "云大师"

    config = RuntimeConfig(runtime=provider.runtime_type, revision=1, values={})
    runtime = asyncio.run(provider.create_runtime(config, _DummyHost()))
    assert runtime.identity.runtime == "yunwork"
    assert runtime.identity.display_name == "云大师"


def test_dsh_default_identity_falls_back_to_dsh(monkeypatch: Any) -> None:
    monkeypatch.delenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", raising=False)
    monkeypatch.delenv("YUNWORK_SHORT_NAME", raising=False)
    monkeypatch.delenv("YUNWORK_PRODUCT_NAME", raising=False)

    provider = DshProvider()
    assert provider.runtime_type == "dsh"
    assert provider.display_name == "DeepSeek Harness"

    config = RuntimeConfig(runtime=provider.runtime_type, revision=1, values={})
    runtime = asyncio.run(provider.create_runtime(config, _DummyHost()))
    assert runtime.identity.runtime == "dsh"
    assert runtime.identity.display_name == "DeepSeek Harness"


def test_dsh_bridge_models_use_yunwork_runtime(monkeypatch: Any) -> None:
    monkeypatch.setenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", "yunwork")

    meta = models.session_meta({
        "runtime": "dsh",
        "sessionId": "sess-1",
        "externalSessionId": "ext-1",
        "title": "测试",
        "updatedAt": "2026-11-25T00:00:00Z",
    })
    assert meta.runtime == "yunwork"

    state = models.session_state({
        "runtime": "dsh",
        "sessionId": "sess-1",
        "externalSessionId": "ext-1",
        "status": "idle",
        "updatedAt": "2026-11-25T00:00:00Z",
    })
    assert state.runtime == "yunwork"

    caps = models.capability_set({
        "runtime": "dsh",
        "revision": 1,
        "capabilities": [
            {"capabilityId": "session.send_message", "runtime": "dsh", "scope": "runtime", "supported": True, "available": True, "allowed": True}
        ],
    }, connector_id="test-connector")
    assert caps.runtime == "yunwork"
    assert caps.capabilities[0].runtime == "yunwork"

    notice = models.notice({
        "noticeId": "n-1",
        "sessionId": "sess-1",
        "runtime": "dsh",
        "kind": "info",
        "title": "hello",
        "createdAt": "2026-11-25T00:00:00Z",
    })
    assert notice.runtime == "yunwork"
