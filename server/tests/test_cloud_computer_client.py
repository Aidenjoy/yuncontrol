from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from agent_server.infra.cloud_computer import (
    CloudComputerClient,
    CloudComputerError,
    CloudComputerSettings,
)

CLOUD_SECRET = "test-cloud-secret-0123456789abcdef"
KEY_SECRET = "test-key-secret-0123456789abcdef"


def _settings() -> CloudComputerSettings:
    return CloudComputerSettings(
        cloud_url="https://cloud.test",
        cloud_secret=CLOUD_SECRET,
        utoken_url="https://utoken.test",
        key_secret=KEY_SECRET,
        public_origin="https://agents.test",
    )


def test_cloud_computer_client_uses_private_credentials_and_filters_response():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/yuncontrol/cloud-key":
            return httpx.Response(200, json={"language_api_key": "sk-test-language-key"})
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "missing"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"instanceId": "user-0123456789abcdef01234567", "phase": "disabled"})
        return httpx.Response(200, json={
            "instanceId": "user-0123456789abcdef01234567",
            "connectorId": "conn_test",
            "displayName": "云电脑",
            "phase": "running",
            "containerState": "running",
            "updatedAt": "2026-01-01T00:00:00Z",
            "error": None,
            "yunworkApiKey": "must-not-be-returned",
            "connectorToken": "must-not-be-returned",
        })

    client = CloudComputerClient(_settings(), transport=httpx.MockTransport(handler))

    async def scenario():
        assert await client.get("user-0123456789abcdef01234567") is None
        key = await client.language_key("42")
        assert key == "sk-test-language-key"
        instance = await client.create(
            user_id="ut-test",
            display_name="测试用户",
            connector_id="conn_test",
            connector_token="cxt-test-connector-token",
            yunwork_api_key=key,
        )
        await client.delete("user-0123456789abcdef01234567")
        return instance

    instance = asyncio.run(scenario())
    assert not hasattr(instance, "yunworkApiKey")
    assert not hasattr(instance, "connectorToken")
    key_request = next(request for request in requests if request.url.path == "/api/yuncontrol/cloud-key")
    assert key_request.headers["X-Cloud-Key-Secret"] == KEY_SECRET
    assert json.loads(key_request.content) == {"user_id": 42}
    create_request = next(request for request in requests if request.method == "POST" and request.url.path == "/v1/instances")
    assert create_request.headers["Authorization"] == f"Bearer {CLOUD_SECRET}"
    body = json.loads(create_request.content)
    assert body["serverUrl"] == "https://agents.test"
    assert body["apiBaseUrl"] == body["authBaseUrl"] == "https://utoken.test"
    assert body["yunworkApiKey"] == "sk-test-language-key"


def test_cloud_computer_client_does_not_echo_upstream_error_secrets():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "sk-upstream-secret-must-not-leak"})

    client = CloudComputerClient(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(CloudComputerError) as captured:
        asyncio.run(client.get("user-0123456789abcdef01234567"))
    assert "sk-upstream" not in str(captured.value)


def test_cloud_computer_settings_require_complete_safe_configuration(monkeypatch):
    monkeypatch.setenv("AGENT_SERVER_YUNWORK_CLOUD_URL", "https://cloud.test")
    monkeypatch.setenv("AGENT_SERVER_YUNWORK_CLOUD_SECRET", CLOUD_SECRET)
    monkeypatch.setenv("AGENT_SERVER_UTOKEN_URL", "https://utoken.test")
    monkeypatch.setenv("AGENT_SERVER_UTOKEN_CLOUD_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("AGENT_SERVER_PUBLIC_ORIGIN", "https://agents.test")
    assert CloudComputerSettings.from_environment() == _settings()

    monkeypatch.setenv("AGENT_SERVER_PUBLIC_ORIGIN", "https://user@agents.test/path")
    with pytest.raises(CloudComputerError):
        CloudComputerSettings.from_environment()
    monkeypatch.delenv("AGENT_SERVER_UTOKEN_CLOUD_KEY_SECRET")
    assert CloudComputerSettings.from_environment() is None
