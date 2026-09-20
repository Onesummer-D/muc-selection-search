"""20 样本对照评测：从逐样本原始结果重算全部指标。

设计约束（B 任务书 + PR #5 复核意见）：
- 汇总必须能从逐样本 0/1 判断重新计算，不接受手填汇总；
- 主指标为严格 0/1（仅空白归一），不静默放宽；归一化等价
  （简称包含、硕士≡硕士研究生等）单独一套数字，等价通过样本
  进入 equivalence_pending 供人工裁决，两套数字都报；
- 多人海报：人数一致且逐人物逐字段全对，该字段才记正确；
  抽取人数多于金标准（幻觉人物）同样判错；
  单人物 gold=null 时抽取也须为 null（有值=幻觉，判错）；
- 五核心字段（届别/学历/专业/城市/岗位）参与 90% 门槛与完整记录；
  年级/学院照实判定报告（fields_extra），不参与门槛；
- 金标准 null 不计分母，但必须报告分母；
- 成功率 = 产生结构合法结果的样本数 / 20（失败样本不从分母删除）；
- 多模态启用门槛 = 多模态完整记录准确率 − OCR 完整记录准确率 ≥ 5pp。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import fields as F

CORE = ("cohort", "education", "major", "city", "position_or_unit")
EXTRA = ("grade", "college")
ALL7 = CORE + EXTRA
GATE_PP = 5.0  # 启用门槛，百分点


@dataclass
class RouteRaw:
    """一条路线在 20 样本上的原始结果（评测的唯一输入，禁止手填汇总）。"""

    route_name: str
    sample_results: list[dict] = field(default_factory=list)
    # 每项：{"sample_id": "P01", "valid": bool, "elapsed_s": float, "cost": float,
    #        "persons": [{"cohort": ..., "grade": ..., ... 7 字段}, ...]}


def _norm_strict(v) -> str | None:
    """严格口径归一：仅去空白（其余差异都算不同）。"""
    if v is None:
        return None
    return str(v).strip().replace(" ", "") or None


def _norm(v) -> str | None:
    """归一口径：空白、学历同义、机构简称、省市后缀、任职尾巴。"""
    if v is None:
        return None
    s = str(v).strip().replace(" ", "")
    s = F.EDUCATION_ALIAS.get(s, s)
    s = s.replace("纪检委", "纪委监委")
    for tail in ("试用期公务员（不定职级）", "试用期公务员(不定职级)",
                 "试用期干部（不定职级）", "试用期干部(不定职级)",
                 "试用期公务员", "试用期干部", "公务员", "干部"):
        if s.endswith(tail) and len(s) > len(tail):
            s = s[: -len(tail)]
            break
    for suffix in ("地区", "盟", "市", "省"):
        if s.endswith(suffix) and len(s) > len(suffix) + 1:
            return s[: -len(suffix)]
    return s or None


def _match_norm(gold_v, ext_v, field: str = "") -> bool:
    """归一/裁决口径（PR 终版验收·第三部分统一规则）：

    - education："硕士"≡"硕士研究生"、"博士"≡"博士研究生" ✅等价；
    - city：输出唯一正确识别金标准城市即 ✅——允许±市后缀与更细下级地址
      （双向包含/前缀，"株洲"⊆"湖南省株洲市炎陵县…"）；另一行政实体自然 ❌；
    - major/position_or_unit：逐字要求高，只认「金标准 ⊆ 输出」的细化
      （金标准原文完整出现在输出中，如"临汾市城联社"⊆"山西省临汾市城联社"）；
      丢字/错字/丢括号内容（输出 ⊊ 金标准）一律 ❌；
    - grade：允许"2020级"≡"2020"。
    """
    a, b = _norm(gold_v), _norm(ext_v)
    if a is None or b is None:
        return False
    if field == "grade":
        a, b = a.removesuffix("级"), b.removesuffix("级")
    if a == b:
        return True
    if field == "education":
        return False  # 同义已由 _norm 别名覆盖，其余差异不算等价
    if field in ("major", "position_or_unit"):
        # 只认金标准⊆输出的细化；丢字（输出⊊金标准）❌
        return len(a) >= 3 and a in b
    if field == "city":
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        return short in long or long.startswith(short)
    return False


def judge_pair(gold_value, ext_value, field: str = "") -> tuple[int | None, int | None]:
    """返回 (strict, normalized) 两个 0/1 判定；gold 缺失时返回 (None, None)。"""
    if gold_value is None:
        return None, None
    strict = 1 if _norm_strict(ext_value) == _norm_strict(gold_value) else 0
    norm = 1 if _match_norm(gold_value, ext_value, field) else 0
    return strict, norm


def judge_field(gold_value, ext_value, field: str = "") -> int | None:
    """兼容旧调用：返回归一口径判定。"""
    return judge_pair(gold_value, ext_value, field)[1]


def _judge_person(gold_p: dict, ext_p: dict) -> dict[str, tuple[int | None, int | None]]:
    """单人物逐字段判定；gold=null 时抽取须为 null（有值=幻觉判错）。"""
    out = {}
    for f in ALL7:
        gv = gold_p.get(f)
        if gv is None:
            ok = ext_p.get(f) is None
            out[f] = (1 if ok else 0, 1 if ok else 0)
        else:
            out[f] = judge_pair(gv, ext_p.get(f), f)
    return out


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(0.95 * (len(s) + 1)) - 1))
    return round(s[idx], 3)


def evaluate_route(gold: dict, raw: RouteRaw,
                   adjudicated: set | None = None) -> dict:
    """逐样本逐字段打分并汇总；任何缺失如实进入对应状态。

    adjudicated：{(sample_id, field)} 集合——人工裁决表中确认"等价✅"的
    strict-fail 项，重算时翻为正确（adjudicated 口径）。
    """
    adjudicated = adjudicated or set()
    gold_by_id = {s["sample_id"]: s for s in gold["samples"]}
    per_sample = []
    stats = {f: {"strict": 0, "norm": 0, "decidable": 0} for f in ALL7}
    stats_adj = {f: {"correct": 0, "decidable": 0} for f in ALL7}
    complete = {"strict": 0, "norm": 0, "decidable": 0}
    complete_adj = {"correct": 0, "decidable": 0}
    valid_count = 0
    elapsed: list[float] = []
    cost_total = 0.0
    gold_null_but_extracted: list[str] = []
    strict_failures: dict[str, list[str]] = {f: [] for f in ALL7}
    equivalence: dict[str, list[str]] = {f: [] for f in ALL7}

    seen_ids = []
    for item in raw.sample_results:
        sid = item["sample_id"]
        seen_ids.append(sid)
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

        if "persons" in g:
            gold_persons = g["persons"]
            ext_persons = item.get("persons") or []
            judgments, judgments_norm = {}, {}
            for f in ALL7:
                gold_vals = [p.get(f) for p in gold_persons]
                if all(v is None for v in gold_vals):
                    judgments[f] = judgments_norm[f] = None
                    continue
                stats[f]["decidable"] += 1
                pairs = [_judge_person(gp, ep)[f]
                         for gp, ep in zip(gold_persons, ext_persons)] \
                    if len(ext_persons) == len(gold_persons) else []
                ok_s = bool(pairs) and all(p[0] == 1 for p in pairs)
                ok_n = bool(pairs) and all(p[1] == 1 for p in pairs)
                judgments[f] = 1 if ok_s else 0
                judgments_norm[f] = 1 if ok_n else 0
                stats[f]["strict"] += judgments[f]
                stats[f]["norm"] += judgments_norm[f]
                if judgments[f] == 0:
                    strict_failures[f].append(sid)
                if judgments[f] == 0 and judgments_norm[f] == 1:
                    equivalence[f].append(sid)
                # adjudicated 口径：strict-fail 且人工确认等价 → 翻正确
                stats_adj[f]["decidable"] += 1
                adj_ok = judgments[f] == 1 or (sid, f) in adjudicated
                stats_adj[f]["correct"] += 1 if adj_ok else 0
            comp_dec = all(judgments[f] is not None for f in CORE)
            if comp_dec:
                complete["decidable"] += 1
                if all(judgments[f] == 1 for f in CORE):
                    complete["strict"] += 1
                if all(judgments_norm[f] == 1 for f in CORE):
                    complete["norm"] += 1
                if all(judgments[f] == 1 or (sid, f) in adjudicated
                       for f in CORE):
                    complete_adj["correct"] += 1
                complete_adj["decidable"] += 1
            per_sample.append({
                "sample_id": sid, "status": "judged", "mode": "multi_person",
                "persons_extracted": len(ext_persons),
                "persons_gold": len(gold_persons),
                "judgments": judgments, "judgments_norm": judgments_norm,
                "complete": (all(judgments[f] == 1 for f in CORE)
                             if comp_dec else None),
            })
            continue

        # 单人物（旧格式兼容）
        judgments, judgments_norm = {}, {}
        fields = item.get("fields", {})
        gfields = g.get("fields", {})
        for f in ALL7:
            gold_v = gfields.get(f)
            ext_v = fields.get(f)
            s_v, n_v = judge_pair(gold_v, ext_v, f)
            judgments[f], judgments_norm[f] = s_v, n_v
            if s_v is None and ext_v is not None:
                gold_null_but_extracted.append(f"{sid}.{f}")
            if s_v is not None:
                stats[f]["decidable"] += 1
                stats[f]["strict"] += s_v
                stats[f]["norm"] += n_v
                if s_v == 0:
                    strict_failures[f].append(sid)
                    if n_v == 1:
                        equivalence[f].append(sid)
                stats_adj[f]["decidable"] += 1
                stats_adj[f]["correct"] += 1 if (
                    s_v == 1 or (sid, f) in adjudicated) else 0
        core_j = [judgments[f] for f in CORE]
        comp_dec = all(j is not None for j in core_j)
        if comp_dec:
            complete["decidable"] += 1
            if all(j == 1 for j in core_j):
                complete["strict"] += 1
            if all(j == 1 or (sid, f) in adjudicated for j, f in zip(core_j, CORE)):
                complete_adj["correct"] += 1
            complete_adj["decidable"] += 1
        core_jn = [judgments_norm[f] for f in CORE]
        if all(j is not None for j in core_jn) and all(j == 1 for j in core_jn):
            complete["norm"] += 1
        per_sample.append({
            "sample_id": sid, "status": "judged",
            "judgments": judgments, "judgments_norm": judgments_norm,
            "complete": (all(j == 1 for j in core_j) if comp_dec else None),
        })

    def pct(num, den):
        return round(100.0 * num / den, 2) if den else None

    def field_block(mode: str, names) -> dict:
        return {f: {"correct": stats[f][mode], "decidable": stats[f]["decidable"],
                    "accuracy": pct(stats[f][mode], stats[f]["decidable"])}
                for f in names}

    fields_strict = field_block("strict", CORE)
    fields_norm = field_block("norm", CORE)
    below_90 = [f for f in CORE
                if fields_strict[f]["accuracy"] is not None
                and fields_strict[f]["accuracy"] < 90.0]

    metrics = {
        "route": raw.route_name,
        "samples_input": len(raw.sample_results),
        "samples_gold": len(gold_by_id),
        "gold_ids_missing_from_route": sorted(set(gold_by_id) - set(seen_ids)),
        "valid_results": valid_count,
        "success_rate": pct(valid_count, len(gold_by_id)),
        "fields": fields_strict,
        "fields_norm": fields_norm,
        "fields_extra": field_block("strict", EXTRA),
        "fields_extra_norm": field_block("norm", EXTRA),
        "complete_record": {
            "correct": complete["strict"], "decidable": complete["decidable"],
            "accuracy": pct(complete["strict"], complete["decidable"])},
        "complete_record_norm": {
            "correct": complete["norm"], "decidable": complete["decidable"],
            "accuracy": pct(complete["norm"], complete["decidable"])},
        "fields_adjudicated": {
            f: {"correct": stats_adj[f]["correct"],
                "decidable": stats_adj[f]["decidable"],
                "accuracy": pct(stats_adj[f]["correct"], stats_adj[f]["decidable"])}
            for f in CORE},
        "fields_extra_adjudicated": {
            f: {"correct": stats_adj[f]["correct"],
                "decidable": stats_adj[f]["decidable"],
                "accuracy": pct(stats_adj[f]["correct"], stats_adj[f]["decidable"])}
            for f in EXTRA},
        "complete_record_adjudicated": {
            "correct": complete_adj["correct"],
            "decidable": complete_adj["decidable"],
            "accuracy": pct(complete_adj["correct"], complete_adj["decidable"])},
        "elapsed_s": {
            "avg": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "p95": _p95(elapsed), "n": len(elapsed)},
        "cost": {"total": round(cost_total, 6),
                 "per_success": round(cost_total / valid_count, 6) if valid_count else None},
        "warnings": {
            "gold_null_but_extracted": gold_null_but_extracted,
            "below_90_fields": below_90,
            # 任务3硬要求：低于90%字段列出具体样本；等价通过样本单列供人工裁决
            "review_queue": {
                f: {"wrong_samples": strict_failures[f],
                    "equivalence_pending": equivalence[f],
                    "invalid_samples": [p["sample_id"] for p in per_sample
                                        if p.get("status") == "invalid_result"]}
                for f in CORE if f in below_90
            },
        },
        "per_sample": per_sample,
    }
    return metrics


def compare_and_gate(ocr_metrics: dict, mm_metrics: dict) -> dict:
    """对照两路线并输出多模态启用结论（数据决定，不手填）。"""
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

    # 裁决后 gate（PR 终版验收 A：strict_gate / adjudicated_gate 并列，
    # 最终采纳 adjudicated_gate——严格口径把"简称 vs 全称"的等价
    # 表述判为错误属于匹配伪影，人工裁决表已逐条确认）
    def acc_adj(m):
        return m["complete_record_adjudicated"]["accuracy"]

    ocr_adj, mm_adj = acc_adj(ocr_metrics), acc_adj(mm_metrics)
    if ocr_adj is None or mm_adj is None:
        adj_diff = diff_pp
    else:
        adj_diff = round(mm_adj - ocr_adj, 2)
    adj_pass = adj_diff is not None and adj_diff >= GATE_PP

    return {
        "gate_basis": basis,
        "strict_gate": {
            "ocr_complete_accuracy": ocr_a,
            "multimodal_complete_accuracy": mm_a,
            "diff_percentage_points": diff_pp,
            "gate_pass": gate_pass,
            "multimodal_enablement": "启用" if gate_pass else "不启用",
            "enablement_basis": (
                f"完整记录准确率差 {diff_pp}pp（门槛 ≥{GATE_PP}pp）"
                if diff_pp is not None else "准确率缺失，无法判定"),
        },
        "adjudicated_gate": {
            "ocr_complete_accuracy": ocr_adj,
            "multimodal_complete_accuracy": mm_adj,
            "diff_percentage_points": adj_diff,
            "gate_pass": adj_pass,
            "multimodal_enablement": "启用" if adj_pass else "不启用",
            "enablement_basis": (
                f"裁决后完整记录准确率差 {adj_diff}pp（门槛 ≥{GATE_PP}pp；"
                "等价通过样本见 equivalence_adjudicated.json）"
                if adj_diff is not None else "准确率缺失，无法判定"),
        },
        "ocr_reference_accuracy": ocr_a,
        "multimodal_accuracy": mm_a,
        "diff_percentage_points": diff_pp,
        "gate_pp": GATE_PP,
        "gate_pass": adj_pass,
        "fields_meeting_90": fields_meet_90,
        "multimodal_enablement": "启用" if adj_pass else "不启用",
        "enablement_basis": (
            f"最终采纳裁决后口径：完整记录准确率差 {adj_diff}pp（门槛 ≥{GATE_PP}pp）；"
            f"严格口径差 {diff_pp}pp 并列保留"
            if adj_diff is not None and diff_pp is not None
            else "准确率缺失，无法判定"),
    }


def load_adjudicated(path) -> set:
    """equivalence_adjudicated.json -> {(sample_id, field)}（仅人工确认项）。"""
    p = Path(path)
    if not p.exists():
        return set()
    data = json.loads(p.read_text(encoding="utf-8"))
    confirmed = data.get("human_confirmed", False)
    if not confirmed:
        return set()
    return {(e["sample_id"], e["field"])
            for e in data.get("entries", []) if e.get("adjudication") == "等价"}


def run_evaluation(gold_path, ocr_raw_path, mm_raw_path, out_path,
                   adjudicated_path=None) -> dict:
    """从 gold + 两条路线原始文件产出对照报告（双 gate）。"""
    gold = json.loads(open(gold_path, encoding="utf-8").read())
    adj_path = adjudicated_path or (
        Path(gold_path).parent / "equivalence_adjudicated.json")
    adjudicated = load_adjudicated(adj_path)
    routes = {}
    for name, path in (("ocr", ocr_raw_path), ("multimodal", mm_raw_path)):
        data = json.loads(open(path, encoding="utf-8").read())
        routes[name] = evaluate_route(
            gold, RouteRaw(route_name=name, sample_results=data["sample_results"]),
            adjudicated=adjudicated)

    report = {
        "gold_sample_set": gold.get("sample_set"),
        "gold_revision": gold.get("revision"),
        "judging": "主指标=严格0/1（仅空白归一）；fields_norm=归一化等价口径；"
                   "fields_adjudicated=人工裁决后口径（最终采纳）；"
                   "等价通过样本见 warnings.review_queue[].equivalence_pending",
        "adjudicated_source": (str(adj_path) if adjudicated
                               else "equivalence_adjudicated.json 未确认/不存在"),
        "routes": routes,
        "gate": compare_and_gate(routes["ocr"], routes["multimodal"]),
        "timing_boundary": "收到 article bundle 到产出 extraction bundle（两路线一致）",
        "recomputable": "所有指标均由 per_sample 0/1 判断汇总，可重算",
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return report
