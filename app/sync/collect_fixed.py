"""采集 5 篇固定样本的命令行入口（需人工 CAS 登录）。

用法（在仓库根目录）：
    python -m app.sync.collect_fixed --count 5 --out evidence/week1/A/fixed_samples

流程：人工 CAS 登录（有界面浏览器）→ 内存会话 → 抓取列表 →
按 2 文本 / 2 海报 / 1 混合优先选择（不满足时保留真实构成并打印说明）→
输出 article_bundle.v1 JSON → Schema 校验 5/5 → 打印交接信息。
"""
from __future__ import annotations

import argparse
import json

from ..datasource.cas_login import assisted_login
from ..datasource.config import PortalConfig
from ..datasource.portal_client import PortalClient, RequestsTransport
from ..datasource.rate import SystemClock
from .bundle import (build_article_bundle, content_type_for, sanitize_text,
                     asset_refs_for, validate_bundle, write_bundle)
from .ledger import now_iso

DESIRED_COMPOSITION = {"text": 2, "poster": 2, "mixed": 1}


def pick_fixed_samples(details: list[dict]) -> tuple[list[dict], dict]:
    """按理想构成挑选 5 篇；不足时保留真实构成。"""
    chosen: list[dict] = []
    composition = {"text": 0, "poster": 0, "mixed": 0, "unknown": 0}
    for kind, want in DESIRED_COMPOSITION.items():
        candidates = [d for d in details
                      if content_type_for(d) == kind and d not in chosen]
        for detail in candidates[:want]:
            chosen.append(detail)
            composition[kind] += 1
    # 补足到 5 篇（保留真实构成）
    for detail in details:
        if len(chosen) >= 5:
            break
        if detail not in chosen:
            chosen.append(detail)
            composition[content_type_for(detail)] += 1
    return chosen, composition


def main() -> int:
    parser = argparse.ArgumentParser(description="采集 5 篇固定样本")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--out", default="evidence/week1/A/fixed_samples")
    parser.add_argument("--cas-base-url", required=True)
    parser.add_argument("--portal-base-url", required=True)
    args = parser.parse_args()

    config = PortalConfig.from_env()
    config.base_url = args.portal_base_url

    session = assisted_login(args.cas_base_url, args.portal_base_url)
    client = PortalClient(config, RequestsTransport(session), clock=SystemClock())

    details: list[dict] = []
    for item in client.iterate_notices():
        if len(details) >= args.count * 4:  # 候选池
            break
        try:
            details.append(client.get_notice(item["notice_id"]))
        except Exception as exc:  # noqa: BLE001 - 记录并继续
            print(f"[skip] {item['notice_id']}: {exc}")

    chosen, composition = pick_fixed_samples(details)
    print(f"[composition] 实际构成: {json.dumps(composition, ensure_ascii=False)}")
    if composition != {"text": 2, "poster": 2, "mixed": 1, "unknown": 0}:
        print("[composition] 注意：与理想构成（2文本/2海报/1混合）不符，"
              "已保留真实构成，请在交接表中说明。")

    report = []
    for detail in chosen[:args.count]:
        ctype = content_type_for(detail)
        bundle = build_article_bundle(
            notice_id=str(detail["notice_id"]),
            title=detail.get("title") or "(无标题)",
            source_url=detail.get("source_url") or "",
            content_type=ctype,
            published_at=detail.get("published_at"),
            clean_text=sanitize_text(detail.get("content"))
            if ctype in ("text", "mixed") else None,
            asset_refs=asset_refs_for(detail),
            fetch_status="processed",
            failure_reason=None,
            fetched_at=now_iso(),
        )
        path = write_bundle(bundle, args.out)
        report.append({"notice_id": bundle["notice_id"],
                       "content_type": ctype, "path": path})
        print(f"[ok] {bundle['notice_id']} ({ctype}) -> {path}")

    # 校验全部通过
    for row in report:
        with open(row["path"], encoding="utf-8") as fh:
            validate_bundle(json.load(fh))
    print(f"[validate] {len(report)}/{len(report)} 通过 article_bundle.v1 校验")
    with open(f"{args.out}/REPORT.json", "w", encoding="utf-8") as fh:
        json.dump({"samples": report, "composition": composition,
                   "generated_at": now_iso()}, fh, ensure_ascii=False, indent=2)
    print(f"[done] 交接信息已写入 {args.out}/REPORT.json，请把 commit 发给 B 和 C")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
