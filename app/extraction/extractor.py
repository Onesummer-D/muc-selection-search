"""抽取编排：按 content_type 分流，产出 extraction_bundle.v1。

- text   → html_rule（本文件实现）
- poster → ocr_adapter 必须提供；缺失时整篇 failed，failure_reason=missing_ocr_adapter
- mixed  → 正文 html_rule + 海报 ocr_rule，两类证据都保留
- unknown→ failed，failure_reason=unknown_content_type

一篇文章可产出多条人物记录，record_key = {notice_id}-{NN}，重复处理保持稳定。
"""

from __future__ import annotations

from . import rules
from .bundle import now_iso

CONFIDENCE_THRESHOLD = 0.60

# Schema 要求的七个字段
ALL_FIELDS = ("cohort", "grade", "education", "college", "major",
              "city", "position_or_unit")
CORE_FIELDS = ("cohort", "education", "major", "city", "position_or_unit")


def _record_key(notice_id: str, index: int) -> str:
    return f"{notice_id}-{index + 1:02d}"


def _build_record(notice_id: str, index: int, field_results,
                  method: str, asset_id: str | None, bbox=None) -> dict:
    evidence = []
    for fname, res in field_results.items():
        for ev in res.evidence:
            evidence.append({
                "field": fname,
                "text": ev["text"],
                "method": method,
                "asset_id": asset_id,
                "bbox": ev.get("bbox", bbox),
            })

    missing_core = any(fr.value is None and fr.confidence == 0.0 and not fr.conflict
                       for fr in (field_results.get(f) for f in CORE_FIELDS))
    has_conflict = any(fr.conflict for fr in field_results.values())
    values_ok = all(field_results[f].value is not None for f in CORE_FIELDS)
    low_conf = any(
        field_results[f].value is not None and field_results[f].confidence < CONFIDENCE_THRESHOLD
        for f in CORE_FIELDS
    )

    if missing_core or has_conflict or low_conf:
        status = "review_required"
        confidence = round(
            min((field_results[f].confidence for f in CORE_FIELDS), default=0.0), 2
        ) if not has_conflict else 0.0
    elif values_ok:
        status = "processed"
        confidence = round(min(field_results[f].confidence for f in CORE_FIELDS), 2)
    else:
        status = "review_required"
        confidence = 0.0

    record = {"record_key": _record_key(notice_id, index)}
    for fname in ALL_FIELDS:
        res = field_results.get(fname)
        record[fname] = res.value if res is not None else None
    record["review_status"] = status
    record["confidence"] = confidence
    record["evidence"] = evidence
    return record


class Extractor:
    """可注入 ocr_adapter（切片3 实现 PaddleOCR 版本）的确定性抽取器。"""

    extractor_version = "rule-extract-0.1.0"

    def __init__(self, ocr_adapter=None):
        self.ocr_adapter = ocr_adapter

    def extract(self, article: dict) -> dict:
        notice_id = article["notice_id"]
        content_type = article.get("content_type", "unknown")
        records: list[dict] = []
        failure_reason = None

        if content_type == "text":
            records = self._extract_text(article)
        elif content_type == "poster":
            records, failure_reason = self._extract_poster(article)
        elif content_type == "mixed":
            records, failure_reason = self._extract_mixed(article)
        else:
            failure_reason = "unknown_content_type"

        if failure_reason and not records:
            processing_status = "failed"
        elif not records:
            failure_reason = "no_records_extracted"
            processing_status = "failed"
        elif any(r["review_status"] != "processed" for r in records):
            processing_status = "review_required"
        else:
            processing_status = "processed"

        return {
            "schema_version": "extraction_bundle.v1",
            "notice_id": notice_id,
            "extractor_version": self.extractor_version,
            "records": records,
            "processing_status": processing_status,
            "failure_reason": failure_reason,
            "processed_at": now_iso(),
        }

    # ---- text：html_rule ----
    def _extract_text(self, article: dict) -> list[dict]:
        clean_text = article.get("clean_text")
        if not clean_text:
            return []
        results = rules.extract_from_text(clean_text)
        return [_build_record(article["notice_id"], 0, results,
                              method="html_rule", asset_id=None, bbox=None)]

    # ---- poster / mixed：依赖 ocr_adapter ----
    def _call_adapter(self, article):
        """适配器异常（超时/引擎崩溃）转为 failed 状态，不让批处理中断。"""
        try:
            return self.ocr_adapter.extract_records(article)
        except TimeoutError:
            return [], "adapter_error:TimeoutError"
        except Exception as exc:
            return [], f"adapter_error:{type(exc).__name__}"

    def _extract_poster(self, article):
        if self.ocr_adapter is None:
            return [], "missing_ocr_adapter"
        return self._call_adapter(article)

    def _extract_mixed(self, article):
        records = self._extract_text(article)
        if self.ocr_adapter is None:
            # 混合帖正文已抽到即保留正文记录；海报路径缺失如实标记
            return records, "missing_ocr_adapter"
        poster_records, failure = self._call_adapter(article)
        records.extend(poster_records)
        # 两条路径各自从 -01 编号会撞 record_key，合并后按顺序统一重编号
        for i, r in enumerate(records):
            r["record_key"] = _record_key(article["notice_id"], i)
        return records, failure
