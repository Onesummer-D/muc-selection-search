"""领域模型与契约常量。

字段含义、枚举与唯一约束以 docs/week1/04_接口与数据字典.md（v1.0，2026-09-17 冻结）
及 schemas/article_bundle.v1.schema.json、schemas/extraction_bundle.v1.schema.json 为准。

person_name、avatar_ref、qr_code_ref、contact_info、meeting_entry、original_asset_ref、
source_sso_url 是受控数据库的私有字段（接口字典第 5 节，2026-09-18 附录 G 更新）：
bundle 不携带，导入不写入，永不进入仓库样本与访客 DTO。
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_ARTICLE = "article_bundle.v1"
SCHEMA_EXTRACTION = "extraction_bundle.v1"

# 处理状态：article.fetch_status / record.review_status / bundle.processing_status
PROCESS_STATUSES = frozenset({"pending", "processed", "review_required", "failed"})
# processing_events 与调度状态，比处理状态多一个 running（接口字典第 7 节）
EVENT_STATUSES = frozenset({"pending", "running", "processed", "review_required", "failed"})
# 发布状态，与处理状态分离；只有人工确认且 published 的记录可进入公开查询
VISIBILITIES = frozenset({"draft", "published", "withdrawn"})
CONTENT_TYPES = frozenset({"text", "poster", "mixed", "unknown"})
ASSET_KINDS = frozenset({"poster", "image", "attachment"})
EVIDENCE_METHODS = frozenset({"html_rule", "ocr_rule", "multimodal", "manual"})
# 七个关键字段：既是记录的可空字段，也是证据允许指向的字段
KEY_FIELDS = ("cohort", "grade", "education", "college", "major", "city", "position_or_unit")
EVIDENCE_FIELDS = frozenset(KEY_FIELDS)


@dataclass
class Article:
    """一篇文章 / 海报来源，notice_id 唯一，可对应零到多条人物记录。"""

    notice_id: str
    title: str
    source_url: str
    content_type: str
    fetch_status: str
    fetched_at: str
    published_at: str | None = None
    clean_text: str | None = None
    failure_reason: str | None = None
    schema_version: str = SCHEMA_ARTICLE

    @classmethod
    def from_bundle(cls, bundle: dict) -> "Article":
        return cls(
            notice_id=bundle["notice_id"],
            title=bundle["title"],
            source_url=bundle["source_url"],
            content_type=bundle["content_type"],
            fetch_status=bundle["fetch_status"],
            fetched_at=bundle["fetched_at"],
            published_at=bundle.get("published_at"),
            clean_text=bundle.get("clean_text"),
            failure_reason=bundle.get("failure_reason"),
            schema_version=bundle["schema_version"],
        )


@dataclass
class Asset:
    """素材：本地受限引用、摘要与派生资源引用，asset_id 唯一。"""

    asset_id: str
    notice_id: str
    kind: str
    local_ref: str
    sha256: str
    derived_guest_ref: str | None = None

    @classmethod
    def from_bundle(cls, notice_id: str, ref: dict) -> "Asset":
        return cls(
            asset_id=ref["asset_id"],
            notice_id=notice_id,
            kind=ref["kind"],
            local_ref=ref["local_ref"],
            sha256=ref["sha256"],
        )


@dataclass
class ExperienceRecord:
    """一条人物经验记录，record_key 唯一；一篇 Article 可对应多条（一帖多人）。

    review_status 是处理状态，visibility 是发布状态，两者分离；
    导入只允许产生 draft，发布由人工复核流程决定。
    """

    record_key: str
    notice_id: str
    extractor_version: str
    review_status: str
    confidence: float
    cohort: str | None = None
    grade: str | None = None
    education: str | None = None
    college: str | None = None
    major: str | None = None
    city: str | None = None
    position_or_unit: str | None = None
    visibility: str = "draft"
    person_name: str | None = None
    avatar_ref: str | None = None
    qr_code_ref: str | None = None
    contact_info: str | None = None
    meeting_entry: str | None = None
    original_asset_ref: str | None = None
    source_sso_url: str | None = None

    @classmethod
    def from_bundle(
        cls, notice_id: str, extractor_version: str, record: dict
    ) -> "ExperienceRecord":
        return cls(
            record_key=record["record_key"],
            notice_id=notice_id,
            extractor_version=extractor_version,
            review_status=record["review_status"],
            confidence=record["confidence"],
            cohort=record["cohort"],
            grade=record["grade"],
            education=record["education"],
            college=record["college"],
            major=record["major"],
            city=record["city"],
            position_or_unit=record["position_or_unit"],
        )


@dataclass
class Evidence:
    """一个字段的来源依据，必须关联 record_key 与字段名。"""

    record_key: str
    field: str
    text: str
    method: str
    asset_id: str | None = None
    bbox: list[float] | None = None

    @classmethod
    def from_bundle(cls, record_key: str, item: dict) -> "Evidence":
        return cls(
            record_key=record_key,
            field=item["field"],
            text=item["text"],
            method=item["method"],
            asset_id=item["asset_id"],
            bbox=list(item["bbox"]) if item["bbox"] is not None else None,
        )


@dataclass
class ProcessingEvent:
    """处理步骤事件：步骤、状态、时间与失败原因。事件是审计日志，只增不删。"""

    notice_id: str | None
    step: str
    status: str
    occurred_at: str
    failure_reason: str | None = None
    event_id: int | None = None
