"""RecordPresenter：按角色生成 DTO。

规则来自接口字典 5.1 与附录 G G9 游客可见范围矩阵：
- guest：删除全部 7 个私有字段与来源 URL，使用匿名记录编号，证据仅保留脱敏文本。
- student/teacher：授权字段 + 来源 SSO 链接；头像/联系方式/会议入口/完整海报默认关闭。
- admin：完整字段、证据与处理信息（复核队列用）。

受限字段在服务端被删除（不出现在 JSON 中），前端不做任何脱敏逻辑。
"""

from __future__ import annotations

from typing import Any

from .models import Article, Evidence, ExperienceRecord
from .role_policy import (
    GUEST_HIDDEN_SOURCE_FIELDS,
    PRIVATE_FIELDS,
    ROLE_LABELS_ZH,
    campus_original_asset_enabled,
)


class RecordPresenter:
    """领域对象 → 角色 DTO。"""

    def present_summary(self, record: ExperienceRecord, article: Article | None, role: str) -> dict:
        """结果列表用摘要 DTO（不含证据数组，带证据数量）。"""
        dto = self._base(record, role)
        if article is not None:
            dto["source"] = self._source(article, role)
        return dto

    def present_full(
        self,
        record: ExperienceRecord,
        article: Article | None,
        evidence: list[Evidence],
        role: str,
    ) -> dict:
        """详情 DTO（含证据并排视图所需数据）。"""
        dto = self._base(record, role)
        if article is not None:
            dto["source"] = self._source(article, role)
        dto["evidence"] = [self._evidence(item, role) for item in evidence]
        dto["poster"] = {
            "full_access": role == "admin"
            or (role in ("student", "teacher") and campus_original_asset_enabled()),
            "note": "完整海报默认关闭，需学校授权后由策略开关启用"
            if role != "admin" else "管理员复核视图",
        }
        return dto

    # ---- 内部 ----

    def _base(self, record: ExperienceRecord, role: str) -> dict[str, Any]:
        dto: dict[str, Any] = {
            "record_key": record.record_key,
            "notice_id": record.notice_id,
            "display_name": f"匿名记录 {record.record_key}",
            "review_status": record.review_status,
            "visibility": record.visibility,
            "confidence": record.confidence,
            "fields": {
                "cohort": record.cohort,
                "grade": record.grade,
                "education": record.education,
                "college": record.college,
                "major": record.major,
                "city": record.city,
                "position_or_unit": record.position_or_unit,
            },
        }
        if role == "admin":
            # 管理员复核视图：受控字段仅在服务端注入，仍不得进入仓库样本
            dto["person"] = {
                "person_name": record.person_name,
                "avatar_ref": record.avatar_ref,
                "qr_code_ref": record.qr_code_ref,
                "contact_info": record.contact_info,
                "meeting_entry": record.meeting_entry,
                "original_asset_ref": record.original_asset_ref,
                "source_sso_url": record.source_sso_url,
            }
            dto["extractor_version"] = record.extractor_version
        return dto

    def _source(self, article: Article, role: str) -> dict[str, Any]:
        source: dict[str, Any] = {
            "title": article.title,
            "published_at": article.published_at,
            "content_type": article.content_type,
        }
        if role != "guest":
            # 校内角色可访问来源 SSO 链接；游客不下发需要登录的 URL
            source["url"] = article.source_url
        return source

    def _evidence(self, item: Evidence, role: str) -> dict[str, Any]:
        dto: dict[str, Any] = {
            "field": item.field,
            "text": item.text,
            "method": item.method,
            "bbox": item.bbox,
        }
        if role != "guest" and item.asset_id:
            dto["asset_id"] = item.asset_id
        return dto


def assert_no_restricted_fields(dto: dict, role: str) -> None:
    """内部校验：非 admin DTO 中禁止出现任何受限键（防止回归）。"""
    if role == "admin":
        return
    forbidden = set(PRIVATE_FIELDS) | set(GUEST_HIDDEN_SOURCE_FIELDS) | {"local_ref"}
    found = _find_keys(dto, forbidden)
    if found:
        raise AssertionError(f"{role} DTO 泄漏受限字段: {sorted(found)}")


def _find_keys(data: Any, forbidden: set[str], path: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if key in forbidden:
                found.add(f"{path}{key}")
            found |= _find_keys(value, forbidden, f"{path}{key}.")
    elif isinstance(data, list):
        for index, value in enumerate(data):
            found |= _find_keys(value, forbidden, f"{path}[{index}].")
    return found


def role_label(role: str) -> str:
    return ROLE_LABELS_ZH.get(role, role)
