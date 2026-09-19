"""切片2测试：html_rule 文本路径、bundle 组装与 Schema 校验。"""

import json
from pathlib import Path

import pytest

from app.extraction import Extractor, validate_bundle


def _article(text, notice_id="247001", content_type="text"):
    return {
        "schema_version": "article_bundle.v1",
        "notice_id": notice_id,
        "title": "经验分享",
        "source_url": "https://my.muc.edu.cn/notice/247001",
        "published_at": "2026-09-10 08:00",
        "content_type": content_type,
        "clean_text": text,
        "asset_refs": [],
        "fetch_status": "processed",
        "failure_reason": None,
        "fetched_at": "2026-09-17T20:30:00+08:00",
    }


CLEAR_TEXT = (
    "2025届计算机科学与技术专业本科生小李，经学校推荐报考四川省选调生，"
    "录用为成都市某区基层岗位。信息学院辅导员全程指导。"
)


def test_text_article_extracts_fields_with_html_rule_evidence():
    bundle = Extractor().extract(_article(CLEAR_TEXT))
    errors = validate_bundle(bundle)
    assert errors == [], errors
    assert len(bundle["records"]) == 1
    rec = bundle["records"][0]
    assert rec["cohort"] == "2025届"
    assert rec["education"] == "本科"
    assert rec["major"] == "计算机科学与技术"
    assert rec["college"] == "信息学院"
    assert rec["city"] == "成都"
    assert rec["position_or_unit"] == "成都市某区基层岗位"
    assert rec["review_status"] == "processed"
    assert rec["record_key"] == "247001-01"
    # 每个非空字段都有 html_rule 证据
    ev_fields = {e["field"] for e in rec["evidence"]}
    for f in ("cohort", "education", "major", "city", "position_or_unit"):
        assert f in ev_fields
    for e in rec["evidence"]:
        assert e["method"] == "html_rule"
        assert e["text"]
        assert e["asset_id"] is None and e["bbox"] is None


def test_missing_field_is_null_and_goes_to_review():
    text = "2024届本科生，从信息学院毕业。"  # 无城市、无专业、无岗位
    bundle = Extractor().extract(_article(text))
    rec = bundle["records"][0]
    assert rec["city"] is None
    assert rec["position_or_unit"] is None
    assert rec["review_status"] == "review_required"
    assert bundle["processing_status"] == "review_required"


def test_conflicting_values_keep_candidates_and_null():
    text = "有同学录用为成都的岗位，也有同学录用为北京的岗位，均为2025届本科生，专业软件工程。"
    bundle = Extractor().extract(_article(text))
    rec = bundle["records"][0]
    assert rec["city"] is None  # 不擅自选
    city_ev = [e for e in rec["evidence"] if e["field"] == "city"]
    texts = " ".join(e["text"] for e in city_ev)
    assert "成都" in texts and "北京" in texts  # 候选证据保留
    assert rec["review_status"] == "review_required"


def test_publication_date_is_not_taken_as_cohort():
    text = "2026-09-10发布。本科毕业生考取选调生，录用为兰州的基层岗位，专业法学。"
    bundle = Extractor().extract(_article(text))
    rec = bundle["records"][0]
    assert rec["cohort"] is None  # 原文没有「XX届」
    assert rec["review_status"] == "review_required"


def test_fullwidth_cohort_is_normalized():
    text = "２０２３届本科生，专业会计学，录用为南宁的单位岗位。"
    bundle = Extractor().extract(_article(text))
    rec = bundle["records"][0]
    assert rec["cohort"] == "2023届"


def test_empty_text_yields_empty_records():
    bundle = Extractor().extract(_article("", notice_id="247002"))
    assert bundle["records"] == []
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"]


def test_poster_without_ocr_adapter_fails_honestly():
    bundle = Extractor().extract(_article(None, content_type="poster"))
    assert bundle["records"] == []
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"] == "missing_ocr_adapter"
    assert validate_bundle(bundle) == []


def test_bundle_validates_against_repo_schema():
    """组装结果必须通过仓库里的 extraction_bundle.v1.schema.json。"""
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas" / "extraction_bundle.v1.schema.json")
        .read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "extraction_bundle.v1"
    bundle = Extractor().extract(_article(CLEAR_TEXT))
    assert validate_bundle(bundle) == []


def test_record_key_is_stable_across_runs():
    b1 = Extractor().extract(_article(CLEAR_TEXT))
    b2 = Extractor().extract(_article(CLEAR_TEXT))
    assert [r["record_key"] for r in b1["records"]] == \
           [r["record_key"] for r in b2["records"]]
