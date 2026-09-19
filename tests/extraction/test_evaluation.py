"""切片6测试：评测汇总可从逐样本重算、分子分母、门槛判定。"""

import json

from app.extraction.evaluation import (
    RouteRaw, compare_and_gate, evaluate_route, judge_field, run_evaluation)


def _gold(samples):
    return {"sample_set": "week1-poster-gold-20", "samples": samples}


def _g(sid, **fields):
    base = {"cohort": None, "education": None, "major": None,
            "city": None, "position_or_unit": None}
    base.update(fields)
    return {"sample_id": sid, "fields": base}


def _r(sid, valid=True, elapsed=1.0, cost=0.01, **fields):
    base = {"cohort": None, "education": None, "major": None,
            "city": None, "position_or_unit": None}
    base.update(fields)
    return {"sample_id": sid, "valid": valid, "elapsed_s": elapsed,
            "cost": cost, "fields": base}


def test_judge_field_rules():
    assert judge_field("2025届", "2025届") == 1
    assert judge_field("成都", " 成都 ") == 1  # 归一化空白
    assert judge_field("成都", "重庆") == 0
    assert judge_field("软件工程", None) == 0  # 金标准有值、抽取为空 → 错误
    assert judge_field(None, "随便") is None  # 金标准缺失 → 不计分母


def test_field_accuracy_reports_numerator_and_denominator():
    gold = _gold([
        _g("P01", cohort="2025届"), _g("P02", cohort="2024届"),
        _g("P03", cohort=None),                  # 不可判定
        _g("P04", cohort="2025届"),
    ])
    raw = RouteRaw("ocr", [
        _r("P01", cohort="2025届"),              # 对
        _r("P02", cohort="2026届"),              # 错
        _r("P03", cohort="编造值"),              # 金标准 null：不计分，但要告警
        _r("P04", cohort=None),                  # 金标准有值抽空：错
    ])
    m = evaluate_route(gold, raw)
    c = m["fields"]["cohort"]
    assert c["correct"] == 1 and c["decidable"] == 3
    assert c["accuracy"] == round(100 / 3, 2)
    assert "P03.cohort" in m["warnings"]["gold_null_but_extracted"]


def test_complete_record_requires_all_five_core_fields():
    gold = _gold([
        _g("P01", cohort="2025届", education="本科", major="软件工程",
           city="成都", position_or_unit="基层岗位"),
        _g("P02", cohort="2025届", education="本科", major="软件工程",
           city="成都", position_or_unit=None),  # 岗位金标准缺失 → 整条不可判定
    ])
    raw = RouteRaw("ocr", [
        _r("P01", cohort="2025届", education="本科", major="软件工程",
           city="成都", position_or_unit="基层岗位"),   # 五字段全对
        _r("P02", cohort="2025届", education="本科", major="软件工程",
           city="成都", position_or_unit="某岗位"),     # 岗位无金标准
    ])
    m = evaluate_route(gold, raw)
    assert m["complete_record"]["correct"] == 1
    assert m["complete_record"]["decidable"] == 1
    assert m["complete_record"]["accuracy"] == 100.0


def test_invalid_results_stay_in_denominator():
    gold = _gold([_g(f"P{i:02d}", cohort="2025届") for i in range(1, 21)])
    results = [_r(f"P{i:02d}", cohort="2025届") for i in range(1, 16)]  # 15 有效
    results.append({**_r("P16", cohort="x"), "valid": False})            # 1 无效
    m = evaluate_route(gold, RouteRaw("ocr", results))
    assert m["success_rate"] == 75.0            # 15/20，失败不从分母删除
    assert m["gold_ids_missing_from_route"] == [f"P{i:02d}" for i in range(17, 21)]


