"""批处理入口：article bundle 文件 -> extraction bundle + evidence pack。

用法：
    python -m app.extraction.cli <article_bundle.json ...>
    python -m app.extraction.cli --dir evidence/week1/A/fixed_samples

输出：
    reports/extraction/bundles/<notice_id>.extraction.json
    reports/extraction/packs/<notice_id>.packs.json
    reports/extraction/summary.json
有 PaddleOCR 环境且 EXTRACTION_ASSET_DIR 指向受控图片目录时自动启用 OCR 路径；
否则海报路径如实 failed（failure_reason=missing_ocr_adapter / asset_not_found）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bundle import validate_bundle
from .evidence import build_evidence_pack
from .extractor import Extractor


def _load_article(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if data.get("schema_version") == "article_bundle.v1":
        return [data]
    raise SystemExit(f"{path}: 不是 article_bundle.v1 文件")


def make_extractor():
    try:
        from .ocr import PaddleOcrAdapter
        return Extractor(ocr_adapter=PaddleOcrAdapter()), "paddleocr"
    except Exception as exc:
        print(f"[cli] OCR 不可用，海报路径将如实标 failed：{exc}", file=sys.stderr)
        return Extractor(), None


def run(inputs: list[Path], out_dir: Path) -> int:
    extractor, ocr_name = make_extractor()
    bundles_dir = out_dir / "bundles"
    packs_dir = out_dir / "packs"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    packs_dir.mkdir(parents=True, exist_ok=True)

    summary = {"ocr_adapter": ocr_name, "articles": 0, "records": 0,
               "schema_errors": 0, "items": []}
    for path in inputs:
        for article in _load_article(path):
            bundle = extractor.extract(article)
            errors = validate_bundle(bundle)
            summary["articles"] += 1
            summary["records"] += len(bundle["records"])
            summary["schema_errors"] += len(errors)
            summary["items"].append({
                "notice_id": bundle["notice_id"],
                "content_type": article.get("content_type"),
                "records": len(bundle["records"]),
                "processing_status": bundle["processing_status"],
                "failure_reason": bundle["failure_reason"],
                "schema_ok": not errors,
            })
            (bundles_dir / f"{bundle['notice_id']}.extraction.json").write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            packs = build_evidence_pack(article, bundle)
            (packs_dir / f"{bundle['notice_id']}.packs.json").write_text(
                json.dumps(packs, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["schema_errors"] == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="extraction batch runner")
    parser.add_argument("inputs", nargs="*", help="article bundle JSON 文件")
    parser.add_argument("--dir", help="批量读取目录中的 *.json")
    parser.add_argument("--out", default="reports/extraction", help="输出目录")
    args = parser.parse_args(argv)

    inputs = [Path(p) for p in args.inputs]
    if args.dir:
        d = Path(args.dir)
        inputs += sorted(p for p in d.glob("*.json")
                         if p.name not in ("REPORT.json",))
    if not inputs:
        parser.error("需要至少一个输入文件或 --dir")
    return run(inputs, Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
