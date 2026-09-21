"""等价预标表生成（PR 终版验收·第四部分执行流程）。

从评测报告的 per_sample 生成 strict-fail 项的预标表：
列 = 样本/字段/抽取输出/金标准/AI预标/理由/人工确认（留空待标注人抽查）。
AI 预标规则：norm=1 → "等价✅"（理由=匹配到的等价规则）；norm=0 → "真错❌"。
同时产出 equivalence_adjudicated.json 草稿（human_confirmed=false，
标注人抽查确认后置 true，评测重算时才采纳）。

用法：python -m app.extraction.gen_equivalence_table
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ("cohort", "education", "major", "city", "position_or_unit")
LABEL = {"cohort": "届别", "education": "学历", "major": "专业", "city": "城市",
         "position_or_unit": "岗位", "grade": "年级", "college": "学院"}


def person_value(item: dict, sid: str, field: str) -> str:
    return ""


def main() -> int:
    report = json.loads(
        (ROOT / "reports" / "extraction" / "evaluation_report.json")
        .read_text(encoding="utf-8"))
    gold = json.loads(
        (ROOT / "data" / "gold" / "gold_20.json").read_text(encoding="utf-8"))
    gold_by = {s["sample_id"]: s for s in gold["samples"]}

    rows = []
    adjudicated = {"human_confirmed": False,
                   "confirmed_by": None,
                   "rules": "PR 终版验收·第三部分统一裁决口径",
                   "entries": []}
    for route in ("ocr", "multimodal"):
        m = report["routes"][route]
        raw_by = {i["sample_id"]: i for i in
                  json.loads((ROOT / "reports" / "extraction" / "eval_raw"
                              / f"{route}.json").read_text(encoding="utf-8"))
                  ["sample_results"]}
        for ps in m["per_sample"]:
            if ps.get("status") != "judged":
                continue
            sid = ps["sample_id"]
            item = raw_by.get(sid, {})
            ext_persons = item.get("persons") or []
            gold_persons = gold_by[sid].get("persons", [])
            for f in CORE:
                j = ps.get("judgments", {}).get(f)
                jn = ps.get("judgments_norm", {}).get(f)
                if j != 0:
                    continue  # 只预标 strict-fail 项
                # 抽取输出与金标准（逐人物对齐展示）
                ext_vals = [p.get(f) for p in ext_persons] or [None]
                gold_vals = [p.get(f) for p in gold_persons] or [None]
                if f in ("education", "major", "position_or_unit"):
                    rule = ("金标准⊆输出（简称/全称细化）" if jn == 1
                            else "输出与金标准无包含关系（逐字要求）")
                elif f == "city":
                    rule = ("唯一识别同一城市（±市后缀/更细地址）" if jn == 1
                            else "另一行政实体或未识别")
                else:
                    rule = ("同义/后缀归一" if jn == 1 else "值不同")
                rows.append({
                    "路线": route,
                    "样本": sid,
                    "字段": LABEL.get(f, f),
                    "抽取输出": " | ".join(str(v) for v in ext_vals),
                    "金标准": " | ".join(str(v) for v in gold_vals),
                    "AI预标": "等价✅" if jn == 1 else "真错❌",
                    "理由": rule,
                    "人工确认": "",
                })
                if jn == 1:
                    adjudicated["entries"].append({
                        "route": route, "sample_id": sid, "field": f,
                        "adjudication": "等价",
                        "extracted": ext_vals, "gold": gold_vals,
                        "reason": rule, "human_confirmed": None,
                    })

    out = ROOT / "reports" / "extraction" / "equivalence_pending.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (ROOT / "data" / "gold" / "equivalence_adjudicated.json").write_text(
        json.dumps(adjudicated, ensure_ascii=False, indent=2), encoding="utf-8")

    n_eq = sum(1 for r in rows if r["AI预标"] == "等价✅")
    print(f"预标表 {len(rows)} 行（等价✅ {n_eq} / 真错❌ {len(rows)-n_eq}）")
    print(f"  -> {out.relative_to(ROOT)}")
    print(f"  -> data/gold/equivalence_adjudicated.json（草稿，human_confirmed=false）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
