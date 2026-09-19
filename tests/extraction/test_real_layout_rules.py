"""真实海报版式驱动的规则补强测试（通用模式，非针对特定样本硬编码）。"""

from app.extraction import Extractor, validate_bundle
from app.extraction.ocr import OcrBox, OcrPage

from tests.extraction.test_poster_rules import StubOcrAdapter, _article, _box, _page


def test_city_pattern_catches_prefecture_unit_line():
    """词典没有临汾；单位行「山西省临汾市城联社」应由通用城市模式命中。"""
    boxes = [
        _box("牛某某 2024届", 20, 100, 380, 140),
        _box("生命与环境科学学院2020级环境科学专业本科生", 20, 160, 420, 200),
        _box("山西省临汾市城联社", 20, 220, 380, 260),
        _box("试用期公务员（不定职级）", 20, 280, 380, 320),
    ]
    adapter = StubOcrAdapter({"x-poster-01": _page("x-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(
        _article(notice_id="x"))
    rec = bundle["records"][0]
    assert rec["city"] == "临汾"          # 去后缀，与词典口径一致
    assert rec["major"] == "环境科学"      # 「XX专业」模式
    assert rec["position_or_unit"] == "山西省临汾市城联社"  # 机构后缀单位行
    assert rec["cohort"] == "2024届"
    assert validate_bundle(bundle) == []


def test_major_suffix_pattern_and_unit_line_variants():
    boxes = [
        _box("赵某某 2024届", 20, 100, 380, 140),
        _box("文学院2021级汉语言文字学专业硕士研究生", 20, 160, 420, 200),
        _box("唐山市纪委监委", 20, 220, 380, 260),
    ]
    adapter = StubOcrAdapter({"x-poster-01": _page("x-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article(notice_id="x"))
    rec = bundle["records"][0]
    assert rec["major"] == "汉语言文字学"
    assert rec["college"] == "文学院"
    assert rec["position_or_unit"] == "唐山市纪委监委"
    assert rec["city"] == "唐山"


def test_city_conflict_stays_null_with_pattern_hits():
    boxes = [
        _box("2024届 本科 软件工程专业", 20, 100, 380, 140),
        _box("临汾市城联社", 20, 160, 380, 200),
        _box("大同市财政局", 20, 220, 380, 260),
    ]
    adapter = StubOcrAdapter({"x-poster-01": _page("x-poster-01", boxes)})
    bundle = Extractor(ocr_adapter=adapter).extract(_article(notice_id="x"))
    rec = bundle["records"][0]
    assert rec["city"] is None  # 两个地级市 → 冲突保留候选
    assert rec["review_status"] == "review_required"


def test_prefecture_city_eval_norm_matches_gold_with_suffix():
    """金标准写「临汾市」、抽取值「临汾」→ 判定等价正确。"""
    from app.extraction.evaluation import judge_field
    assert judge_field("临汾市", "临汾") == 1
    assert judge_field("临汾", "临汾市") == 1
    assert judge_field("硕士", "硕士研究生") == 1
    assert judge_field("临汾", "大同") == 0
