"""9/23 通用规则修正回归：教育枚举粒度、城市回退链、噪声字符、职务词、归一统一。

每项对应复核队列中的真实错例簇（详见 progress/week1/B/PROGRESS.md 9/23 段），
规则均为通用版式/词典逻辑，不针对单一样本硬编码。
"""

from app.extraction.ocr import OcrBox, OcrPage
from app.extraction.poster_rules import extract_person_fields, records_from_boxes
from app.extraction.evaluation import judge_pair

from tests.extraction.test_poster_rules import StubOcrAdapter, _article, _box, _page


def _fields(lines):
    res, _ = extract_person_fields(lines)
    return {k: v.value for k, v in res.items()}


def test_education_longest_match_and_bare_graduate():
    # 硕士研究生 优先于 硕士（最长命中）
    f = _fields(["2024届湖南选调生", "民族学与社会学学院2021级文物与博物馆学专业硕士研究生"])
    assert f["education"] == "硕士研究生"
    # 裸「研究生」（无硕/博前缀）按硕士研究生
    f = _fields(["2024届天津定向选调生", "外国语学院2022级学科教学（英语）专业研究生"])
    assert f["education"] == "硕士研究生"


def test_major_leading_ocr_noise_stripped():
    # OCR 项目符号噪声（米）混入专业名 → 剥离
    f = _fields(["2023届定向选调生", "中国少数民族语言文学学院2018级维吾尔语专业本科生"])
    assert f["major"] == "维吾尔语"


def test_city_county_fallback_and_noise():
    # 县级回退：单位行/整块无市级地名时取最后一个「XX县」
    f = _fields(["2024届贵州选调生", "管理学院2021级行政管理专业研究生", "贵州省织金县文体广电旅游局"])
    assert f["city"] == "织金"
    # 噪声前缀不进入城市名
    f = _fields(["2024届宁夏选调生", "民族学与社会学学院2020级文物与博物馆学专业本科生",
                 "石嘴山市惠农区红果子镇人民政府", "试用期公务员（不定职级）"])
    assert f["city"] == "石嘴山"


def test_city_joined_fallback_when_unit_line_has_no_city():
    # 单位行（现任职XX镇）无市级地名 → 整块回退在入职行找到「三明市」
    f = _fields(["2024届福建选调生", "民族学与社会学学院2021级社会学专业硕士研究生",
                 "入职福建省三明市宁化县委社会工作部，现任职翠江镇中山村党支部"])
    assert f["city"] == "三明"


def test_unit_line_multi_candidate_disambiguation():
    # 多候选单位行：入职/录用标记行优先，不再误取「现任职」行
    f = _fields(["2024届福建选调生", "民族学与社会学学院2021级社会学专业硕士研究生",
                 "入职福建省三明市宁化县委社会工作部", "现任职翠江镇中山村党支部"])
    assert f["position_or_unit"] == "入职福建省三明市宁化县委社会工作部"


def test_job_title_suffixes_enable_unit_detection():
    # 职务词（书记助理）作为单位行锚点；跨框拼接后仍可定位
    boxes = [
        _box("2024届湖南选调生", 20, 100, 380, 140),
        _box("民族学与社会学学院2021级文物与博物馆学专业硕士研究生", 20, 160, 420, 200),
        _box("湖南省株洲市炎陵县鹿原镇三口村党总支书", 20, 220, 420, 260),
        _box("记助理（不定职级）", 20, 280, 420, 320),
    ]
    adapter = StubOcrAdapter({"x-poster-01": _page("x-poster-01", boxes)})
    bundle = __import__("app.extraction.extractor", fromlist=["Extractor"]) \
        .Extractor(ocr_adapter=adapter).extract(_article(notice_id="x"))
    rec = bundle["records"][0]
    assert rec["position_or_unit"] is not None
    assert "党总支" in rec["position_or_unit"] or "书记助理" in rec["position_or_unit"]


def test_norm_major_tail_and_bracket_width():
    # 专业尾部「专业」粒度差异 → 归一等价（严格仍不等）
    s, n = judge_pair("新闻与传播专业", "新闻与传播", "major")
    assert (s, n) == (0, 1)
    # 括号全半角 → 归一等价（严格不等）
    s, n = judge_pair("法律（法学）", "法律(法学)", "major")
    assert (s, n) == (0, 1)
    # 丢括号内容仍是真错（两个口径都 0）
    s, n = judge_pair("法律（法学）", "法学", "major")
    assert (s, n) == (0, 0)


def test_education_alias_in_norm():
    s, n = judge_pair("硕士研究生", "硕士", "education")
    assert (s, n) == (0, 1)
    s, n = judge_pair("硕士研究生", "硕士研究生", "education")
    assert (s, n) == (1, 1)


def test_text_path_education_longest_match():
    from app.extraction.rules import extract_from_text
    res = extract_from_text("2025届硕士研究生录取名单公布，另有本科同学若干。")
    assert res["education"].value == "硕士研究生"
