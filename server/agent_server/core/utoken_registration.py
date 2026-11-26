"""当前注册界面的强类型请求；验证码和账号生命周期完全由 token 服务管理。"""

from typing import Literal

from pydantic import BaseModel, Field


class UtokenRegistrationConfig(BaseModel):
    """上游公开注册能力，不包含密钥、邮件配置或管理权限。"""

    enabled: bool
    emailVerification: bool
    phoneVerification: bool
    turnstileSiteKey: str | None = None
    agreementUrl: str | None = None
    privacyUrl: str | None = None


class UtokenRegistrationCodeRequest(BaseModel):
    """请求 token 服务向指定邮箱或手机发送注册验证码。"""

    method: Literal["email", "phone"]
    recipient: str = Field(min_length=1, max_length=320)
    turnstile: str = Field(default="", max_length=4096, repr=False)


class UtokenRegistrationRequest(BaseModel):
    """只转发上游支持的普通用户注册字段，不接受角色或本地账号字段。"""

    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=8, max_length=20, repr=False)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=32)
    verificationCode: str = Field(default="", max_length=32, repr=False)
    inviteCode: str = Field(default="", max_length=128, repr=False)
    affiliateCode: str = Field(default="", max_length=128, repr=False)
    turnstile: str = Field(default="", max_length=4096, repr=False)
    agreed: bool = False


class UtokenRegistrationResult(BaseModel):
    """注册或发码成功，不返回登录会话或本地账号。"""

    success: bool = True
