from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from yunwork_cloud.config import Settings

MANAGED_LABEL = "com.yundashi.yunwork.managed"
INSTANCE_LABEL = "com.yundashi.yunwork.instance"


class DockerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContainerState:
    exists: bool
    owned: bool
    running: bool = False
    status: str = "missing"


class Docker:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def _execute(self, *args: str, timeout: float = 60) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                self.settings.docker_bin,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (OSError, TimeoutError) as exc:
            raise DockerError("Docker 命令执行失败") from exc
        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[-500:].strip()
            raise DockerError(detail or "Docker 命令执行失败")
        return stdout.decode(errors="replace").strip()

    async def inspect(self, container: str, instance_id: str) -> ContainerState:
        template = (
            "{{json .State}}|"
            f'{{{{index .Config.Labels "{MANAGED_LABEL}"}}}}|'
            f'{{{{index .Config.Labels "{INSTANCE_LABEL}"}}}}'
        )
        try:
            output = await self._execute("container", "inspect", "--format", template, container)
        except DockerError as exc:
            if "no such" in str(exc).lower() or "not found" in str(exc).lower():
                return ContainerState(exists=False, owned=False)
            raise
        raw_state, managed, owner = output.split("|", 2)
        state = json.loads(raw_state)
        owned = managed == "true" and owner == instance_id
        return ContainerState(
            exists=True,
            owned=owned,
            running=bool(state.get("Running")),
            status=str(state.get("Status") or "unknown"),
        )

    async def require_absent_or_owned(self, container: str, instance_id: str) -> ContainerState:
        state = await self.inspect(container, instance_id)
        if state.exists and not state.owned:
            raise DockerError("容器名称已被非本服务管理的实例占用")
        return state

    async def run(self, *, instance_id: str, container: str, env_file: Path, data_dir: Path) -> None:
        state = await self.require_absent_or_owned(container, instance_id)
        if state.exists:
            raise DockerError("同名容器已经存在")
        await self._execute("image", "inspect", self.settings.image)
        await self._execute(
            "run",
            "-d",
            "--name",
            container,
            "--label",
            f"{MANAGED_LABEL}=true",
            "--label",
            f"{INSTANCE_LABEL}={instance_id}",
            "--restart",
            "unless-stopped",
            "--env-file",
            str(env_file),
            "--volume",
            f"{data_dir}:/user:rw",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.settings.pids_limit),
            "--memory",
            self.settings.memory,
            "--cpus",
            self.settings.cpus,
            self.settings.image,
            timeout=90,
        )

    async def remove(self, *, container: str, instance_id: str) -> None:
        state = await self.require_absent_or_owned(container, instance_id)
        if state.exists:
            await self._execute("rm", "--force", container, timeout=90)
