"""UToken 身份桥接、兼容入口及并发幂等回归，不访问真实账号或模型。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from agent_server.api import auth
from agent_server.services import utoken_login
from agent_server.services.utoken_login import UtokenIdentity, UtokenLoginError
from conftest import make_test_client


@pytest.fixture
def client(monkeypatch):
    """先初始化原有本地管理员，再启用 UToken，保持真实权限与会话机制。"""
    monkeypatch.delenv("AGENT_SERVER_UTOKEN_URL", raising=False)
    with make_test_client() as client:
        token = client.app.state.setup_token.peek()
        response = client.post("/auth/register", json={"email": "admin@example.test", "password": "admin-secret", "displayName": "Admin", "setupToken": token})
        assert response.status_code == 200
        monkeypatch.setenv("AGENT_SERVER_UTOKEN_URL", "http://utoken.test")
        yield client


def identity(monkeypatch):
    """模拟上游验证结果，保留实际数据库事务与本地凭证签发。"""
    async def authenticate(origin, username, password):
        assert username == "utoken-user" and password == "utoken-secret"
        return UtokenIdentity(origin, "123", "UToken User")
    monkeypatch.setattr(auth, "authenticate_utoken", authenticate)


def login(client):
    """使用原有接口及 email/password 字段提交非邮箱用户名。"""
    return client.post("/auth/login", json={"email": "utoken-user", "password": "utoken-secret"})


def test_create_reuse_and_access_existing_session(client, monkeypatch):
    identity(monkeypatch)
    first = login(client)
    assert first.status_code == 200
    data = first.json()
    assert data["role"] == "member"
    assert login(client).json()["userId"] == data["userId"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {data['accessToken']}"})
    assert me.status_code == 200 and me.json()["userId"] == data["userId"]
    assert asyncio.run(client.app.state.store.count_users()) == 2


def test_concurrent_first_login_is_idempotent(client, monkeypatch):
    identity(monkeypatch)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: login(client), range(5)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()["userId"] for r in results}) == 1
    assert asyncio.run(client.app.state.store.count_users()) == 2


def test_disabled_local_account_cannot_reenter(client, monkeypatch):
    identity(monkeypatch)
    user = login(client).json()["userId"]
    asyncio.run(client.app.state.store.set_user_disabled(user, True))
    assert login(client).status_code == 403
    assert asyncio.run(client.app.state.store.count_users()) == 2


def test_admin_preserved_and_registration_oauth_closed(client):
    assert client.post("/auth/login", json={"email": "admin@example.test", "password": "admin-secret"}).json()["role"] == "admin"
    assert client.post("/auth/register", json={"email": "member@example.test", "password": "secret", "displayName": "Member"}).status_code == 403
    assert client.get("/auth/oauth/start").status_code == 403
    assert client.post("/auth/oauth/finalize", json={"pendingToken": "invalid"}).status_code == 403
    cfg = client.get("/auth/config").json()
    assert cfg["registrationOpen"] is False and cfg["oauthEnabled"] is False


def test_local_member_password_not_accepted(client, monkeypatch):
    asyncio.run(client.app.state.store.create_email_user(email="member@example.test", display_name="Member", password="local-secret"))
    async def reject(*args):
        raise UtokenLoginError("invalid credentials", 401)
    monkeypatch.setattr(auth, "authenticate_utoken", reject)
    assert client.post("/auth/login", json={"email": "member@example.test", "password": "local-secret"}).status_code == 401
    assert client.post("/auth/login", json={"email": "member@example.test", "passwordVerifier": "invalid"}).status_code == 401


@pytest.mark.parametrize("status", [401, 409, 502, 503])
def test_upstream_errors_never_create_account(client, monkeypatch, status):
    async def fail(*args):
        raise UtokenLoginError("safe error", status)
    monkeypatch.setattr(auth, "authenticate_utoken", fail)
    assert login(client).status_code == status
    assert asyncio.run(client.app.state.store.count_users()) == 1


@pytest.mark.parametrize("payload,status", [
    ({"success": False}, 401),
    ({"success": True, "data": {"require_2fa": True}}, 409),
    ({"success": True, "data": {"id": 123, "status": 2}}, 401),
    ({"success": True, "data": {"id": True, "status": 1}}, 502),
    ({"success": True, "data": {"id": 123, "status": 1, "username": "user", "role": 100}}, 200),
])
def test_upstream_contract(monkeypatch, payload, status):
    real_client = httpx.AsyncClient
    def handler(request):
        assert str(request.url) == "http://utoken.test/api/user/login"
        assert b'"username":"user"' in request.content
        return httpx.Response(200, json=payload)
    monkeypatch.setattr(utoken_login.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    if status == 200:
        result = asyncio.run(utoken_login.authenticate_utoken("http://utoken.test", "user", "secret"))
        assert result.subject == "123"
    else:
        with pytest.raises(UtokenLoginError) as error:
            asyncio.run(utoken_login.authenticate_utoken("http://utoken.test", "user", "secret"))
        assert error.value.status_code == status


def test_local_admin_password_verifier_compatibility(client):
    from agent_server.core.auth import hash_password
    salt = client.post("/auth/password-salt", json={"email": "admin@example.test"}).json()["salt"]
    verifier = hash_password("admin-secret", salt=salt).split("$", 2)[2]
    response = client.post("/auth/login", json={"email": "admin@example.test", "passwordVerifier": verifier})
    assert response.status_code == 200 and response.json()["role"] == "admin"


@pytest.mark.parametrize("failure,status", [("timeout", 502), ("redirect", 502), ("unauthorized", 401), ("invalid_json", 502)])
def test_upstream_transport_failures(monkeypatch, failure, status):
    real_client = httpx.AsyncClient
    def handler(request):
        if failure == "timeout":
            raise httpx.ConnectTimeout("timeout", request=request)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "http://untrusted.test"})
        if failure == "unauthorized":
            return httpx.Response(401)
        return httpx.Response(200, content=b"not-json")
    monkeypatch.setattr(utoken_login.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(UtokenLoginError) as error:
        asyncio.run(utoken_login.authenticate_utoken("http://utoken.test", "user", "secret"))
    assert error.value.status_code == status


def test_first_utoken_login_requires_admin_initialization(monkeypatch):
    monkeypatch.setenv("AGENT_SERVER_UTOKEN_URL", "http://utoken.test")
    with make_test_client() as client:
        assert client.get("/auth/config").json()["needsBootstrap"] is True
        assert login(client).status_code == 403
        assert asyncio.run(client.app.state.store.count_users()) == 0


def test_password_change_revokes_access_and_refresh_idempotently(client, monkeypatch):
    import time
    from agent_server.core.auth import create_signed_token
    identity(monkeypatch)
    monkeypatch.setenv("AGENT_SERVER_AUTH_REVOKE_SECRET", "notification-secret-" + "x" * 32)
    first = login(client).json()
    old = {"Authorization": f"Bearer {first['accessToken']}"}
    assert client.get("/auth/me", headers=old).status_code == 200
    event = {"userId": 123, "changedAt": time.time_ns() // 1_000_000}
    assert client.post("/auth/revoke", json=event).status_code == 401
    secret = {"X-Auth-Secret": "notification-secret-" + "x" * 32}
    assert client.post("/auth/revoke", json=event, headers=secret).json()["matched"] is True
    assert client.get("/auth/me", headers=old).status_code == 401
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as disconnected:
        with client.websocket_connect("/api/v2/unused?token=" + first["accessToken"]):
            pass
    assert disconnected.value.code == 1008
    refresh = create_signed_token("mobile_refresh", {"sub": first["userId"], "aud": "agents-anywhere-mobile"}, 600)
    assert client.post("/auth/mobile-login/refresh", json={"refreshToken": refresh}).status_code == 401
    # 之后的新登录可用；重放旧通知不能撤销它。
    original_ns = time.time_ns()
    monkeypatch.setattr(time, "time_ns", lambda: original_ns + 10_000_000)
    second = login(client).json()
    assert second["userId"] == first["userId"]
    assert client.post("/auth/revoke", json=event, headers=secret).status_code == 200
    event["changedAt"] -= 1
    assert client.post("/auth/revoke", json=event, headers=secret).status_code == 200
    new = {"Authorization": f"Bearer {second['accessToken']}"}
    assert client.get("/auth/me", headers=new).status_code == 200


def test_revoke_endpoint_rejects_future_and_acknowledges_unknown(client, monkeypatch):
    import time
    monkeypatch.setenv("AGENT_SERVER_AUTH_REVOKE_SECRET", "notification-secret-" + "x" * 32)
    headers = {"X-Auth-Secret": "notification-secret-" + "x" * 32}
    now = time.time_ns() // 1_000_000
    assert client.post("/auth/revoke", headers=headers, json={"userId": 9999, "changedAt": now + 120_000}).status_code == 422
    result = client.post("/auth/revoke", headers=headers, json={"userId": 9999, "changedAt": now})
    assert result.status_code == 200 and result.json() == {"ok": True, "matched": False}
    assert asyncio.run(client.app.state.store.count_users()) == 1