def test_p95_and_cost():
    gold = _gold([_g(f"P{i:02d}") for i in range(1, 21)])
    results = [_r(f"P{i:02d}", valid=(i % 5 != 0), elapsed=float(i) / 10,
                  cost=0.02 * (i % 3)) for i in range(1, 21)]
    m = evaluate_route(gold, RouteRaw("mm", results))
    assert m["elapsed_s"]["n"] == 16
    assert m["elapsed_s"]["avg"] == round(sum(i / 10 for i in range(1, 21) if i % 5) / 16, 3)
    assert m["elapsed_s"]["p95"] == 1.9
    assert m["cost"]["per_success"] == round(sum(0.02 * (i % 3) for i in range(1, 21)) / 16, 6)


def test_gate_requires_5pp_and_is_data_driven():
    gold = _gold([_g(f"P{i:02d}", cohort="2025届") for i in range(1, 21)])
    ocr = evaluate_route(gold, RouteRaw(
        "ocr", [_r(f"P{i:02d}", cohort="2025届") for i in range(1, 11)] +
               [_r(f"P{i:02d}", cohort="错") for i in range(11, 21)]))  # 50%
    mm_pass = evaluate_route(gold, RouteRaw(
        "mm", [_r(f"P{i:02d}", cohort="2025届") for i in range(1, 17)] +
              [_r(f"P{i:02d}", cohort="错") for i in range(17, 21)]))   # 80%？字段层面
    g1 = compare_and_gate(ocr, mm_pass)
    assert g1["multimodal_enablement"] == "启用"
    assert g1["diff_percentage_points"] == 30.0

    mm_fail = evaluate_route(gold, RouteRaw(
        "mm", [_r(f"P{i:02d}", cohort="2025届") for i in range(1, 12)] +
              [_r(f"P{i:02d}", cohort="错") for i in range(12, 21)]))   # +5%？55%→差5pp
    g2 = compare_and_gate(ocr, mm_fail)
    # 11/20=55%，差 5.0pp，恰好达标 → 启用
    assert g2["diff_percentage_points"] == 5.0
    assert g2["multimodal_enablement"] == "启用"

    mm_tie = evaluate_route(gold, RouteRaw(
        "mm", [_r(f"P{i:02d}", cohort="2025届") for i in range(1, 11)] +
              [_r(f"P{i:02d}", cohort="错") for i in range(11, 21)]))   # 50% → 0pp
    g3 = compare_and_gate(ocr, mm_tie)
    assert g3["multimodal_enablement"] == "不启用"


def test_below_90_fields_flagged():
    gold = _gold([_g(f"P{i:02d}", city="成都") for i in range(1, 21)])
    raw = RouteRaw("ocr", [_r(f"P{i:02d}", city="成都" if i <= 17 else "错")
                           for i in range(1, 21)])  # 17/20 = 85%
    m = evaluate_route(gold, raw)
    assert m["warnings"]["below_90_fields"] == ["city"]
    assert "cohort" not in m["warnings"]["below_90_fields"]


