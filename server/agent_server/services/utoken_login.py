"""验证 utoken 账号密码，不保留上游密码、Cookie 或模型密钥。"""
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class UtokenIdentity:
    """经 utoken 验证的稳定账号身份及展示名称。"""

    origin: str
    subject: str
    display_name: str


class UtokenLoginError(ValueError):
    """携带安全错误提示及 HTTP 状态，不包含上游响应或凭证。"""

    def __init__(self, message: str, status_code: int):
        """保存可返回给客户端的错误，不泄露上游响应内容。"""
        super().__init__(message)
        self.status_code = status_code


async def authenticate_utoken(origin: str, username: str, password: str) -> UtokenIdentity:
    """调用可信配置的 utoken origin 验证密码，返回数字用户 ID；拒绝未完成的二次验证。"""
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise UtokenLoginError("认证服务地址未正确配置", 503)
    origin = origin.rstrip("/")
    try:
        # 步骤1：只向管理员配置的服务发送凭证，不经环境代理，禁止重定向转发密码。
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False, trust_env=False) as client:
            response = await client.post(f"{origin}/api/user/login", json={"username": username.strip(), "password": password})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise UtokenLoginError("账号或密码错误，或账号当前不可用", 401) from exc
        raise UtokenLoginError("登录服务暂时不可用，请稍后重试", 502) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise UtokenLoginError("登录服务暂时不可用，请稍后重试", 502) from exc
    # 步骤2：业务成功和二次验证状态必须同时检查，不能把待验证账号当作已登录。
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise UtokenLoginError("账号或密码错误，或账号当前不可用", 401)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise UtokenLoginError("登录服务响应无效", 502)
    if data.get("require_2fa"):
        raise UtokenLoginError("此账号需要二次验证，当前账号密码入口暂不支持", 409)
    user_id = data.get("id")
    if data.get("status") is not None and data.get("status") != 1:
        raise UtokenLoginError("账号已停用", 401)
    if type(user_id) is not int or user_id <= 0 or data.get("status") != 1:
        raise UtokenLoginError("登录服务未返回有效账号", 502)
    return UtokenIdentity(origin, str(user_id), str(data.get("display_name") or data.get("username") or "用户")[:64])
