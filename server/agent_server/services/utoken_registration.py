"""Relay existing token registration APIs without local mail, account creation or upstream changes."""

import os
from urllib.parse import urlsplit

import httpx

from agent_server.core.utoken_registration import (
    UtokenRegistrationCodeRequest,
    UtokenRegistrationConfig,
    UtokenRegistrationRequest,
)
from agent_server.services.utoken_login import UtokenLoginError


def registration_origin() -> str:
    """Read only the administrator-configured identity origin; never accept client supplied URLs."""
    origin = os.environ.get("AGENT_SERVER_UTOKEN_URL", "").strip().rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise UtokenLoginError("认证服务地址未正确配置", 503)
    return origin


async def _request(
    origin: str, method: str, path: str, *, params=None, body=None
) -> dict:
    """Call one fixed upstream endpoint without cookies, redirects or automatic write retries."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.request(
                method, origin + path, params=params, json=body
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as exc:
        status = 429 if exc.response.status_code == 429 else 502
        raise UtokenLoginError(
            "注册服务请求过于频繁" if status == 429 else "注册服务暂时不可用", status
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise UtokenLoginError("注册服务暂时不可用", 502) from exc
    if not isinstance(result, dict):
        raise UtokenLoginError("注册服务响应无效", 502)
    if result.get("success") is not True:
        message = result.get("message")
        if (
            path == "/api/verification"
            and isinstance(message, str)
            and message.strip() == "EOF"
        ):
            # token 原样返回 SMTP 异常；这是上游邮件服务故障，不应提示用户输入错误。
            raise UtokenLoginError(
                "token 邮件服务连接中断（EOF），请联系管理员检查 token 侧 SMTP 配置及连接",
                502,
            )
        raise UtokenLoginError(
            message[:300]
            if isinstance(message, str) and message
            else "注册请求未通过验证",
            400,
        )
    return result


async def registration_config() -> UtokenRegistrationConfig:
    """Expose only public upstream switches needed by the current registration form."""
    origin = registration_origin()
    result = await _request(origin, "GET", "/api/status")
    data = result.get("data")
    if not isinstance(data, dict):
        raise UtokenLoginError("注册服务响应无效", 502)
    captcha = data.get("turnstile_check") is True
    key = data.get("turnstile_site_key")
    if captcha and (not isinstance(key, str) or not key):
        raise UtokenLoginError("注册服务人机校验未正确配置", 503)
    return UtokenRegistrationConfig(
        enabled=data.get("register_enabled") is True
        and data.get("password_register_enabled") is True,
        emailVerification=data.get("email_verification") is True,
        phoneVerification=data.get("phone_verification") is True,
        turnstileSiteKey=key if captcha else None,
        agreementUrl=origin + "/user-agreement"
        if data.get("user_agreement_enabled") is True
        else None,
        privacyUrl=origin + "/privacy-policy"
        if data.get("privacy_policy_enabled") is True
        else None,
    )


async def send_registration_code(payload: UtokenRegistrationCodeRequest) -> None:
    """Token generates, stores, sends and subsequently verifies every code; local mail is unused."""
    config = await registration_config()
    if not config.enabled:
        raise UtokenLoginError("注册服务暂未开放", 403)
    if not (
        config.phoneVerification
        if payload.method == "phone"
        else config.emailVerification
    ):
        raise UtokenLoginError("该注册验证方式未开启", 400)
    path = (
        "/api/phone_verification" if payload.method == "phone" else "/api/verification"
    )
    await _request(
        registration_origin(),
        "GET",
        path,
        params={
            payload.method: payload.recipient.strip(),
            "turnstile": payload.turnstile,
        },
    )


async def register_utoken_account(payload: UtokenRegistrationRequest) -> None:
    """Forward only supported fields; upstream enforces uniqueness, codes, captcha and invitation rules."""
    config = await registration_config()
    if not config.enabled:
        raise UtokenLoginError("注册服务暂未开放", 403)
    if (config.agreementUrl or config.privacyUrl) and not payload.agreed:
        raise UtokenLoginError("请先同意用户协议及隐私政策", 400)
    await _request(
        registration_origin(),
        "POST",
        "/api/user/register",
        params={"turnstile": payload.turnstile},
        body={
            "username": payload.username.strip(),
            "password": payload.password,
            "email": payload.email.strip(),
            "phone": payload.phone.strip(),
            "verification_code": payload.verificationCode,
            "invite_code": payload.inviteCode.strip(),
            "aff_code": payload.affiliateCode.strip(),
        },
    )
