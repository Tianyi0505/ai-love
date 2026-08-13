
from __future__ import annotations

from dataclasses import dataclass, field


# 描述账号绑定冲突
class BindingViolation(ValueError):
    pass


# 描述渠道支持的发送能力
@dataclass(frozen=True)
class ChannelCapabilities:

    is_live_platform: bool = False
    supports_multi_ai: bool = False
    send_types: frozenset[str] = field(default_factory=frozenset)
    receive_types: frozenset[str] = field(default_factory=frozenset)
    supports_history: bool = False


# 表示社交账号数据
@dataclass(frozen=True)
class SocialAccount:
    account_id: str
    platform: str
    platform_account_id: str
    display_name: str = ""
    credential_ref: str = ""
    status: str = "offline"
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)


# 表示账号绑定数据
@dataclass(frozen=True)
class AccountBinding:
    account_id: str
    ai_id: str
    active: bool = True


# 表示平台身份数据
@dataclass(frozen=True)
class PlatformIdentity:

    identity_id: str
    person_id: str
    platform: str
    account_id: str
    platform_user_id: str
    verified_by: str


# 校验账号绑定关系
def validate_account_bindings(account: SocialAccount, bindings: list[AccountBinding]) -> None:

    active = [binding for binding in bindings if binding.active and binding.account_id == account.account_id]
    ai_ids = [binding.ai_id for binding in active]
    if len(ai_ids) != len(set(ai_ids)):
        raise BindingViolation(f"账号 {account.account_id} 存在重复 AI 绑定")
    if len(active) > 1 and not account.capabilities.supports_multi_ai:
        raise BindingViolation(f"平台 {account.platform} 的账号不允许绑定多个 AI")
