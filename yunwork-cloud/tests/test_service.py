import asyncio
import json
from pathlib import Path

from yunwork_cloud.config import Settings
from yunwork_cloud.docker import ContainerState
from yunwork_cloud.identity import instance_id_for
from yunwork_cloud.service import InstanceCreateRequest, InstanceManager

SECRET = "controller-secret-with-at-least-32-characters"


class FakeDocker:
    def __init__(self):
        self.containers = {}
        self.calls = []

    async def require_absent_or_owned(self, container, instance_id):
        state = self.containers.get(container, ContainerState(exists=False, owned=False))
        if state.exists and not state.owned:
            raise RuntimeError("unowned container")
        return state

    async def run(self, *, instance_id, container, env_file, data_dir):
        self.calls.append(("run", container, env_file, data_dir))
        self.containers[container] = ContainerState(exists=True, owned=True, running=True, status="running")

    async def remove(self, *, container, instance_id):
        self.calls.append(("remove", container))
        self.containers.pop(container, None)


def settings(tmp_path: Path) -> Settings:
    return Settings(control_secret=SECRET, data_root=tmp_path / "users")


def request(user_id: str, connector_id: str = "connector-1") -> InstanceCreateRequest:
    return InstanceCreateRequest(
        userId=user_id,
        displayName="中文用户 / 管理员",
        serverUrl="https://agent.example.test",
        connectorId=connector_id,
        connectorToken="connector-token-that-is-long-enough",
        yunworkApiKey="sk-test-secret-key",
        apiBaseUrl="https://token.example.test",
        authBaseUrl="https://token.example.test",
    )


def test_create_is_idempotent_and_separates_users(tmp_path):
    async def scenario():
        docker = FakeDocker()
        manager = InstanceManager(settings(tmp_path), docker)
        first = await manager.create(request("user-one/中文"))
        second = await manager.create(request("user-two"))
        assert first["instanceId"] != second["instanceId"]
        assert first["phase"] == "running"
        assert "yunworkApiKey" not in json.dumps(first)
        assert "userId" not in first
        assert len([call for call in docker.calls if call[0] == "run"]) == 2
        await manager.create(request("user-one/中文"))
        assert len([call for call in docker.calls if call[0] == "run"]) == 2
        first_root = tmp_path / "users" / first["instanceId"]
        second_root = tmp_path / "users" / second["instanceId"]
        assert first_root != second_root
        assert (first_root / "container.env").stat().st_mode & 0o777 == 0o600
        assert docker.calls[0][3] == first_root / "data"
        assert docker.calls[1][3] == second_root / "data"

    asyncio.run(scenario())


def test_delete_removes_only_the_requested_instance(tmp_path):
    async def scenario():
        docker = FakeDocker()
        manager = InstanceManager(settings(tmp_path), docker)
        first = await manager.create(request("user-one"))
        second = await manager.create(request("user-two"))
        result = await manager.delete(first["instanceId"])
        assert result["phase"] == "disabled"
        assert not (tmp_path / "users" / first["instanceId"]).exists()
        assert (tmp_path / "users" / second["instanceId"] / "instance.json").is_file()
        assert (await manager.get(second["instanceId"]))["phase"] == "running"
        assert (await manager.delete(first["instanceId"]))["phase"] == "disabled"

    asyncio.run(scenario())


def test_restart_recovers_state_from_metadata_and_docker(tmp_path):
    async def scenario():
        docker = FakeDocker()
        first_manager = InstanceManager(settings(tmp_path), docker)
        created = await first_manager.create(request("stable-user"))
        restarted_manager = InstanceManager(settings(tmp_path), docker)
        recovered = await restarted_manager.get(created["instanceId"])
        assert recovered["connectorId"] == "connector-1"
        assert recovered["phase"] == "running"
        assert recovered["instanceId"] == instance_id_for("stable-user", SECRET)

    asyncio.run(scenario())
