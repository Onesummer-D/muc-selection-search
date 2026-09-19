"""切片3测试：海报版面规则、一帖多人、OCR 状态与混合路径。

测试注入的是「OCR 识别框结果」（外部引擎输出），版面分组与字段规则本身
走真实实现，不 mock 被测抽取器。
"""

import pytest

from app.extraction import Extractor, validate_bundle
from app.extraction.ocr import OcrBox, OcrPage


def _article(content_type="poster", asset_refs=None, clean_text=None,
             notice_id="247919"):
    return {
        "schema_version": "article_bundle.v1",
        "notice_id": notice_id,
        "title": "经验分享",
        "source_url": "https://my.muc.edu.cn/notice/247919",
        "published_at": "2026-09-10 08:00",
        "content_type": content_type,
        "clean_text": clean_text,
        "asset_refs": asset_refs if asset_refs is not None else [
            {"asset_id": f"{notice_id}-poster-01", "kind": "poster",
             "local_ref": f"private://{notice_id}/poster-01", "sha256": "a" * 64}],
        "fetch_status": "processed",
        "failure_reason": None,
        "fetched_at": "2026-09-17T20:30:00+08:00",
    }


class StubOcrAdapter:
    """把预设的识别框结果按 asset_id 注入；记录调用次数用于幂等测试。"""

    name = "stub"

    def __init__(self, pages_by_asset, fail=None, empty=None):
        self.pages = pages_by_asset
        self.fail = fail or set()
        self.empty = empty or set()
        self.calls = 0

    def extract_records(self, article):
        self.calls += 1
        records = []
        index = 0
        for asset in article.get("asset_refs", []):
            aid = asset["asset_id"]
            if aid in self.fail:
                return [], f"ocr_error:RuntimeError"
            if aid in self.empty:
                return [], "ocr_empty"
            page = self.pages[aid]
            from app.extraction.poster_rules import records_from_boxes
            page_records = records_from_boxes(article["notice_id"], page, index)
            index += len(page_records)
            records.extend(page_records)
        return records, None


def _page(asset_id, boxes):
    return OcrPage(asset_id=asset_id, boxes=boxes)


def _box(text, x0, y0, x1, y1, conf=0.95):
    return OcrBox(text=text, confidence=conf, bbox=[x0, y0, x1, y1])


def _single_person_boxes():
    return [
        _box("选调经验分享会", 20, 20, 300, 60),          # 标题块，应被跳过
        _box("姓名：李某某  2024届", 20, 100, 380, 140),
        _box("学历：本科  专业：软件工程", 20, 160, 380, 200),
        _box("信息学院", 20, 220, 380, 250),
        _box("工作地点：成都  录用为成都市某区基层岗位", 20, 280, 420, 320),
    ]


def test_single_person_poster_creates_one_record_with_bbox_evidence():
    adapter = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01",
                                                        _single_person_boxes())})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())
    errors = validate_bundle(bundle)
    assert errors == [], errors
    assert len(bundle["records"]) == 1
    rec = bundle["records"][0]
    assert rec["cohort"] == "2024届"
    assert rec["education"] == "本科"
    assert rec["major"] == "软件工程"
    assert rec["college"] == "信息学院"
    assert rec["city"] == "成都"
    assert rec["position_or_unit"] == "成都市某区基层岗位"
    assert rec["review_status"] == "processed"
    assert rec["record_key"] == "247919-01"
    city_ev = next(e for e in rec["evidence"] if e["field"] == "city")
    assert city_ev["method"] == "ocr_rule"
    assert city_ev["asset_id"] == "247919-poster-01"
    assert city_ev["bbox"] == [20, 280, 420, 320]


def test_multi_person_poster_creates_distinct_record_keys():
    boxes = _single_person_boxes() + [
        _box("姓名：王某  2025届", 20, 420, 380, 460),
        _box("学历：硕士  专业：法学", 20, 480, 380, 520),
        _box("工作地点：兰州  录用为甘肃省直机关岗位", 20, 540, 420, 580),
    ]
    adapter = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())
    assert len(bundle["records"]) == 2
    k1, k2 = bundle["records"][0]["record_key"], bundle["records"][1]["record_key"]
    assert k1 == "247919-01" and k2 == "247919-02" and k1 != k2
    majors = {r["major"] for r in bundle["records"]}
    assert majors == {"软件工程", "法学"}  # 互不混淆


def test_missing_fields_stay_null_and_go_to_review():
    boxes = [_box("2024届本科生", 20, 100, 380, 140)]
    adapter = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())
    rec = bundle["records"][0]
    assert rec["major"] is None and rec["city"] is None
    assert rec["position_or_unit"] is None
    assert rec["review_status"] == "review_required"
    assert bundle["processing_status"] == "review_required"


def test_conflicting_city_values_not_picked():
    boxes = [
        _box("2024届 本科 软件工程", 20, 100, 380, 140),
        _box("工作地点：成都", 20, 160, 380, 200),
        _box("工作地点：北京", 20, 220, 380, 260),
    ]
    adapter = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())
    rec = bundle["records"][0]
    assert rec["city"] is None
    city_texts = " ".join(e["text"] for e in rec["evidence"] if e["field"] == "city")
    assert "成都" in city_texts and "北京" in city_texts
    assert rec["review_status"] == "review_required"


def test_low_confidence_ocr_goes_to_review():
    boxes = _single_person_boxes()
    # 把关键字段框的 OCR 置信度降到阈值以下
    boxes[4] = _box("工作地点：成都  录用为成都市某区基层岗位", 20, 280, 420, 320, conf=0.40)
    adapter = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article())
    rec = bundle["records"][0]
    assert rec["review_status"] == "review_required"


def test_ocr_failure_and_empty_produce_failed_status():
    fail = StubOcrAdapter({}, fail={"247919-poster-01"})
    b = Extractor(ocr_adapter=fail).extract(_article())
    assert b["processing_status"] == "failed" and b["failure_reason"].startswith("ocr_error")

    empty = StubOcrAdapter({}, empty={"247919-poster-01"})
    b = Extractor(ocr_adapter=empty).extract(_article())
    assert b["processing_status"] == "failed" and b["failure_reason"] == "ocr_empty"


def test_repeated_processing_keeps_record_keys_stable():
    boxes = _single_person_boxes() + [
        _box("姓名：王某  2025届", 20, 420, 380, 460),
        _box("学历：硕士  专业：法学", 20, 480, 380, 520),
    ]
    adapter1 = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    adapter2 = StubOcrAdapter({"247919-poster-01": _page("247919-poster-01", boxes)})
    b1 = Extractor(ocr_adapter=adapter1).extract(_article())
    b2 = Extractor(ocr_adapter=adapter2).extract(_article())
    assert [r["record_key"] for r in b1["records"]] == \
           [r["record_key"] for r in b2["records"]]


def test_mixed_poster_keeps_both_html_and_ocr_evidence():
    text = "线上说明会文字稿：2025届本科生，专业软件工程，录用为成都的基层岗位。"
    adapter = StubOcrAdapter({"348879-poster-01": _page(
        "348879-poster-01", [_box("补充：学历硕士 专业法学 工作地点兰州", 20, 100, 380, 140)])})
    article = _article(content_type="mixed", clean_text=text, notice_id="348879")
    bundle = Extractor(ocr_adapter=adapter).extract(article)
    assert validate_bundle(bundle) == []
    methods = {e["method"] for r in bundle["records"] for e in r["evidence"]}
    assert "html_rule" in methods and "ocr_rule" in methods
    assert len(bundle["records"]) == 2  # 正文一人 + 海报一人
