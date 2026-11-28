from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from yunwork_cloud.config import Settings
from yunwork_cloud.docker import Docker, DockerError
from yunwork_cloud.identity import instance_id_for, valid_instance_id


class CloudError(RuntimeError):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class InstanceCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(alias="userId", min_length=1, max_length=256)
    display_name: str = Field(alias="displayName", default="云电脑", max_length=80)
    server_url: str = Field(alias="serverUrl", max_length=2048)
    connector_id: str = Field(alias="connectorId", min_length=1, max_length=256)
    connector_token: SecretStr = Field(alias="connectorToken", min_length=20, max_length=4096)
    yunwork_api_key: SecretStr = Field(alias="yunworkApiKey", min_length=10, max_length=4096)
    api_base_url: str = Field(alias="apiBaseUrl", max_length=2048)
    auth_base_url: str = Field(alias="authBaseUrl", max_length=2048)

    @field_validator("server_url", "api_base_url", "auth_base_url")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("must be an HTTP(S) origin without credentials, path, query or fragment")
        return value.rstrip("/")

    @field_validator("user_id", "display_name", "connector_id")
    @classmethod
    def reject_newlines(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("must not contain newlines")
        return value


@dataclass
class InstanceRecord:
    instanceId: str
    userId: str
    displayName: str
    connectorId: str
    phase: str
    createdAt: str
    updatedAt: str
    containerState: str = "missing"
    error: str | None = None

    def public(self) -> dict[str, str | None]:
        value = asdict(self)
        value.pop("userId", None)
        return value


class InstanceManager:
    def __init__(self, settings: Settings, docker: Docker | None = None):
        self.settings = settings
        self.docker = docker or Docker(settings)
        self.locks: dict[str, asyncio.Lock] = {}
        self.settings.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _root(self, instance_id: str) -> Path:
        if not valid_instance_id(instance_id):
            raise CloudError("无效的云电脑实例标识", 400)
        root = self.settings.data_root / instance_id
        if root.parent != self.settings.data_root or root.is_symlink():
            raise CloudError("云电脑目录不安全", 400)
        return root

    @staticmethod
    def _container(instance_id: str) -> str:
        return f"yunwork-{instance_id}"

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save(self, root: Path, record: InstanceRecord) -> None:
        record.updatedAt = self._now()
        self._atomic_write(root / "instance.json", json.dumps(asdict(record), ensure_ascii=False, indent=2))

    @staticmethod
    def _load(root: Path, instance_id: str) -> InstanceRecord | None:
        path = root / "instance.json"
        if not path.is_file():
            return None
        try:
            record = InstanceRecord(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise CloudError("云电脑实例状态损坏，请由管理员检查该实例目录") from exc
        if record.instanceId != instance_id:
            raise CloudError("云电脑实例状态不匹配")
        return record

    def _write_environment(self, root: Path, request: InstanceCreateRequest) -> None:
        insecure = request.api_base_url.startswith("http://") or request.auth_base_url.startswith("http://")
        values = {
            "AGENT_SERVER_URL": request.server_url,
            "AGENT_CONNECTOR_ID": request.connector_id,
            "AGENT_CONNECTOR_TOKEN": request.connector_token.get_secret_value(),
            "YUNWORK_API_BASE_URL": request.api_base_url,
            "YUNWORK_AUTH_BASE_URL": request.auth_base_url,
            "YUNWORK_INSECURE": "true" if insecure else "false",
            "YUNWORK_API_KEY": request.yunwork_api_key.get_secret_value(),
            "YUNWORK_ANYWHERE_SERVER_URL": request.server_url,
            "YUNWORK_ANYWHERE_WEB_URL": request.server_url,
            "YUNWORK_ENV": "prod",
        }
        if any("\n" in value or "\r" in value for value in values.values()):
            raise CloudError("实例环境变量不能包含换行", 422)
        content = "".join(f"{name}={value}\n" for name, value in values.items())
        self._atomic_write(root / "container.env", content)

    async def create(self, request: InstanceCreateRequest) -> dict[str, str | None]:
        instance_id = instance_id_for(request.user_id, self.settings.control_secret)
        lock = self.locks.setdefault(instance_id, asyncio.Lock())
        async with lock:
            root = self._root(instance_id)
            container = self._container(instance_id)
            existing = self._load(root, instance_id)
            state = await self.docker.require_absent_or_owned(container, instance_id)
            if existing and existing.connectorId == request.connector_id and state.running:
                return existing.public()
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            root.chmod(0o700)
            data_dir = root / "data"
            data_dir.mkdir(exist_ok=True, mode=0o755)
            if state.exists:
                await self.docker.remove(container=container, instance_id=instance_id)
            now = self._now()
            record = InstanceRecord(
                instanceId=instance_id,
                userId=request.user_id,
                displayName=request.display_name or "云电脑",
                connectorId=request.connector_id,
                phase="provisioning",
                createdAt=existing.createdAt if existing else now,
                updatedAt=now,
            )
            self._write_environment(root, request)
            self._save(root, record)
            try:
                await self.docker.run(
                    instance_id=instance_id,
                    container=container,
                    env_file=root / "container.env",
                    data_dir=data_dir,
                )
            except DockerError as exc:
                record.phase = "error"
                record.error = "云电脑容器启动失败，请检查云主机镜像与 Docker 状态"
                self._save(root, record)
                raise CloudError(record.error) from exc
            return await self._inspect_record(root, record)

    async def _inspect_record(self, root: Path, record: InstanceRecord) -> dict[str, str | None]:
        state = await self.docker.require_absent_or_owned(self._container(record.instanceId), record.instanceId)
        record.containerState = state.status
        if state.running:
            record.phase = "running"
            record.error = None
        elif not state.exists:
            record.phase = "error"
            record.error = "云电脑容器不存在，请重新开启"
        elif state.status in {"exited", "dead"}:
            record.phase = "error"
            record.error = "云电脑容器已退出，请检查云主机日志后重试"
        else:
            record.phase = "provisioning"
        self._save(root, record)
        return record.public()

    async def get(self, instance_id: str) -> dict[str, str | None]:
        lock = self.locks.setdefault(instance_id, asyncio.Lock())
        async with lock:
            root = self._root(instance_id)
            record = self._load(root, instance_id)
            if record is None:
                raise CloudError("云电脑尚未开启", 404)
            return await self._inspect_record(root, record)

    async def delete(self, instance_id: str) -> dict[str, str]:
        lock = self.locks.setdefault(instance_id, asyncio.Lock())
        async with lock:
            root = self._root(instance_id)
            await self.docker.remove(container=self._container(instance_id), instance_id=instance_id)
            if root.exists():
                if root.parent != self.settings.data_root or root.is_symlink():
                    raise CloudError("拒绝删除不安全的云电脑目录", 400)
                trash = self.settings.data_root / f".deleting-{instance_id}-{uuid.uuid4().hex}"
                os.replace(root, trash)
                await asyncio.to_thread(shutil.rmtree, trash)
            return {"instanceId": instance_id, "phase": "disabled"}
