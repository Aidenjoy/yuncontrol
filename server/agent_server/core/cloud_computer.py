from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Literal

from pydantic import BaseModel

CloudComputerPhase = Literal["disabled", "provisioning", "running", "error"]


class CloudComputerResponse(BaseModel):
    configured: bool
    phase: CloudComputerPhase
    containerState: str = "missing"
    connectorId: str | None = None
    displayName: str = "云电脑"
    updatedAt: str | None = None
    error: str | None = None


class CloudInstance(BaseModel):
    instanceId: str
    connectorId: str
    displayName: str = "云电脑"
    phase: CloudComputerPhase
    containerState: str = "missing"
    updatedAt: str | None = None
    error: str | None = None


def cloud_instance_id(user_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return f"user-{digest[:24]}"


def cloud_installation_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agents-anywhere:cloud-computer:{user_id}"))


def cloud_connector_id(user_id: str) -> str:
    installation_id = cloud_installation_id(user_id)
    digest = hashlib.sha256(f"{user_id}:{installation_id}".encode()).hexdigest()
    return f"conn_{digest[:24]}"
