from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from agent_server.core.cloud_computer import CloudInstance, cloud_instance_id


class CloudComputerError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CloudComputerSettings:
    cloud_url: str
    cloud_secret: str
    utoken_url: str
    key_secret: str
    public_origin: str

    @classmethod
    def from_environment(cls) -> CloudComputerSettings | None:
        values = {
            "cloud_url": os.environ.get("AGENT_SERVER_YUNWORK_CLOUD_URL", "").strip().rstrip("/"),
            "cloud_secret": os.environ.get("AGENT_SERVER_YUNWORK_CLOUD_SECRET", ""),
            "utoken_url": os.environ.get("AGENT_SERVER_UTOKEN_URL", "").strip().rstrip("/"),
            "key_secret": os.environ.get("AGENT_SERVER_UTOKEN_CLOUD_KEY_SECRET", ""),
            "public_origin": os.environ.get("AGENT_SERVER_PUBLIC_ORIGIN", "").strip().rstrip("/"),
        }
        if not all(values.values()):
            return None
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self) -> None:
        for name, value in (
            ("AGENT_SERVER_YUNWORK_CLOUD_URL", self.cloud_url),
            ("AGENT_SERVER_UTOKEN_URL", self.utoken_url),
            ("AGENT_SERVER_PUBLIC_ORIGIN", self.public_origin),
        ):
            if not _is_origin(value):
                raise CloudComputerError(f"{name} must be an HTTP(S) origin", 503)
        if len(self.cloud_secret) < 32 or len(self.key_secret) < 32:
            raise CloudComputerError("cloud computer shared secrets must contain at least 32 characters", 503)


def _is_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


class CloudComputerClient:
    def __init__(
        self,
        settings: CloudComputerSettings | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @classmethod
    def from_environment(cls) -> CloudComputerClient:
        return cls(CloudComputerSettings.from_environment())

    @property
    def configured(self) -> bool:
        return self.settings is not None

    def instance_id(self, user_id: str) -> str:
        settings = self._settings()
        return cloud_instance_id(user_id, settings.cloud_secret)

    async def get(self, instance_id: str) -> CloudInstance | None:
        response = await self._cloud_request("GET", f"/v1/instances/{instance_id}")
        if response is None:
            return None
        return self._instance(response)

    async def create(
        self,
        *,
        user_id: str,
        display_name: str,
        connector_id: str,
        connector_token: str,
        yunwork_api_key: str,
    ) -> CloudInstance:
        settings = self._settings()
        response = await self._cloud_request(
            "POST",
            "/v1/instances",
            body={
                "userId": user_id,
                "displayName": display_name or "云电脑",
                "serverUrl": settings.public_origin,
                "connectorId": connector_id,
                "connectorToken": connector_token,
                "yunworkApiKey": yunwork_api_key,
                "apiBaseUrl": settings.utoken_url,
                "authBaseUrl": settings.utoken_url,
            },
        )
        if response is None:
            raise CloudComputerError("云主机响应无效")
        return self._instance(response)

    async def delete(self, instance_id: str) -> None:
        await self._cloud_request("DELETE", f"/v1/instances/{instance_id}")

    async def language_key(self, subject: str) -> str:
        settings = self._settings()
        if not subject.isdecimal() or int(subject) <= 0:
            raise CloudComputerError("当前账号没有有效的 utoken 身份", 409)
        response = await self._request(
            "POST",
            settings.utoken_url + "/api/yuncontrol/cloud-key",
            headers={"X-Cloud-Key-Secret": settings.key_secret},
            body={"user_id": int(subject)},
        )
        if response is None:
            raise CloudComputerError("认证服务响应无效")
        key = response.get("language_api_key")
        if not isinstance(key, str) or not key.startswith("sk-") or len(key) < 13:
            raise CloudComputerError("认证服务响应无效")
        return key

    async def _cloud_request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        settings = self._settings()
        return await self._request(
            method,
            settings.cloud_url + path,
            headers={"Authorization": f"Bearer {settings.cloud_secret}"},
            body=body,
            allow_missing=True,
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
        allow_missing: bool = False,
    ) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20, connect=5),
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.request(method, url, headers=headers, json=body)
            if allow_missing and response.status_code == 404:
                return None
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CloudComputerError("云电脑依赖服务暂时不可用") from exc
        if not isinstance(result, dict):
            raise CloudComputerError("云电脑依赖服务响应无效")
        return result

    @staticmethod
    def _instance(value: dict[str, Any]) -> CloudInstance:
        try:
            return CloudInstance.model_validate(value)
        except ValidationError as exc:
            raise CloudComputerError("云主机响应无效") from exc

    def _settings(self) -> CloudComputerSettings:
        if self.settings is None:
            raise CloudComputerError("云电脑尚未配置，请联系管理员完成部署", 503)
        return self.settings
