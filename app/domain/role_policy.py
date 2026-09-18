"""角色策略：guest / student / teacher / admin 的服务端权限判断。

权限判断只发生在后端（ARCHITECTURE 8.1）；前端只渲染服务端 DTO。
开发角色开关必须由环境变量 ENABLE_DEV_ROLE_SWITCH 显式开启（附录 G G5），
生产环境该入口不可用。正式认证目标为 CAS/SSO，第二周接入。
"""

from __future__ import annotations

import os

ROLES = ("guest", "student", "teacher", "admin")

# 角色展示名（前端显示用）
ROLE_LABELS_ZH = {
    "guest": "游客",
    "student": "校内学生",
    "teacher": "校内教师",
    "admin": "管理员",
}

# 查询可见性：非 admin 只能看到人工确认且 published 的记录（接口字典 5.1 / 任务2）
PUBLISHED_ONLY_ROLES = frozenset({"guest", "student", "teacher"})
# review_required 只进入 admin 复核队列和管理员演示
REVIEW_QUEUE_ROLE = "admin"

# 访客 DTO 必须删除的私有/受限字段（接口字典 5.1，附录 G 扩展到 7 个）
PRIVATE_FIELDS = (
    "person_name",
    "avatar_ref",
    "qr_code_ref",
    "contact_info",
    "meeting_entry",
    "original_asset_ref",
    "source_sso_url",
)

# 游客不可见的来源字段：需要登录的来源 URL 不下发（附录 G G9 游客可见范围矩阵）
GUEST_HIDDEN_SOURCE_FIELDS = ("source_url", "local_ref")

# 完整海报由独立策略开关控制，默认关闭（CAMPUS_ORIGINAL_ASSET_ENABLED）
CAMPUS_ORIGINAL_ASSET_ENABLED = "CAMPUS_ORIGINAL_ASSET_ENABLED"
# 开发角色开关环境变量
DEV_ROLE_SWITCH_ENABLED = "ENABLE_DEV_ROLE_SWITCH"


def is_valid_role(role: str) -> bool:
    return role in ROLES


def normalize_role(role: str | None) -> str:
    """会话角色归一化；非法值一律按 guest 处理，不抛错。"""
    if role and role in ROLES:
        return role
    return "guest"


def published_only(role: str) -> bool:
    """该角色是否只能查询 published 记录。"""
    return role in PUBLISHED_ONLY_ROLES


def can_see_review_queue(role: str) -> bool:
    return role == REVIEW_QUEUE_ROLE


def campus_original_asset_enabled() -> bool:
    """完整海报策略开关；没有学校授权前保持关闭。"""
    return os.environ.get(CAMPUS_ORIGINAL_ASSET_ENABLED, "false").lower() == "true"


def dev_role_switch_enabled() -> bool:
    """开发角色开关是否启用；生产配置必须为 false。"""
    return os.environ.get(DEV_ROLE_SWITCH_ENABLED, "false").lower() == "true"


def role_capabilities(role: str) -> list[str]:
    """各角色可用能力，供 /api/auth/me 与前端渲染。"""
    if role == "guest":
        caps = ["search", "view_public_detail", "view_public_stats"]
    elif role in ("student", "teacher"):
        caps = ["search", "view_authorized_detail", "view_source_sso_link",
                "compare", "export", "save_search"]
    else:
        caps = ["search", "view_full_detail", "view_source_sso_link",
                "compare", "export", "review_queue", "sync", "view_audit_log"]
    if campus_original_asset_enabled() and role != "guest":
        caps.append("view_full_poster")
    return caps
