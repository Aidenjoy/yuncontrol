from __future__ import annotations

import hmac
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from yunwork_cloud.config import Settings
from yunwork_cloud.docker import DockerError
from yunwork_cloud.service import CloudError, InstanceCreateRequest, InstanceManager


def create_app(settings: Settings | None = None, manager: InstanceManager | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    manager = manager or InstanceManager(settings)
    app = FastAPI(title="Yunwork Cloud Controller", docs_url=None, redoc_url=None, openapi_url=None)
    async def authorized(request: Request) -> None:
        scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.encode(), settings.control_secret.encode()):
            raise CloudError("无效的云主机控制凭证", 401)

    @app.middleware("http")
    async def limit_request(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > 64 * 1024:
            return JSONResponse(status_code=413, content={"detail": "请求体过大"})
        return await call_next(request)

    @app.exception_handler(CloudError)
    async def cloud_error_handler(_request: Request, exc: CloudError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(DockerError)
    async def docker_error_handler(_request: Request, exc: DockerError):
        logger.error("Docker operation failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Docker 操作失败，请检查控制服务状态"})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "请求字段无效", "errors": errors})

    @app.get("/healthz")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/instances", dependencies=[Depends(authorized)])
    async def create_instance(payload: InstanceCreateRequest):
        return await manager.create(payload)

    @app.get("/v1/instances/{instance_id}", dependencies=[Depends(authorized)])
    async def get_instance(instance_id: str):
        return await manager.get(instance_id)

    @app.delete("/v1/instances/{instance_id}", dependencies=[Depends(authorized)])
    async def delete_instance(instance_id: str):
        return await manager.delete(instance_id)

    return app
