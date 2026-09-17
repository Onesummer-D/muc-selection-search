"""采集 5 篇固定样本的命令行入口（需人工 CAS 登录）。

用法（在仓库根目录）：
    python -m app.sync.collect_fixed --count 5 --out evidence/week1/A/fixed_samples

流程：人工 CAS 登录（有界面浏览器）→ 内存会话 → 抓取列表 →
主题过滤（只留选调相关）→ 经验分享类优先排序 →
按 2 文本 / 2 海报 / 1 混合优先选择（不满足时保留真实构成并打印说明）→
输出 article_bundle.v1 JSON → Schema 校验 5/5 → 打印交接信息。

选样规则：必须与选调相关；经验分享类（经验/心得/上岸/备考等，
PORTAL_EXPERIENCE_KEYWORDS 可配）优先，纯选调通知仅在数量不足时补位。
"""
from __future__ import annotations

import argparse
import json

from ..datasource.cas_login import assisted_login
from ..datasource.config import PortalConfig
from ..datasource.portal_client import PortalClient, RequestsTransport
from ..datasource.rate import SystemClock
from .bundle import (build_article_bundle, content_type_for, sanitize_text,
                     asset_refs_for, validate_bundle, write_bundle,
                     html_to_text)
from .ledger import now_iso

DESIRED_COMPOSITION = {"text": 2, "poster": 2, "mixed": 1}


def matches_topic(detail: dict, keywords: tuple) -> bool:
    """标题或正文命中任一主题关键词即视为相关（keywords 为空时不过滤）。"""
    if not keywords:
        return True
    haystack = f"{detail.get('title') or ''}{detail.get('content') or ''}"
    return any(kw in haystack for kw in keywords)


def is_experience_sharing(detail: dict, experience_keywords: tuple) -> bool:
    """是否为经验分享类内容（标题命中倾向词，或正文开头命中）。"""
    if not experience_keywords:
        return True
    title = detail.get("title") or ""
    head = (detail.get("content") or "")[:500]
    return (any(kw in title for kw in experience_keywords)
            or any(kw in head for kw in experience_keywords))


def rank_by_relevance(details: list[dict], config) -> list[dict]:
    """排序：选调主题内的经验分享类优先，其余选调相关殿后。"""
    def score(d: dict) -> int:
        if not matches_topic(d, config.topic_keywords):
            return -1  # 非主题，直接排除
        return 1 if is_experience_sharing(d, config.experience_keywords) else 0
    ranked = sorted(details, key=score, reverse=True)
    return [d for d in ranked if score(d) >= 0]


def _pick_composition(details: list[dict], limit: int) -> tuple[list[dict], dict]:
    """在给定候选内按理想构成（2文本/2海报/1混合）挑选，不足保留真实构成。"""
    chosen: list[dict] = []
    composition = {"text": 0, "poster": 0, "mixed": 0, "unknown": 0}
    for kind, want in DESIRED_COMPOSITION.items():
        candidates = [d for d in details
                      if content_type_for(d) == kind and d not in chosen]
        for detail in candidates[:want]:
            if len(chosen) >= limit:
                return chosen, composition
            chosen.append(detail)
            composition[kind] += 1
    for detail in details:  # 补足（保留真实构成）
        if len(chosen) >= limit:
            break
        if detail not in chosen:
            chosen.append(detail)
            composition[content_type_for(detail)] += 1
    return chosen, composition


def pick_fixed_samples(details: list[dict],
                       experience_keywords: tuple = ()) -> tuple[list[dict], dict]:
    """两阶段选样：经验分享类优先；数量不足时才用其他选调相关内容补位。

    details 应已按相关性排序（rank_by_relevance）。
    """
    if experience_keywords:
        exp = [d for d in details
               if is_experience_sharing(d, experience_keywords)]
        rest = [d for d in details if d not in exp]
    else:
        exp, rest = list(details), []
    chosen, composition = _pick_composition(exp, 5)
    if len(chosen) < 5 and rest:
        more, comp2 = _pick_composition([d for d in rest if d not in chosen],
                                        5 - len(chosen))
        chosen += more
        for kind, cnt in comp2.items():
            composition[kind] += cnt
    return chosen, composition


def main() -> int:
    parser = argparse.ArgumentParser(description="采集 5 篇固定样本")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--out", default="evidence/week1/A/fixed_samples")
    parser.add_argument("--cas-base-url", default=None,
                        help="省略并给出 --from-pool 时无需登录")
    parser.add_argument("--portal-base-url", default=None)
    parser.add_argument("--pool-path", default="../candidates_pool.json",
                        help="选调相关候选池缓存（仓库外，避免整池内容入库）")
    parser.add_argument("--from-pool", action="store_true",
                        help="用已缓存的候选池重新选样（无需登录）")
    args = parser.parse_args()

    config = PortalConfig.from_env()

    if args.from_pool:
        with open(args.pool_path, encoding="utf-8") as fh:
            details = json.load(fh)
        print(f"[pool] 从缓存载入候选池 {len(details)} 篇（未登录）")
    else:
        if not (args.cas_base_url and args.portal_base_url):
            parser.error("需要 --cas-base-url 与 --portal-base-url（或使用 --from-pool）")
        config.base_url = args.portal_base_url
        session = assisted_login(args.cas_base_url, args.portal_base_url)
        client = PortalClient(config, RequestsTransport(session), clock=SystemClock())

        details = []
        skipped_off_topic = 0
        for item in client.iterate_notices():
            if len(details) >= args.count * 4:  # 候选池
                break
            try:
                detail = client.get_notice(item["notice_id"])
            except Exception as exc:  # noqa: BLE001 - 记录并继续
                print(f"[skip] {item['notice_id']}: {exc}")
                continue
            if not matches_topic(detail, config.topic_keywords):
                skipped_off_topic += 1
                continue
            details.append(detail)
        if skipped_off_topic:
            print(f"[filter] 已跳过非{'/'.join(config.topic_keywords)}内容"
                  f" {skipped_off_topic} 篇")
        if not details:
            print(f"[error] 候选池中没有命中主题关键词（{config.topic_keywords}）的文章，"
                  "请确认栏目 ID 或关键词配置。")
            return 1
        # 缓存候选池（仓库外文件，重新选样无需再次登录）
        with open(args.pool_path, "w", encoding="utf-8") as fh:
            json.dump(details, fh, ensure_ascii=False, indent=1)
        print(f"[pool] 候选池已缓存到 {args.pool_path}")

    # 经验分享类优先：先统计，供选择与交接说明
    exp_count = sum(1 for d in details
                    if is_experience_sharing(d, config.experience_keywords))
    print(f"[filter] 选调相关 {len(details)} 篇，其中经验分享类 {exp_count} 篇（优先入选）")
    details = rank_by_relevance(details, config)

    chosen, composition = pick_fixed_samples(details,
                                             config.experience_keywords)
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
            clean_text=sanitize_text(html_to_text(detail.get("content")))
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
