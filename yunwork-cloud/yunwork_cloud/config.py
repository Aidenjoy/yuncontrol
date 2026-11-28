from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    control_secret: str
    data_root: Path
    image: str = "yunwork-cloud:local"
    docker_bin: str = "docker"
    memory: str = "2g"
    cpus: str = "2"
    pids_limit: int = 512

    @classmethod
    def from_env(cls) -> Settings:
        secret = os.environ.get("YUNWORK_CLOUD_CONTROL_SECRET", "")
        if len(secret) < 32:
            raise RuntimeError("YUNWORK_CLOUD_CONTROL_SECRET must contain at least 32 characters")
        raw_root = os.environ.get("YUNWORK_CLOUD_DATA_ROOT", "/srv/yunwork-cloud/users")
        root = Path(raw_root)
        if not root.is_absolute():
            raise RuntimeError("YUNWORK_CLOUD_DATA_ROOT must be an absolute host path")
        image = os.environ.get("YUNWORK_CLOUD_IMAGE", "yunwork-cloud:local").strip()
        docker_bin = os.environ.get("YUNWORK_CLOUD_DOCKER_BIN", "docker").strip()
        if not image or not docker_bin:
            raise RuntimeError("YUNWORK_CLOUD_IMAGE and YUNWORK_CLOUD_DOCKER_BIN must not be empty")
        try:
            pids_limit = int(os.environ.get("YUNWORK_CLOUD_PIDS_LIMIT", "512"))
        except ValueError as exc:
            raise RuntimeError("YUNWORK_CLOUD_PIDS_LIMIT must be an integer") from exc
        if not 64 <= pids_limit <= 8192:
            raise RuntimeError("YUNWORK_CLOUD_PIDS_LIMIT must be between 64 and 8192")
        return cls(
            control_secret=secret,
            data_root=root,
            image=image,
            docker_bin=docker_bin,
            memory=os.environ.get("YUNWORK_CLOUD_MEMORY", "2g"),
            cpus=os.environ.get("YUNWORK_CLOUD_CPUS", "2"),
            pids_limit=pids_limit,
        )
