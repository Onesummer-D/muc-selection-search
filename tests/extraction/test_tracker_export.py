"""切片8测试：评测报告 -> 台账 20样本评测 导入格式。"""

import csv
import json

from app.extraction.evaluation import RouteRaw, evaluate_route, run_evaluation
from app.extraction.tracker_export import COLUMNS, export_csv


def _gold():
    samples = []
    for i in range(1, 21):
        samples.append({
            "sample_id": f"P{i:02d}",
            "image_sha256": "a" * 64,
            "annotated_by": "B-annotator-1",
            "fields": {"cohort": "2025届", "education": "本科",
                       "major": "软件工程" if i <= 10 else None,
                       "city": "成都", "position_or_unit": "基层岗位"},
        })
    return {"sample_set": "week1-poster-gold-20", "samples": samples}


def _route_raw(right_major_count):
    """cohort/city/position/education 全对；major 前 right_major_count 对。"""
    results = []
    for i in range(1, 21):
        results.append({
            "sample_id": f"P{i:02d}", "valid": True,
            "elapsed_s": 1.0 + i / 100, "cost": 0.01,
            "fields": {"cohort": "2025届", "education": "本科",
                       "major": "软件工程" if i <= right_major_count else "错值",
                       "city": "成都", "position_or_unit": "基层岗位"},
        })
    return {"sample_results": results}


def test_tracker_export_matches_excel_columns_and_zero_one(tmp_path):
    gold = _gold()
    gp = tmp_path / "gold.json"
    gp.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")

    ocr_raw = _route_raw(14)   # major 14/20 对（10 个可判定中 10 对——major 金标准只有 P01-P10）
    mm_raw = _route_raw(10)
    op, mp = tmp_path / "ocr.json", tmp_path / "mm.json"
    op.write_text(json.dumps(ocr_raw, ensure_ascii=False), encoding="utf-8")
    mp.write_text(json.dumps(mm_raw, ensure_ascii=False), encoding="utf-8")

    report = run_evaluation(gp, op, mp, tmp_path / "report.json")
    rp = tmp_path / "report.json"
    out = export_csv(gp, rp, tmp_path / "tracker.csv", raw_ocr_path=op, raw_mm_path=mp)

    with open(out, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 20
    assert list(rows[0].keys()) == COLUMNS

    r1 = rows[0]
    assert r1["样本ID"] == "P01"
    assert r1["图像SHA-256"] == "a" * 64
    assert r1["金标准届别"] == "2025届" and r1["金标准学历"] == "本科"
    # OCR 路线 P01：五字段全对 → 各字段 1、完整 1
    assert (r1["OCR届别"], r1["OCR学历"], r1["OCR专业"],
            r1["OCR城市"], r1["OCR岗位"], r1["OCR完整"]) == ("1", "1", "1", "1", "1", "1")
    assert r1["OCR样本ID"] == "P01"
    assert r1["OCR秒"] != ""  # 耗时来自原始文件，不手填
    # 多模态路线 P01 全对
    assert r1["多模态完整"] == "1"
    assert r1["标注人"] == "B-annotator-1"


def test_undecidable_fields_stay_blank_in_tracker(tmp_path):
    """major 金标准只有 P01-P10 → P11+ 的 major 判定留空（公式排除出分母）。"""
    gold = _gold()
    gp = tmp_path / "gold.json"
    gp.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    ocr_raw = _route_raw(8)
    op = tmp_path / "ocr.json"
    op.write_text(json.dumps(ocr_raw, ensure_ascii=False), encoding="utf-8")
    mm_raw = _route_raw(9)
    mp = tmp_path / "mm.json"
    mp.write_text(json.dumps(mm_raw, ensure_ascii=False), encoding="utf-8")
    report = run_evaluation(gp, op, mp, tmp_path / "report.json")

    out = export_csv(gp, tmp_path / "report.json", tmp_path / "tracker.csv",
                     raw_ocr_path=op, raw_mm_path=mp)
    with open(out, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    r11 = rows[10]  # P11：major 金标准 null → 不可判定
    assert r11["金标准专业"] == "" and r11["OCR专业"] == ""
    # 完整判定：P11 金标准缺 major → 整条不可判定 → 留空
    assert r11["OCR完整"] == ""
    # 可判定样本 P01-P08 major 全对 → 1
    r01 = rows[0]
    assert r01["OCR专业"] == "1"


def test_invalid_route_result_marks_note_and_blank_ids(tmp_path):
    gold = _gold()
    gp = tmp_path / "gold.json"
    gp.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    ocr_raw = _route_raw(10)
    ocr_raw["sample_results"][4]["valid"] = False  # P05 OCR 无效
    op = tmp_path / "ocr.json"
    op.write_text(json.dumps(ocr_raw, ensure_ascii=False), encoding="utf-8")
    mm_raw = _route_raw(10)
    mp = tmp_path / "mm.json"
    mp.write_text(json.dumps(mm_raw, ensure_ascii=False), encoding="utf-8")
    run_evaluation(gp, op, mp, tmp_path / "report.json")

    out = export_csv(gp, tmp_path / "report.json", tmp_path / "tracker.csv",
                     raw_ocr_path=op, raw_mm_path=mp)
    with open(out, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    r5 = rows[4]
    assert "OCR结果无效" in r5["备注"]
    assert r5["OCR完整"] == ""  # 无效结果不参与判定
