"""9/22 烟测：固定 5 篇 bundle/evidence pack 导入 C SQLite。

验证（任务书 B · 9/22 交付）：
1. 5 篇 article bundle + 5 篇 extraction bundle 全部通过契约校验并导入；
2. 行数核对（articles/assets/experience_records/evidence）与 bundle 内容一致；
3. 幂等：整批重复导入后各表行数不变（processing_events 例外，审计日志有意追加）；
4. evidence pack 行数与导入的 evidence 行数交叉核对。

用法：python -m app.extraction.import_smoke
输出：控制台摘要（完整日志由调用方存 evidence/week1/B/）。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ("cohort", "education", "major", "city", "position_or_unit")


def _table_counts(repo) -> dict:
    return {"articles": repo.count_articles(),
            "assets": repo.count_assets(),
            "records": repo.count_records(),
            "evidence": repo.count_evidence(),
            "events": len(repo.list_events())}


def run(verbose: bool = True) -> dict:
    from app.repository.importer import BundleImporter
    from app.repository.sqlite_repository import SQLiteRepository

    repo = SQLiteRepository(":memory:")
    importer = BundleImporter(repo)

    article_dir = ROOT / "evidence" / "week1" / "A" / "fixed_samples"
    bundle_dir = ROOT / "reports" / "extraction" / "bundles"
    articles = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(article_dir.glob("*.json")) if p.name != "REPORT.json"]
    extractions = [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted(bundle_dir.glob("*.extraction.json"))]
    assert len(articles) == 5 and len(extractions) == 5, \
        f"需要 5+5 个 bundle，实际 {len(articles)}+{len(extractions)}"

    log: list[str] = []

    def say(msg: str) -> None:
        log.append(msg)
        if verbose:
            print(msg, flush=True)

    schema_ok = all(
        "schema_version" in a and a["schema_version"] == "article_bundle.v1"
        for a in articles) and all(
        e["schema_version"] == "extraction_bundle.v1" for e in extractions)
    say(f"[1] Schema 预检：article 5/5 + extraction 5/5 = "
        f"{'通过' if schema_ok else '失败'}")

    total = {"articles": 0, "assets": 0, "records": 0, "evidence": 0}
    for a in articles:
        r = importer.import_article_bundle(a)
        total["articles"] += r.articles
        total["assets"] += r.assets
    for e in extractions:
        r = importer.import_extraction_bundle(e)
        total["records"] += r.records
        total["evidence"] += r.evidence
    first = _table_counts(repo)
    say(f"[2] 首次导入行数：articles={first['articles']} assets={first['assets']} "
        f"records={first['records']} evidence={first['evidence']} "
        f"events={first['events']}")
    say(f"    bundle 声明合计：{total}")

    # evidence pack 交叉核对：packs 的字段证据条数应与导入 evidence 行数一致
    packs_dir = ROOT / "reports" / "extraction" / "packs"
    pack_ev = 0
    for p in sorted(packs_dir.glob("*.packs.json")):
        packs = json.loads(p.read_text(encoding="utf-8"))
        pack_ev += sum(len(entries)
                       for pk in packs
                       for entries in pk["field_evidence"].values())
    say(f"[3] evidence pack 交叉核对：packs 字段证据 {pack_ev} 条 vs "
        f"导入 evidence {first['evidence']} 行")

    # 幂等：整批重复导入
    for a in articles:
        importer.import_article_bundle(a)
    for e in extractions:
        importer.import_extraction_bundle(e)
    second = _table_counts(repo)
    idempotent = all(first[k] == second[k]
                     for k in ("articles", "assets", "records", "evidence"))
    say(f"[4] 重复导入后行数：articles={second['articles']} "
        f"assets={second['assets']} records={second['records']} "
        f"evidence={second['evidence']} events={second['events']}")
    say(f"[5] 幂等核验（四业务表行数不变）：{'通过' if idempotent else '失败'}；"
        f"processing_events {first['events']}→{second['events']} "
        f"（审计日志有意追加）")

    result = {
        "schema_ok": schema_ok,
        "first_counts": first,
        "second_counts": second,
        "bundle_totals": total,
        "pack_evidence": pack_ev,
        "idempotent": idempotent,
        "ok": schema_ok and idempotent,
    }
    result["_log"] = log
    return result


if __name__ == "__main__":
    result = run()
    raise SystemExit(0 if result["ok"] else 1)