def test_multi_person_strict_judging():
    """多人海报：人数一致且逐人物全对才记 1；幻觉人物判错。"""
    gold = {"sample_set": "t", "samples": [{
        "sample_id": "P01",
        "persons": [
            {"cohort": "2024届", "education": "本科", "major": "法学",
             "city": "本溪", "position_or_unit": "本溪市检察院"},
            {"cohort": "2024届", "education": "硕士", "major": "新闻与传播",
             "city": "大连", "position_or_unit": "辛寨子街道办事处"},
        ]}]}
    def run(ext_persons):
        return evaluate_route(gold, RouteRaw("ocr", [
            {"sample_id": "P01", "valid": True, "elapsed_s": 1.0,
             "cost": 0.0, "persons": ext_persons}]))

    # 全对
    m = run([{"cohort": "2024届", "education": "本科", "major": "法学",
              "city": "本溪", "position_or_unit": "本溪市检察院"},
             {"cohort": "2024届", "education": "硕士研究生", "major": "新闻与传播",
              "city": "大连", "position_or_unit": "辛寨子街道办事处"}])
    assert m["fields"]["major"]["accuracy"] == 100.0
    assert m["complete_record"]["accuracy"] == 100.0

    # 第二人城市错 → 各字段：city 0，其余 1
    m = run([{"cohort": "2024届", "education": "本科", "major": "法学",
              "city": "本溪", "position_or_unit": "本溪市检察院"},
             {"cohort": "2024届", "education": "硕士", "major": "新闻与传播",
              "city": "沈阳", "position_or_unit": "辛寨子街道办事处"}])
    assert m["fields"]["city"]["correct"] == 0
    assert m["fields"]["major"]["correct"] == 1

    # 幻觉第三人 → 全字段判错
    m = run([{"cohort": "2024届", "education": "本科", "major": "法学",
              "city": "本溪", "position_or_unit": "本溪市检察院"},
             {"cohort": "2024届", "education": "硕士", "major": "新闻与传播",
              "city": "大连", "position_or_unit": "辛寨子街道办事处"},
             {"cohort": "2024届", "education": "本科", "major": "法学",
              "city": "本溪", "position_or_unit": "x"}])
    assert all(m["fields"][f]["correct"] == 0 for f in
               ("cohort", "education", "major", "city", "position_or_unit"))
    assert m["per_sample"][0]["persons_extracted"] == 3


def test_below_90_review_queue_lists_specific_samples():
    """任务3硬要求：低于90%字段必须列出具体样本进入复核队列。"""
    gold = _gold([_g(f"P{i:02d}", city="成都", cohort="2025届")
                  for i in range(1, 21)])
    results = []
    for i in range(1, 21):
        results.append(_r(f"P{i:02d}", cohort="2025届",
                          city="成都" if i <= 17 else "错值"))  # city 85%
    results[3]["valid"] = False  # P04 无效结果也入队
    m = evaluate_route(gold, RouteRaw("ocr", results))
    rq = m["warnings"]["review_queue"]
    assert set(rq["city"]["wrong_samples"]) == {"P18", "P19", "P20"}
    assert rq["city"]["invalid_samples"] == ["P04"]
    assert "cohort" not in rq  # cohort 100% 不入队


def test_run_evaluation_end_to_end_recomputable(tmp_path):
    gold = _gold([_g(f"P{i:02d}", cohort="2025届", major="法学") for i in range(1, 21)])
    ocr_raw = {"sample_results": [
        _r(f"P{i:02d}", cohort="2025届", major="法学") for i in range(1, 15)] +
        [_r(f"P{i:02d}", cohort="2025届", major="错") for i in range(15, 21)]}
    mm_raw = {"sample_results": [
        _r(f"P{i:02d}", cohort="2025届", major="法学") for i in range(1, 19)] +
        [_r(f"P{i:02d}", cohort="错", major="法学") for i in range(19, 21)]}

    gp = tmp_path / "gold.json"
    op = tmp_path / "ocr.json"
    mp = tmp_path / "mm.json"
    out = tmp_path / "report.json"
    gp.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    op.write_text(json.dumps(ocr_raw, ensure_ascii=False), encoding="utf-8")
    mp.write_text(json.dumps(mm_raw, ensure_ascii=False), encoding="utf-8")

    report = run_evaluation(gp, op, mp, out)
    # 汇总可从 per_sample 重算：major 正确数 = per_sample 里 judgments==1 的数量
    ocr_m = report["routes"]["ocr"]
    recomputed = sum(
        1 for s in ocr_m["per_sample"]
        if s.get("judgments", {}).get("major") == 1)
    assert recomputed == ocr_m["fields"]["major"]["correct"] == 14
    assert report["gate"]["multimodal_enablement"] == "启用"  # major 70%→90%，完整记录同幅
    assert json.loads(out.read_text(encoding="utf-8"))["gate"]["gate_pp"] == 5.0
