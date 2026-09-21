"""在隔离 SQLite 内验证 B 固定 5 个 extraction bundle 可被 C 导入器接收。

不写入生产 data/app.db；输出只包含行数、Schema/导入状态和重复导入幂等结果。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.repository.importer import BundleImporter
from app.repository.sqlite_repository import SQLiteRepository

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "week2" / "B" / "bundle_import_smoke.json"


def article_for(notice_id: str, title: str) -> dict:
    digest = hashlib.sha256(notice_id.encode()).hexdigest()
    return {
        "schema_version": "article_bundle.v1",
        "notice_id": notice_id,
        "title": title,
        "source_url": f"https://portal.example.invalid/notice/{notice_id}",
        "published_at": "2026-09-21T09:00:00+08:00",
        "content_type": "poster",
        "clean_text": "B fixed sample sanitized import smoke test",
        "asset_refs": [{"asset_id": f"{notice_id}-poster-01", "kind": "poster", "local_ref": f"private://{notice_id}/poster-01", "sha256": digest}],
        "fetch_status": "processed",
        "failure_reason": None,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def main() -> int:
    bundle_dir = ROOT / "reports" / "extraction" / "bundles"
    paths = sorted(bundle_dir.glob("*.extraction.json"))[:5]
    repo = SQLiteRepository(":memory:")
    importer = BundleImporter(repo)
    results = []
    try:
        for path in paths:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            importer.import_article_bundle(article_for(bundle["notice_id"], f"B fixed sample {bundle['notice_id']}"))
            first = importer.import_extraction_bundle(bundle)
            before = (repo.count_records(), repo.count_evidence())
            second = importer.import_extraction_bundle(bundle)
            after = (repo.count_records(), repo.count_evidence())
            results.append({"path": str(path.relative_to(ROOT)), "notice_id": bundle["notice_id"], "records": first.records, "evidence": first.evidence, "repeat_records": second.records, "repeat_counts_unchanged": before == after, "status": first.status})
        payload = {"generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "bundle_count": len(results), "article_count": repo.count_articles(), "record_count": repo.count_records(), "evidence_count": repo.count_evidence(), "items": results, "visibility_policy": "import preserves draft; admin publish is separate"}
    finally:
        repo.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if len(results) == 5 and all(item["repeat_counts_unchanged"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
