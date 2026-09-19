"""切片5测试：批处理 CLI 与金标准校验器。"""

import json
from pathlib import Path

import pytest

from data.gold.gold_schema_check import validate_gold
from tests.extraction.test_poster_rules import StubOcrAdapter, _article, _box, _page

ROOT = Path(__file__).resolve().parents[2]


def test_cli_runs_on_fixed_samples_and_all_bundles_pass_schema(tmp_path):
    """B2 烟测（文本路径）：对 A 交付的 5 篇固定样本跑批处理。

    无 OCR 环境（原图受控交接中，见 progress/week1/B/BLOCKED.md），
    海报路径如实 failed，不伪造结果。
    """
    from app.extraction.cli import run
    samples_dir = ROOT / "evidence" / "week1" / "A" / "fixed_samples"
    out = tmp_path / "reports"
    rc = run([samples_dir / "352508.json", samples_dir / "247586.json"], out)
    assert rc == 0

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["articles"] == 2
    assert summary["schema_errors"] == 0
    by_id = {i["notice_id"]: i for i in summary["items"]}
    # 文本帖：规则抽取有结果
    assert by_id["352508"]["processing_status"] in ("processed", "review_required")
    assert by_id["352508"]["records"] >= 1
    # 海报帖：无 OCR 环境如实 failed
    assert by_id["247586"]["processing_status"] == "failed"

    bundle = json.loads(
        (out / "bundles" / "352508.extraction.json").read_text(encoding="utf-8"))
    from app.extraction import validate_bundle as vb
    assert vb(bundle) == []


def test_cli_mixed_sample_produces_pack(tmp_path):
    from app.extraction.cli import run
    samples_dir = ROOT / "evidence" / "week1" / "A" / "fixed_samples"
    out = tmp_path / "reports"
    run([samples_dir / "348879.json"], out)
    packs = json.loads((out / "packs" / "348879.packs.json").read_text(encoding="utf-8"))
    assert isinstance(packs, list)
    assert all("record_key" in p and "field_evidence" in p for p in packs)


def _gold(**overrides):
    base = {
        "sample_set": "week1-poster-gold-20",
        "annotator": "B-annotator-1",
        "frozen_at": "2026-09-19T20:00:00+08:00",
        "samples": [
            {"sample_id": f"P{i:02d}", "notice_id": f"24700{i}", "asset_id": f"24700{i}-poster-01",
             "image_sha256": "a" * 64, "annotated_by": "B-annotator-1",
             "evidence_summary": "海报右上角区域",
             "fields": {"cohort": "2025届", "education": "本科", "major": None,
                        "city": None, "position_or_unit": None},
             "is_multi_person": False, "persons": []}
            for i in range(1, 21)
        ],
    }
    for k, v in overrides.items():
        base[k] = v
    return base


def test_gold_template_and_valid_gold_pass():
    template = json.loads(
        (ROOT / "data" / "gold" / "gold_20_template.json").read_text(encoding="utf-8"))
    # 模板是待填状态：仅校验结构可被校验器读取（缺 hash 会报错，属预期）
    assert validate_gold(template)  # 模板未填，必须报错而不是静默通过
    assert validate_gold(_gold()) == []


def test_gold_rejects_bad_sha_bad_enum_bad_ids():
    g = _gold()
    g["samples"][0]["image_sha256"] = "xyz"
    g["samples"][1]["fields"]["education"] = "大专"  # 枚举外
    g["samples"][2]["sample_id"] = "P99"
    errors = validate_gold(g)
    assert any("image_sha256" in e for e in errors)
    assert any("education" in e for e in errors)
    assert any("P01–P20" in e for e in errors)


def test_gold_rejects_fewer_than_20():
    g = _gold()
    g["samples"] = g["samples"][:19]
    assert any("样本数" in e for e in validate_gold(g))
