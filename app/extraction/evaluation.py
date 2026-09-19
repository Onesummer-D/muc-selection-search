"""20 样本对照评测：从逐样本原始结果重算全部指标。

设计约束（B 任务书「多模态对照」）：
- 汇总必须能从逐样本 0/1 判断重新计算，不接受手填百分比；
- 字段准确率 = 该字段正确数 / 该字段可判定金标准数（gold 为 null 不计分，但报告分母）；
- 完整记录 = 五个核心字段全部正确；
- 成功率 = 产生结构合法结果的样本数 / 20（失败样本不从分母删除）；
- 耗时取每样本原始记录，两路线同一计时边界（收到 article 到产出 bundle）；
- 多模态启用门槛 = 多模态完整记录准确率 − OCR 完整记录准确率 ≥ 5 个百分点。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import fields as F

CORE = ("cohort", "education", "major", "city", "position_or_unit")
GATE_PP = 5.0  # 启用门槛，百分点


@dataclass
class RouteRaw:
    """一条路线在 20 样本上的原始结果（评测的唯一输入，禁止手填汇总）。"""

    route_name: str
    sample_results: list[dict] = field(default_factory=list)
    # 每项：{"sample_id": "P01", "valid": bool, "elapsed_s": float, "cost": float,
    #        "fields": {"cohort": "2025届"|null, ...}}


def _norm(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip().replace(" ", "")
    # 学历等价归一：硕士研究生→硕士、博士研究生→博士（台账枚举含两种写法）
    s = F.EDUCATION_ALIAS.get(s, s)
    # 城市口径归一：去「市/州/盟/地区」后缀（临汾市 == 临汾）。
    # 仅当整体形如地名时生效；岗位单位名以机构后缀结尾，不受影响。
    for suffix in ("地区", "盟", "州", "市"):
        if s.endswith(suffix) and len(s) > len(suffix) + 1:
            return s[: -len(suffix)]
    return s


def judge_field(gold_value, extracted_value) -> int | None:
    """返回 1=正确，0=错误，None=不可判定（gold 缺失，不计分母）。"""
    if gold_value is None:
        return None
    return 1 if _norm(extracted_value) == _norm(gold_value) else 0


def evaluate_route(gold: dict, raw: RouteRaw) -> dict:
    """逐样本逐字段打分并汇总；任何缺失如实进入对应状态。"""
    gold_by_id = {s["sample_id"]: s for s in gold["samples"]}
    per_sample = []
    field_correct = {f: 0 for f in CORE}
    field_decidable = {f: 0 for f in CORE}
    complete_correct = 0
    complete_decidable = 0
    valid_count = 0
    elapsed: list[float] = []
    cost_total = 0.0
    gold_null_but_extracted: list[str] = []
    field_failures: dict[str, list[str]] = {f: [] for f in CORE}

    seen_ids = []
    for item in raw.sample_results:
        sid = item["sample_id"]
        seen_ids.append(sid)
        # 成本按全部调用累计（失败调用也计费），成功数单独做分母
        cost_total += float(item.get("cost", 0.0))
        g = gold_by_id.get(sid)
        if g is None:
            per_sample.append({"sample_id": sid, "status": "gold_missing"})
            continue
        if not item.get("valid"):
            per_sample.append({"sample_id": sid, "status": "invalid_result"})
            continue
        valid_count += 1
        elapsed.append(float(item.get("elapsed_s", 0.0)))

        judgments = {}
        fields = item.get("fields", {})
        for f in CORE:
            gold_v = g["fields"].get(f)
            ext_v = fields.get(f)
            j = judge_field(gold_v, ext_v)
            judgments[f] = j
            if j is None and ext_v is not None:
                gold_null_but_extracted.append(f"{sid}.{f}")
            if j is not None:
                field_decidable[f] += 1
                field_correct[f] += j
                if j == 0:
                    field_failures[f].append(sid)
        core_all = [judgments[f] for f in CORE]
        complete_decidable_inc = all(j is not None for j in core_all)
        if complete_decidable_inc:
            complete_decidable += 1
            if all(j == 1 for j in core_all):
                complete_correct += 1
        per_sample.append({
            "sample_id": sid, "status": "judged",
            "judgments": judgments,
            # 完整记录只在五字段全部可判定时有 0/1 值，否则 None（台账留空）
            "complete": (all(j == 1 for j in core_all)
                         if complete_decidable_inc else None),
        })

    def pct(num, den):
        return round(100.0 * num / den, 2) if den else None

    metrics = {
        "route": raw.route_name,
        "samples_input": len(raw.sample_results),
        "samples_gold": len(gold_by_id),
        "gold_ids_missing_from_route": sorted(set(gold_by_id) - set(seen_ids)),
        "valid_results": valid_count,
        "success_rate": pct(valid_count, len(gold_by_id)),
        "fields": {
            f: {"correct": field_correct[f], "decidable": field_decidable[f],
                "accuracy": pct(field_correct[f], field_decidable[f])}
            for f in CORE
        },
        "complete_record": {
            "correct": complete_correct, "decidable": complete_decidable,
            "accuracy": pct(complete_correct, complete_decidable)},
        "elapsed_s": {
            "avg": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "p95": _p95(elapsed), "n": len(elapsed)},
        "cost": {"total": round(cost_total, 6),
                 "per_success": round(cost_total / valid_count, 6) if valid_count else None},
        "warnings": {
            "gold_null_but_extracted": gold_null_but_extracted,
            "below_90_fields": [f for f in CORE
                                if pct(field_correct[f], field_decidable[f]) is not None
                                and pct(field_correct[f], field_decidable[f]) < 90.0],
            # 任务3硬要求：低于90%的字段列出具体样本，进入复核队列
            "review_queue": {
                f: {"wrong_samples": field_failures[f],
                    "invalid_samples": [p["sample_id"] for p in per_sample
                                        if p.get("status") == "invalid_result"]}
                for f in CORE
                if pct(field_correct[f], field_decidable[f]) is not None
                and pct(field_correct[f], field_decidable[f]) < 90.0
            },
        },
        "per_sample": per_sample,
    }
    return metrics


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(0.95 * (len(s) + 1)) - 1))
    return round(s[idx], 3)


def compare_and_gate(ocr_metrics: dict, mm_metrics: dict) -> dict:
    """对照两路线并输出多模态启用结论（数据决定，不手填）。

    优先用完整记录准确率；任一路线完整记录不可判定时（金标准未覆盖
    全部五字段），回退为可判定字段的宏平均，并如实标注判定基础。
    """
    def acc(m):
        return m["complete_record"]["accuracy"]

    def macro(m):
        vals = [m["fields"][f]["accuracy"] for f in CORE
                if m["fields"][f]["accuracy"] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    ocr_a, mm_a = acc(ocr_metrics), acc(mm_metrics)
    basis = "complete_record"
    if ocr_a is None or mm_a is None:
        ocr_a, mm_a = macro(ocr_metrics), macro(mm_metrics)
        basis = "field_macro_average_fallback"

    diff_pp = None
    if ocr_a is not None and mm_a is not None:
        diff_pp = round(mm_a - ocr_a, 2)

    fields_meet_90 = {
        "ocr": ocr_metrics["warnings"]["below_90_fields"] == [],
        "multimodal": mm_metrics["warnings"]["below_90_fields"] == [],
    }
    gate_pass = diff_pp is not None and diff_pp >= GATE_PP

    return {
        "gate_basis": basis,
        "ocr_reference_accuracy": ocr_a,
        "multimodal_accuracy": mm_a,
        "diff_percentage_points": diff_pp,
        "gate_pp": GATE_PP,
        "gate_pass": gate_pass,
        "fields_meeting_90": fields_meet_90,
        "multimodal_enablement": "启用" if gate_pass else "不启用",
        "enablement_basis": (
            f"完整记录准确率差 {diff_pp}pp（门槛 ≥{GATE_PP}pp）"
            if basis == "complete_record" and diff_pp is not None
            else f"字段宏平均差 {diff_pp}pp（门槛 ≥{GATE_PP}pp；完整记录不可判定，回退字段口径）"
            if diff_pp is not None else "准确率缺失，无法判定"),
    }


def run_evaluation(gold_path, ocr_raw_path, mm_raw_path, out_path) -> dict:
    """从 gold + 两条路线原始文件产出对照报告。"""
    gold = json.loads(open(gold_path, encoding="utf-8").read())
    routes = {}
    for name, path in (("ocr", ocr_raw_path), ("multimodal", mm_raw_path)):
        data = json.loads(open(path, encoding="utf-8").read())
        routes[name] = evaluate_route(
            gold, RouteRaw(route_name=name, sample_results=data["sample_results"]))

    report = {
        "gold_sample_set": gold.get("sample_set"),
        "routes": routes,
        "gate": compare_and_gate(routes["ocr"], routes["multimodal"]),
        "timing_boundary": "收到 article bundle 到产出 extraction bundle（两路线一致）",
        "recomputable": "所有指标均由 per_sample 0/1 判断汇总，可重算",
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return report
