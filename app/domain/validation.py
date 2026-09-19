"""bundle 契约校验：article_bundle.v1 与 extraction_bundle.v1。

与 schemas 下两份 JSON Schema（draft 2020-12，additionalProperties=false）逐条对齐：
必填键、字符串长度、枚举、数字范围、ISO 8601 时间、private:// 前缀、
sha256 十六进制摘要、bbox 四元数组，以及 article 的“failed 必须带原因”条件约束。

校验发生在任何写入之前；失败抛 ContractViolation，数据库不产生任何改动。
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from .errors import ContractViolation
from .models import (
    ASSET_KINDS,
    CONTENT_TYPES,
    EVIDENCE_FIELDS,
    EVIDENCE_METHODS,
    KEY_FIELDS,
    PROCESS_STATUSES,
    SCHEMA_ARTICLE,
    SCHEMA_EXTRACTION,
)

_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")

_ARTICLE_KEYS = frozenset({
    "schema_version", "notice_id", "title", "source_url", "published_at",
    "content_type", "clean_text", "asset_refs", "fetch_status",
    "failure_reason", "fetched_at",
})
_ARTICLE_REQUIRED = frozenset({
    "schema_version", "notice_id", "title", "source_url", "content_type",
    "asset_refs", "fetch_status", "fetched_at",
})
_ASSET_KEYS = frozenset({"asset_id", "kind", "local_ref", "sha256"})

_EXTRACTION_KEYS = frozenset({
    "schema_version", "notice_id", "extractor_version", "records",
    "processing_status", "failure_reason", "processed_at",
})
_EXTRACTION_REQUIRED = frozenset({
    "schema_version", "notice_id", "extractor_version", "records",
    "processing_status", "processed_at",
})
_RECORD_KEYS = frozenset({"record_key", "review_status", "confidence", "evidence", *KEY_FIELDS})
_EVIDENCE_KEYS = frozenset({"field", "text", "method", "asset_id", "bbox"})


def _require_dict(value: object, path: str) -> None:
    if not isinstance(value, dict):
        raise ContractViolation(f"{path}: 必须是对象，实际是 {type(value).__name__}")


def _require_list(value: object, path: str) -> None:
    if not isinstance(value, list):
        raise ContractViolation(f"{path}: 必须是数组，实际是 {type(value).__name__}")


def _reject_unknown(data: dict, allowed: frozenset, path: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractViolation(f"{path}: 存在未知字段 {extra}（additionalProperties=false）")


def _require_keys(data: dict, required: frozenset, path: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise ContractViolation(f"{path}: 缺少必填字段 {missing}")


def _check_str(value: object, path: str, *, allow_none: bool = False, min_length: int = 0) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str):
        raise ContractViolation(f"{path}: 必须是字符串，实际是 {type(value).__name__}")
    if len(value) < min_length:
        raise ContractViolation(f"{path}: 字符串长度不得小于 {min_length}，实际是 {value!r}")


def _check_datetime(value: object, path: str) -> None:
    if not isinstance(value, str):
        raise ContractViolation(f"{path}: 必须是 ISO 8601 字符串，实际是 {type(value).__name__}")
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractViolation(f"{path}: 不是合法的 ISO 8601 时间：{value!r}") from exc


def _check_url(value: object, path: str) -> None:
    _check_str(value, path)
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ContractViolation(f"{path}: 必须是 http(s) URL，实际是 {value!r}")


def _check_number(value: object, path: str, minimum: float, maximum: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractViolation(f"{path}: 必须是数字，实际是 {type(value).__name__}")
    if not minimum <= value <= maximum:
        raise ContractViolation(f"{path}: 必须在 {minimum} 到 {maximum} 之间，实际是 {value!r}")


def _check_enum(value: object, allowed: frozenset, path: str) -> None:
    if value not in allowed:
        raise ContractViolation(f"{path}: 只允许 {sorted(allowed)}，实际是 {value!r}")


def _validate_asset_ref(ref: object, path: str) -> None:
    _require_dict(ref, path)
    assert isinstance(ref, dict)
    _reject_unknown(ref, _ASSET_KEYS, path)
    _require_keys(ref, _ASSET_KEYS, path)
    _check_str(ref["asset_id"], f"{path}.asset_id", min_length=1)
    _check_enum(ref["kind"], ASSET_KINDS, f"{path}.kind")
    _check_str(ref["local_ref"], f"{path}.local_ref", min_length=1)
    if not ref["local_ref"].startswith("private://"):
        raise ContractViolation(f"{path}.local_ref: 必须以 private:// 开头，实际是 {ref['local_ref']!r}")
    if not _SHA256_RE.fullmatch(ref["sha256"]):
        raise ContractViolation(f"{path}.sha256: 必须是 64 位十六进制摘要，实际是 {ref['sha256']!r}")


def _validate_evidence(item: object, path: str) -> None:
    _require_dict(item, path)
    assert isinstance(item, dict)
    _reject_unknown(item, _EVIDENCE_KEYS, path)
    _require_keys(item, _EVIDENCE_KEYS, path)
    _check_enum(item["field"], EVIDENCE_FIELDS, f"{path}.field")
    _check_str(item["text"], f"{path}.text", min_length=1)
    _check_enum(item["method"], EVIDENCE_METHODS, f"{path}.method")
    if item["asset_id"] is not None:
        _check_str(item["asset_id"], f"{path}.asset_id", min_length=1)
    bbox = item["bbox"]
    if bbox is not None:
        _require_list(bbox, f"{path}.bbox")
        if len(bbox) != 4:
            raise ContractViolation(f"{path}.bbox: 必须是 4 个数字，实际长度是 {len(bbox)}")
        for i, coord in enumerate(bbox):
            if isinstance(coord, bool) or not isinstance(coord, (int, float)):
                raise ContractViolation(f"{path}.bbox[{i}]: 必须是数字，实际是 {type(coord).__name__}")


def _validate_record(record: object, path: str) -> None:
    _require_dict(record, path)
    assert isinstance(record, dict)
    _reject_unknown(record, _RECORD_KEYS, path)
    _require_keys(record, _RECORD_KEYS, path)
    _check_str(record["record_key"], f"{path}.record_key", min_length=1)
    for field_name in KEY_FIELDS:
        _check_str(record[field_name], f"{path}.{field_name}", allow_none=True)
    _check_enum(record["review_status"], PROCESS_STATUSES, f"{path}.review_status")
    _check_number(record["confidence"], f"{path}.confidence", 0, 1)
    _require_list(record["evidence"], f"{path}.evidence")
    for i, item in enumerate(record["evidence"]):
        _validate_evidence(item, f"{path}.evidence[{i}]")


def validate_article_bundle(bundle: object) -> None:
    """校验 article_bundle.v1；不合法时抛 ContractViolation。"""
    _require_dict(bundle, "article_bundle")
    assert isinstance(bundle, dict)
    _reject_unknown(bundle, _ARTICLE_KEYS, "article_bundle")
    _require_keys(bundle, _ARTICLE_REQUIRED, "article_bundle")
    if bundle["schema_version"] != SCHEMA_ARTICLE:
        raise ContractViolation(
            f"article_bundle.schema_version: 必须是 {SCHEMA_ARTICLE!r}，实际是 {bundle['schema_version']!r}"
        )
    _check_str(bundle["notice_id"], "article_bundle.notice_id", min_length=1)
    _check_str(bundle["title"], "article_bundle.title", min_length=1)
    _check_url(bundle["source_url"], "article_bundle.source_url")
    if bundle["published_at"] is not None:
        _check_datetime(bundle["published_at"], "article_bundle.published_at")
    _check_enum(bundle["content_type"], CONTENT_TYPES, "article_bundle.content_type")
    _check_str(bundle["clean_text"], "article_bundle.clean_text", allow_none=True)
    _require_list(bundle["asset_refs"], "article_bundle.asset_refs")
    for i, ref in enumerate(bundle["asset_refs"]):
        _validate_asset_ref(ref, f"article_bundle.asset_refs[{i}]")
    _check_enum(bundle["fetch_status"], PROCESS_STATUSES, "article_bundle.fetch_status")
    _check_str(bundle["failure_reason"], "article_bundle.failure_reason", allow_none=True)
    if bundle["fetch_status"] == "failed" and not (
        isinstance(bundle["failure_reason"], str) and bundle["failure_reason"]
    ):
        raise ContractViolation(
            "article_bundle.failure_reason: fetch_status=failed 时必须提供非空原因"
        )
    _check_datetime(bundle["fetched_at"], "article_bundle.fetched_at")


def validate_extraction_bundle(bundle: object) -> None:
    """校验 extraction_bundle.v1；不合法时抛 ContractViolation。"""
    _require_dict(bundle, "extraction_bundle")
    assert isinstance(bundle, dict)
    _reject_unknown(bundle, _EXTRACTION_KEYS, "extraction_bundle")
    _require_keys(bundle, _EXTRACTION_REQUIRED, "extraction_bundle")
    if bundle["schema_version"] != SCHEMA_EXTRACTION:
        raise ContractViolation(
            f"extraction_bundle.schema_version: 必须是 {SCHEMA_EXTRACTION!r}，"
            f"实际是 {bundle['schema_version']!r}"
        )
    _check_str(bundle["notice_id"], "extraction_bundle.notice_id", min_length=1)
    _check_str(bundle["extractor_version"], "extraction_bundle.extractor_version", min_length=1)
    _require_list(bundle["records"], "extraction_bundle.records")
    seen_keys: set[str] = set()
    for i, record in enumerate(bundle["records"]):
        _validate_record(record, f"extraction_bundle.records[{i}]")
        assert isinstance(record, dict)
        key = record["record_key"]
        if key in seen_keys:
            raise ContractViolation(f"extraction_bundle.records: record_key {key!r} 在同一 bundle 内重复")
        seen_keys.add(key)
    _check_enum(bundle["processing_status"], PROCESS_STATUSES, "extraction_bundle.processing_status")
    _check_str(bundle["failure_reason"], "extraction_bundle.failure_reason", allow_none=True)
    _check_datetime(bundle["processed_at"], "extraction_bundle.processed_at")
