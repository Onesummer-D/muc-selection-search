"""AuthProvider/CAS Provider 最小契约。

应用层只依赖 subject、role 与登录态；开发角色开关不是生产认证替代品。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthIdentity:
    subject: str
    role: str
    authenticated: bool = True


class AuthProvider(Protocol):
    def current_identity(self) -> AuthIdentity | None:
        """返回当前请求的 CAS/SSO 身份，未登录返回 None。"""

    def login_url(self, next_url: str = "/") -> str:
        """返回服务端生成的登录地址，不拼接客户端提供的凭据。"""


class CasProvider:
    """CAS 生产适配器占位：缺少端点/回调时明确报告未配置。"""

    def __init__(self, login_endpoint: str | None = None):
        self.login_endpoint = login_endpoint

    def current_identity(self) -> AuthIdentity | None:
        return None

    def login_url(self, next_url: str = "/") -> str:
        if not self.login_endpoint:
            raise RuntimeError("CAS_PROVIDER_NOT_CONFIGURED")
        from urllib.parse import quote
        return f"{self.login_endpoint}?service={quote(next_url, safe='')}"
