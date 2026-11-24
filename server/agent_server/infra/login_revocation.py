"""在统一 ASGI 边界拒绝已撤销的用户凭证，覆盖 HTTP 与令牌式 WebSocket 握手。"""
import os
from urllib.parse import parse_qs

from starlette.responses import JSONResponse

from agent_server.core.auth import user_token_issued_at, verify_user_access_token


class LoginRevocationMiddleware:
    """使用现有数据库配置表读取撤销时间，不影响 Connector 自身的凭证。"""

    def __init__(self, app):
        """保存下游应用；实际 Store 由当前请求的应用状态提供。"""
        self.app = app

    async def __call__(self, scope, receive, send):
        """验证用户令牌时间；已建立连接与短期票据继续采用原有生命周期。"""
        if scope["type"] in {"http", "websocket"} and os.environ.get("AGENT_SERVER_UTOKEN_URL", "").strip():
            headers = dict(scope.get("headers", []))
            authorization = headers.get(b"authorization", b"").decode("latin-1")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not token:
                token = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("token", [""])[0]
            user_id = verify_user_access_token(token) if token else None
            if user_id:
                cutoff = await scope["app"].state.store.get_setting("auth-revoked:" + user_id)
                if cutoff is not None and user_token_issued_at(token) <= int(cutoff):
                    if scope["type"] == "websocket":
                        await send({"type": "websocket.close", "code": 1008, "reason": "login expired"})
                    else:
                        await JSONResponse({"detail": "登录已失效，请重新登录"}, status_code=401)(scope, receive, send)
                    return
        await self.app(scope, receive, send)
