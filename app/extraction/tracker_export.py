"""评测报告 -> 验收台账 20样本评测 表的逐行导入格式。

列布局与 docs/week1/05_本周验收台账.xlsx!20样本评测 A14:AB14 完全一致：
A 样本ID | B SHA-256 | C-G 金标准五字段 | H-L OCR各字段0/1 | M OCR完整0/1 |
N OCR秒 | O-S 多模态各字段0/1 | T 多模态完整0/1 | U 多模态秒 | V 单张成本 |
W 备注 | X 标注人 | Y OCR样本ID | Z 多模态样本ID

判定 0/1 来自评测报告 per_sample.judgments（不可判定留空，公式会将其
排除出分母）。注意：台账 AA 校验要求金标准 C-G 全部非空——选样时
应优先选五字段齐全的海报；确有缺失的样本会显示"缺金标准"，如实保留。

用法：python -m app.extraction.tracker_export <report.json> <out.csv>
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

COLUMNS = [
    "样本ID", "图像SHA-256",
    "金标准届别", "金标准学历", "金标准专业", "金标准城市", "金标准岗位",
    "OCR届别", "OCR学历", "OCR专业", "OCR城市", "OCR岗位", "OCR完整", "OCR秒",
    "多模态届别", "多模态学历", "多模态专业", "多模态城市", "多模态岗位",
    "多模态完整", "多模态秒",
    "单张成本", "备注", "标注人", "OCR样本ID", "多模态样本ID",
]

CORE = ("cohort", "education", "major", "city", "position_or_unit")


def _j1(judgments: dict, field: str):
    """judgment 1 -> "1"，0 -> "0"，None -> 空（不可判定不计分母）。"""
    v = judgments.get(field)
    return "" if v is None else str(v)


def export_rows(gold: dict, report: dict) -> list[dict]:
    gold_by_id = {s["sample_id"]: s for s in gold["samples"]}
    ocr_ps = {s["sample_id"]: s for s in report["routes"]["ocr"]["per_sample"]}
    mm_ps = {s["sample_id"]: s for s in report["routes"]["multimodal"]["per_sample"]}

    rows = []
    for sid in sorted(gold_by_id):
        g = gold_by_id[sid]
        o, m = ocr_ps.get(sid, {}), mm_ps.get(sid, {})
        o_j, m_j = o.get("judgments", {}), m.get("judgments", {})
        fields = g["fields"]
        rows.append({
            "样本ID": sid,
            "图像SHA-256": g.get("image_sha256") or "",
            **{f"金标准{label}": fields.get(f) if fields.get(f) is not None else ""
               for label, f in zip(("届别", "学历", "专业", "城市", "岗位"), CORE)},
            **{f"OCR{label}": _j1(o_j, f)
               for label, f in zip(("届别", "学历", "专业", "城市", "岗位"), CORE)},
            "OCR完整": _complete01(o),
            "OCR秒": o.get("elapsed_s") or "",
            **{f"多模态{label}": _j1(m_j, f)
               for label, f in zip(("届别", "学历", "专业", "城市", "岗位"), CORE)},
            "多模态完整": _complete01(m),
            "多模态秒": m.get("elapsed_s") or "",
            "单张成本": (o.get("cost") or m.get("cost") or ""),
            "备注": _note(o, m),
            "标注人": g.get("annotated_by") or "",
            "OCR样本ID": sid if o else "",
            "多模态样本ID": sid if m else "",
        })
    return rows


def _complete01(per_sample: dict) -> str:
    """完整记录 0/1；未判定（无效结果或五字段未全可判定）留空。"""
    if per_sample.get("status") != "judged":
        return ""
    complete = per_sample.get("complete")
    return "" if complete is None else str(int(complete))


def _note(o: dict, m: dict) -> str:
    notes = []
    for name, s in (("OCR", o), ("多模态", m)):
        if s.get("status") == "invalid_result":
            notes.append(f"{name}结果无效")
        elif s.get("status") == "gold_missing":
            notes.append(f"{name}缺该样本")
    return ";".join(notes)


def export_csv(gold_path: Path, report_path: Path, out_path: Path,
               raw_ocr_path: Path | None = None,
               raw_mm_path: Path | None = None) -> Path:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # 逐样本耗时从两条路线的原始文件补齐（同一路线同计时边界）
    for route_key, raw_path in (("ocr", raw_ocr_path), ("multimodal", raw_mm_path)):
        if raw_path is None or not Path(raw_path).exists():
            continue
        raw = {r["sample_id"]: r for r in
               json.loads(Path(raw_path).read_text(encoding="utf-8"))["sample_results"]}
        for s in report["routes"][route_key]["per_sample"]:
            r = raw.get(s["sample_id"])
            if r and s.get("status") == "judged":
                s["elapsed_s"] = r.get("elapsed_s", "")
    rows = export_rows(gold, report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print(__doc__)
        return 2
    gold, report, out = Path(args[0]), Path(args[1]), Path(args[2]) if len(args) > 2 else Path("reports/extraction/tracker_import.csv")
    path = export_csv(
        gold, report, out,
        raw_ocr_path=Path(args[3]) if len(args) > 3 else None,
        raw_mm_path=Path(args[4]) if len(args) > 4 else None)
    print(f"tracker import written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
