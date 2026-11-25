from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from connector.runtime_protocol.models import RuntimeConfig
from connector.runtimes.dsh.bridge import models
from connector.runtimes.dsh.bridge.client import runtime_notification, runtime_payload
from connector.runtimes.dsh.provider import DshProvider
from connector.runtimes.providers import default_runtime_providers
from connector.runtimes.yunwork.provider import YunworkProvider


@dataclass
class _DummyHost:
    connector_id: str = "test-connector"

    async def notify(self, event: str, payload: dict[str, Any]) -> None:
        return None


def test_dsh_yunwork_identity_matches_instance_binding(monkeypatch: Any) -> None:
    monkeypatch.setenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", "yunwork")
    monkeypatch.setenv("YUNWORK_SHORT_NAME", "云大师")

    assert DshProvider().runtime_type == "dsh"
    provider = YunworkProvider()
    identifiers = [item.runtime_type for item in default_runtime_providers()]
    assert len(identifiers) == len(set(identifiers))
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


@pytest.mark.parametrize("runtime", ["dsh", "yunwork"])
def test_dsh_bridge_models_keep_explicit_runtime(monkeypatch: Any, runtime: str) -> None:
    monkeypatch.setenv("YUNWORK_ANYWHERE_RUNTIME_TYPE", "yunwork")

    meta = models.session_meta({
        "runtime": runtime,
        "sessionId": "sess-1",
        "externalSessionId": "ext-1",
        "title": "测试",
        "updatedAt": "2026-11-25T00:00:00Z",
    })
    assert meta.runtime == runtime

    state = models.session_state({
        "runtime": runtime,
        "sessionId": "sess-1",
        "externalSessionId": "ext-1",
        "status": "idle",
        "updatedAt": "2026-11-25T00:00:00Z",
    })
    assert state.runtime == runtime

    caps = models.capability_set({
        "runtime": runtime,
        "revision": 1,
        "capabilities": [
            {"capabilityId": "session.send_message", "runtime": runtime, "scope": "runtime", "supported": True, "available": True, "allowed": True}
        ],
    }, connector_id="test-connector")
    assert caps.runtime == runtime
    assert caps.capabilities[0].runtime == runtime

    notice = models.notice({
        "noticeId": "n-1",
        "sessionId": "sess-1",
        "runtime": runtime,
        "kind": "info",
        "title": "hello",
        "createdAt": "2026-11-25T00:00:00Z",
    })
    assert notice.runtime == runtime


@pytest.mark.parametrize("method,key", [
    ("initialize", "identity"), ("listSessions", "sessions"),
    ("getSessionSnapshot", "items"), ("getSessionNotices", "notices"),
    ("getRuntimeCapabilities", "capabilities"), ("getSessionCapabilities", "capabilities"),
])
def test_protocol_children_are_converted_but_business_fields_are_opaque(method, key):
    business = {"runtime": "dsh", "nested": [{"runtime": "dsh"}], "identity": {"runtime": "dsh"}}
    record = {"runtime": "dsh", "metadata": business, "content": business, "arguments": business}
    value = {key: record if key == "identity" else [record], "metadata": business}
    converted = runtime_payload(value, "yunwork", method=method)
    child = converted[key] if key == "identity" else converted[key][0]
    assert child["runtime"] == "yunwork"
    for field in ("metadata", "content", "arguments"):
        assert child[field] is business
        assert child[field]["runtime"] == "dsh"
    assert converted["metadata"] is business
    assert record["runtime"] == "dsh", "conversion must not modify the source record"
    assert runtime_payload(value, "dsh", method=method) is value


def test_notifications_and_command_results_do_not_rewrite_business_runtime():
    business = {"runtime": "dsh", "items": [{"runtime": "dsh"}]}
    notice = {"method": "timeline.itemUpsert", "params": {
        "sessionId": "s", "item": {"runtime": "dsh", "content": business, "metadata": business, "source": {"runtime": "dsh", "metadata": business}}}}
    result = runtime_notification(notice, "yunwork")
    assert result["params"]["item"]["runtime"] == "yunwork"
    assert result["params"]["item"]["content"] is business
    assert result["params"]["item"]["metadata"] is business
    assert result["params"]["item"]["source"]["runtime"] == "yunwork"
    assert result["params"]["item"]["source"]["metadata"] is business
    command = {"ok": True, "result": business}
    assert runtime_payload(command, "yunwork", method="executeCommand")["result"] is business
    model = {"runtime": "dsh", "models": [{"id": "dsh", "metadata": business}]}
    converted = runtime_payload(model, "yunwork", method="listModels")
    assert converted["runtime"] == "yunwork"
    assert converted["models"] is model["models"]
