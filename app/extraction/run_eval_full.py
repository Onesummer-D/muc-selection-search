"""20 样本全量对照评测驱动（B4 主流程）。

1. 读 reports/extraction/eval_inputs/ 的 20 个 article bundle；
2. 每张跑 OCR 与多模态两条路线（计时、计失败状态）；
3. 原始抽取（含证据文本，可能含姓名）写仓库外受控目录；
4. 评测用原始结果（仅字段值，无 PII）写 reports/extraction/eval_raw/；
5. gold_20.json + 两路线原始 -> 评测报告 + 台账导入 CSV。

用法：python -m app.extraction.run_eval_full
前置：EXTRACTION_ASSET_DIR 指向受控图片根目录；.env 配好 LLM_*。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ("cohort", "education", "major", "city", "position_or_unit")


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def bundle_to_article(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def records_to_persons(bundle: dict) -> list[dict]:
    """抽取记录 -> 评测人物列表（record_key 顺序 = 版面自上而下）。"""
    return [{f: r[f] for f in CORE}
            for r in sorted(bundle["records"], key=lambda x: x["record_key"])]


def main() -> int:
    load_env()
    asset_dir = Path(os.environ["EXTRACTION_ASSET_DIR"])
    workdir = Path(os.environ.get(
        "EXTRACTION_WORKDIR", str(ROOT.parent / "controlled_assets" / "eval_workdir")))
    raw_dir = ROOT / "reports" / "extraction" / "eval_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    inputs = sorted((ROOT / "reports" / "extraction" / "eval_inputs").glob("*.json"))
    assert len(inputs) == 20, f"期望 20 个输入 bundle，实际 {len(inputs)}"

    from .ocr import PaddleOcrAdapter
    from .multimodal import MultimodalAdapter
    from .extractor import Extractor
    from .bundle import validate_bundle

    routes = {"ocr": PaddleOcrAdapter(), "multimodal": MultimodalAdapter()}
    sample_results = {name: [] for name in routes}
    progress = []

    for path in inputs:
        article = bundle_to_article(path)
        nid = article["notice_id"]
        for name, adapter in routes.items():
            start = time.perf_counter()
            bundle = Extractor(ocr_adapter=adapter).extract(article)
            elapsed = round(time.perf_counter() - start, 2)
            errors = validate_bundle(bundle)

            # 含证据/姓名的完整原始 -> 受控目录
            (workdir / name).mkdir(parents=True, exist_ok=True)
            (workdir / name / f"{nid}.extraction.json").write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

            # 无 PII 评测原始（字段值）-> 仓库
            valid = not errors and bundle["processing_status"] != "failed"
            sample_results[name].append({
                "sample_id": nid,
                "valid": valid,
                "elapsed_s": elapsed,
                "cost": 0.0 if name == "ocr" else round(elapsed * 0.0, 6),  # 成本另行登记
                "persons": records_to_persons(bundle) if valid else [],
                "status": bundle["processing_status"],
                "failure_reason": bundle["failure_reason"],
            })
            progress.append(f"{nid} {name}: {bundle['processing_status']} "
                            f"({len(bundle['records'])}人 {elapsed}s)")
            print(progress[-1], flush=True)

    for name in routes:
        (raw_dir / f"{name}.json").write_text(
            json.dumps({"sample_results": sample_results[name]},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    print("RAW WRITTEN", flush=True)

    # 评测 + 台账导出
    from .evaluation import run_evaluation
    from .tracker_export import export_csv
    gold_path = ROOT / "data" / "gold" / "gold_20.json"
    report = run_evaluation(
        gold_path, raw_dir / "ocr.json", raw_dir / "multimodal.json",
        ROOT / "reports" / "extraction" / "evaluation_report.json")
    export_csv(gold_path,
               ROOT / "reports" / "extraction" / "evaluation_report.json",
               ROOT / "reports" / "extraction" / "tracker_import.csv",
               raw_ocr_path=raw_dir / "ocr.json",
               raw_mm_path=raw_dir / "multimodal.json")
    gate = report["gate"]
    print(json.dumps({
        "gate": gate,
        "ocr_fields": report["routes"]["ocr"]["fields"],
        "mm_fields": report["routes"]["multimodal"]["fields"],
    }, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
