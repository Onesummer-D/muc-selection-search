"""Evidence pack：每条人物记录生成供 C 检索的证据包。

至少包含 record_key、notice_id、结构化字段、字段证据数组、来源 URL 和复核状态。
无证据的字段值为 null，不进入回答上下文。
"""

from __future__ import annotations

from .extractor import ALL_FIELDS, CORE_FIELDS


def build_evidence_pack(article: dict, bundle: dict) -> list[dict]:
    source_url = article.get("source_url")
    packs = []
    for record in bundle["records"]:
        field_evidence = {}
        for ev in record.get("evidence", []):
            field_evidence.setdefault(ev["field"], []).append({
                "text": ev["text"],
                "method": ev["method"],
                "asset_id": ev["asset_id"],
                "bbox": ev["bbox"],
            })
        packs.append({
            "record_key": record["record_key"],
            "notice_id": bundle["notice_id"],
            "fields": {f: record[f] for f in ALL_FIELDS},
            "core_fields": list(CORE_FIELDS),
            "field_evidence": field_evidence,
            "source_url": source_url,
            "review_status": record["review_status"],
            "confidence": record["confidence"],
        })
    return packs
