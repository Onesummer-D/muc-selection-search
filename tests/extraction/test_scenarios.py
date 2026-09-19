"""切片4测试：任务书 8 场景收尾——模糊OCR、unknown 类型、证据缺失红绿、evidence pack。"""

import copy

from app.extraction import Extractor, validate_bundle
from app.extraction.evidence import build_evidence_pack
from app.extraction.ocr import OcrBox, OcrPage

from test_poster_rules import StubOcrAdapter, _article, _box, _page


def test_fuzzy_ocr_text_yields_failure_not_garbage():
    """模糊 OCR：识别出的全是乱码 → 无字段命中 → 如实 failed，不猜值。"""
    boxes = [_box("称掇面鲺设鎏鎏", 20, 100, 380, 140, conf=0.35),
             _box("鎏设鲺称掇", 20, 160, 380, 200, conf=0.30)]
    adapter = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())
    assert bundle["records"] == []
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"] == "no_records_extracted"


def test_unknown_content_type_fails_with_reason():
    bundle = Extractor().extract(_article(content_type="unknown", clean_text=None))
    assert bundle["processing_status"] == "failed"
    assert bundle["failure_reason"] == "unknown_content_type"
    assert validate_bundle(bundle) == []


def test_removing_required_evidence_makes_schema_red_then_green():
    """任务书要求：故意删一条必填证据，Schema 必须变红；还原后全绿。"""
    adapter = StubOcrAdapter({"247919-poster-01": _page(
        "247919-poster-01",
        [_box("2024届 本科 软件工程 工作地点成都", 20, 100, 420, 140)])})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())

    # 绿：原始 bundle 通过
    assert validate_bundle(bundle) == []

    # 红：删掉 records[0].evidence 整个必填属性
    broken = copy.deepcopy(bundle)
    del broken["records"][0]["evidence"]
    assert validate_bundle(broken) != []

    # 红：证据项缺 text（minLength 要求）
    broken2 = copy.deepcopy(bundle)
    del broken2["records"][0]["evidence"][0]["text"]
    assert validate_bundle(broken2) != []

    # 还原后全绿：原始对象未被打补丁
    assert validate_bundle(bundle) == []


def test_evidence_pack_contains_required_keys_and_null_fields_stay_null():
    text = "2025届软件工程本科生，录用为成都的基层岗位。"
    article = _article(content_type="text", clean_text=text, notice_id="352508")
    bundle = Extractor().extract(article)
    packs = build_evidence_pack(article, bundle)
    assert len(packs) == 1
    pack = packs[0]
    for key in ("record_key", "notice_id", "fields", "field_evidence",
                "source_url", "review_status"):
        assert key in pack
    assert pack["record_key"] == "352508-01"
    assert pack["notice_id"] == "352508"
    assert pack["source_url"] == article["source_url"]
    assert pack["fields"]["cohort"] == "2025届"
    assert pack["fields"]["city"] == "成都"
    # 原文没有的城市类信息在 pack 里保持 null，不进入可回答上下文
    assert pack["fields"]["grade"] is None
    ev = pack["field_evidence"]["cohort"][0]
    assert ev["method"] == "html_rule" and ev["text"]


def test_no_evidence_means_no_non_null_field_value():
    """任何非空字段值都必须有证据（任务书：无证据不得返回非空值）。"""
    texts = [
        "2024届本科生，专业软件工程，录用为成都的基层岗位。",
        "2025届硕士毕业生，专业法学，任职于兰州的单位。",
        "2023届本科，会计学，岗位：南宁某单位。",
    ]
    for text in texts:
        bundle = Extractor().extract(_article(clean_text=text))
        for rec in bundle["records"]:
            ev_fields = {e["field"] for e in rec["evidence"]}
            for f in ("cohort", "education", "major", "city", "position_or_unit"):
                if rec[f] is not None:
                    assert f in ev_fields, f"{f}={rec[f]} 但无证据"
