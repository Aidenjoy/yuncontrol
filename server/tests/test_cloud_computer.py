from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

from agent_server.core.cloud_computer import CloudInstance, cloud_instance_id
from agent_server.infra.cloud_computer import CloudComputerError
from conftest import make_test_client
from test_auth import admin_token, bearer, register, user_id

ORIGIN = "https://utoken.test"
CLOUD_SECRET = "test-cloud-secret-0123456789abcdef"


class FakeCloudComputerClient:
    configured = True

    def __init__(self) -> None:
        self.settings = SimpleNamespace(utoken_url=ORIGIN)
        self.instances: dict[str, CloudInstance] = {}
        self.create_requests: list[dict] = []
        self.key_subjects: list[str] = []
        self.deleted: list[str] = []
        self.fail_create = False

    def instance_id(self, user_id: str) -> str:
        return cloud_instance_id(user_id, CLOUD_SECRET)

    async def get(self, instance_id: str) -> CloudInstance | None:
        return self.instances.get(instance_id)

    async def create(self, **payload) -> CloudInstance:
        self.create_requests.append(payload)
        if self.fail_create:
            raise CloudComputerError("云主机暂时不可用")
        instance_id = self.instance_id(payload["user_id"])
        instance = CloudInstance(
            instanceId=instance_id,
            connectorId=payload["connector_id"],
            displayName=payload["display_name"],
            phase="provisioning",
            containerState="created",
            updatedAt="2026-01-01T00:00:00Z",
        )
        self.instances[instance_id] = instance
        return instance

    async def delete(self, instance_id: str) -> None:
        self.deleted.append(instance_id)
        self.instances.pop(instance_id, None)

    async def language_key(self, subject: str) -> str:
        self.key_subjects.append(subject)
        return f"sk-test-key-for-user-{subject}"


def _bind_utoken(client, local_user_id: str, subject: str) -> None:
    provider = "utoken:" + hashlib.sha256(ORIGIN.encode()).hexdigest()
    asyncio.run(
        client.app.state.store.bind_oauth_account(
            user_id=local_user_id,
            provider=provider,
            subject=subject,
        )
    )


def _enable(client, token: str):
    return client.post("/api/v2/cloud-computer", headers=bearer(token))


def test_cloud_computer_reports_unconfigured_without_secrets(tmp_path, monkeypatch):
    for name in (
        "AGENT_SERVER_YUNWORK_CLOUD_URL",
        "AGENT_SERVER_YUNWORK_CLOUD_SECRET",
        "AGENT_SERVER_UTOKEN_CLOUD_KEY_SECRET",
        "AGENT_SERVER_UTOKEN_URL",
        "AGENT_SERVER_PUBLIC_ORIGIN",
    ):
        monkeypatch.delenv(name, raising=False)
    client = make_test_client()
    token = admin_token(client)

    status = client.get("/api/v2/cloud-computer", headers=bearer(token))
    assert status.status_code == 200, status.text
    assert status.json() == {
        "configured": False,
        "phase": "disabled",
        "containerState": "missing",
        "connectorId": None,
        "displayName": "云电脑",
        "updatedAt": None,
        "error": None,
    }
    assert _enable(client, token).status_code == 503
    assert client.get("/api/v2/cloud-computer").status_code == 401


