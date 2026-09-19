"""对受控交接的真实海报运行两条路线，产出原始结果（写入仓库外受控目录）。

PII 边界：原始 OCR 文本、evidence 证据文本、evidence pack 都可能含真实姓名，
全部只写 EXTRACTION_WORKDIR（仓库外受控目录）；仓库内只允许聚合指标。

用法：python -m app.extraction.run_real_posters 247919 247586 ...
前置：EXTRACTION_ASSET_DIR 指向受控图片根目录（<notice_id>/poster-01.jpeg），
      LLM_* 已在 .env 配置（多模态路线）。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 固定样本 bundle（仓库内，含标题/来源/时间）；247509 等从台账取标题
LEDGER_TITLES = {
    "247509": ("12月26日||闪耀基层——辽宁选调校友经验分享活动",
               "https://my.muc.edu.cn/notice/247509", "2024-12-18 14:11"),
}


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def build_article(notice_id: str, asset_dir: Path) -> dict | None:
    fixed = ROOT / "evidence" / "week1" / "A" / "fixed_samples" / f"{notice_id}.json"
    if fixed.exists():
        article = json.loads(fixed.read_text(encoding="utf-8"))
    elif notice_id in LEDGER_TITLES:
        title, url, published = LEDGER_TITLES[notice_id]
        article = {
            "schema_version": "article_bundle.v1", "notice_id": notice_id,
            "title": title, "source_url": url, "published_at": published,
            "content_type": "poster", "clean_text": None,
            "asset_refs": [], "fetch_status": "processed",
            "failure_reason": None,
            "fetched_at": "2026-09-19T00:00:00+08:00",
        }
    else:
        return None

    poster = asset_dir / notice_id / "poster-01.jpeg"
    if not poster.exists():
        for ext in (".jpg", ".png"):
            alt = asset_dir / notice_id / f"poster-01{ext}"
            if alt.exists():
                poster = alt
                break
    if not poster.exists():
        return None
    article["asset_refs"] = [{
        "asset_id": f"{notice_id}-poster-01", "kind": "poster",
        "local_ref": f"private://{notice_id}/poster-01",
        "sha256": hashlib.sha256(poster.read_bytes()).hexdigest(),
    }]
    return article


def main(argv: list[str]) -> int:
    load_env()
    asset_dir = Path(os.environ["EXTRACTION_ASSET_DIR"])
    workdir = Path(os.environ.get(
        "EXTRACTION_WORKDIR", str(ROOT.parent / "controlled_assets" / "eval_workdir")))
    (workdir / "ocr").mkdir(parents=True, exist_ok=True)
    (workdir / "multimodal").mkdir(parents=True, exist_ok=True)

    from .ocr import PaddleOcrAdapter
    from .multimodal import MultimodalAdapter
    from .extractor import Extractor
    from .bundle import validate_bundle

    routes = {"ocr": PaddleOcrAdapter(), "multimodal": MultimodalAdapter()}
    summary = []
    for notice_id in argv:
        article = build_article(notice_id, asset_dir)
        if article is None:
            summary.append({"notice_id": notice_id, "error": "asset_or_bundle_missing"})
            continue
        for name, adapter in routes.items():
            start = time.perf_counter()
            bundle = Extractor(ocr_adapter=adapter).extract(article)
            elapsed = round(time.perf_counter() - start, 2)
            errors = validate_bundle(bundle)
            out = workdir / name / f"{notice_id}.extraction.json"
            out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            # 仓库内只放无 PII 聚合：状态、记录数、字段非空计数、耗时
            records = bundle["records"]
            summary.append({
                "notice_id": notice_id, "route": name, "elapsed_s": elapsed,
                "records": len(records),
                "processing_status": bundle["processing_status"],
                "failure_reason": bundle["failure_reason"],
                "schema_ok": not errors,
                "fields_filled": {
                    f: sum(1 for r in records if r[f] is not None)
                    for f in ("cohort", "education", "major", "city", "position_or_unit")},
                "review_required": sum(1 for r in records
                                       if r["review_status"] == "review_required"),
                "record_keys": [r["record_key"] for r in records],
            })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