def test_cloud_computer_isolates_users_and_reuses_connector(tmp_path):
    client = make_test_client()
    first_token = admin_token(client)
    client.patch("/admin/settings", headers=bearer(first_token), json={"registrationOpen": True})
    second_token = register(client, "user2").json()["accessToken"]
    first_id, second_id = user_id(client, "user1"), user_id(client, "user2")
    _bind_utoken(client, first_id, "101")
    _bind_utoken(client, second_id, "202")
    cloud = FakeCloudComputerClient()
    client.app.state.cloud_computer_client = cloud

    first = _enable(client, first_token)
    second = _enable(client, second_token)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["phase"] == second.json()["phase"] == "provisioning"
    assert first.json()["connectorId"] != second.json()["connectorId"]
    assert cloud.key_subjects == ["101", "202"]
    assert [request["user_id"] for request in cloud.create_requests] == [first_id, second_id]
    for response in (first, second):
        assert "connectorToken" not in response.text
        assert "yunworkApiKey" not in response.text
        assert "sk-test-key" not in response.text
        assert cloud.create_requests[0]["connector_token"] not in response.text

    repeated = _enable(client, first_token)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["connectorId"] == first.json()["connectorId"]
    assert len(cloud.create_requests) == 2
    assert cloud.key_subjects == ["101", "202"]
    first_connectors = client.get("/connectors", headers=bearer(first_token)).json()["connectors"]
    second_connectors = client.get("/connectors", headers=bearer(second_token)).json()["connectors"]
    assert len(first_connectors) == len(second_connectors) == 1
    assert first_connectors[0]["name"] == second_connectors[0]["name"] == "云电脑"
    assert first_connectors[0]["id"] != second_connectors[0]["id"]


def test_cloud_computer_cleans_up_failed_creation_and_recovers(tmp_path):
    client = make_test_client()
    token = admin_token(client)
    local_user_id = user_id(client, "user1")
    _bind_utoken(client, local_user_id, "303")
    cloud = FakeCloudComputerClient()
    cloud.fail_create = True
    client.app.state.cloud_computer_client = cloud

    failed = _enable(client, token)
    assert failed.status_code == 502, failed.text
    assert "sk-test-key" not in failed.text
    assert cloud.deleted == [cloud.instance_id(local_user_id)]
    assert client.get("/connectors", headers=bearer(token)).json()["connectors"] == []

    cloud.fail_create = False
    recovered = _enable(client, token)
    assert recovered.status_code == 200, recovered.text
    connectors = client.get("/connectors", headers=bearer(token)).json()["connectors"]
    assert len(connectors) == 1
    assert recovered.json()["connectorId"] == connectors[0]["id"]


def test_cloud_computer_disable_deletes_instance_and_owned_connector(tmp_path):
    client = make_test_client()
    token = admin_token(client)
    local_user_id = user_id(client, "user1")
    _bind_utoken(client, local_user_id, "404")
    cloud = FakeCloudComputerClient()
    client.app.state.cloud_computer_client = cloud
    assert _enable(client, token).status_code == 200

    disabled = client.delete("/api/v2/cloud-computer", headers=bearer(token))
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["phase"] == "disabled"
    assert cloud.deleted == [cloud.instance_id(local_user_id)]
    assert client.get("/connectors", headers=bearer(token)).json()["connectors"] == []

    repeated = client.delete("/api/v2/cloud-computer", headers=bearer(token))
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["phase"] == "disabled"
    assert cloud.deleted == [cloud.instance_id(local_user_id)] * 2


def test_cloud_computer_does_not_trust_another_users_connector(tmp_path):
    client = make_test_client()
    first_token = admin_token(client)
    client.patch("/admin/settings", headers=bearer(first_token), json={"registrationOpen": True})
    second_token = register(client, "user2").json()["accessToken"]
    first_id, second_id = user_id(client, "user1"), user_id(client, "user2")
    _bind_utoken(client, first_id, "505")
    _bind_utoken(client, second_id, "606")
    cloud = FakeCloudComputerClient()
    client.app.state.cloud_computer_client = cloud
    assert _enable(client, first_token).status_code == 200
    second = _enable(client, second_token).json()

    cloud.instances[cloud.instance_id(first_id)].connectorId = second["connectorId"]
    status = client.get("/api/v2/cloud-computer", headers=bearer(first_token))
    assert status.status_code == 200, status.text
    assert status.json()["phase"] == "error"
    assert status.json()["connectorId"] is None
    assert second["connectorId"] not in status.text
