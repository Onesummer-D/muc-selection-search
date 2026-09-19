"""Issue #7 补采：按 B 指定的 6 个 notice_id 补充采集 + bundle + 台账更新。

用法（仓库根目录）：
    python run_supplement.py

流程：人工 CAS 登录（Playwright 窗口）→ 列表迭代定位 6 篇 →
逐篇取详情 + 下载海报原图算 SHA-256（原图存仓库外 controlled_assets）→
构造 article_bundle.v1（脱敏）写 evidence/week1/A/supplements/ →
台账追加 6 条 processed → 导出 CSV → 打印汇总。

B 指定 notice_id：246166、246164、240863、240809、239413、239151
（工单：docs/week1/07_补充采集工单_B给A.md，以 issue #7 内容为准）
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.datasource.cas_login import assisted_login  # noqa: E402
from app.datasource.config import PortalConfig  # noqa: E402
from app.datasource.portal_client import (  # noqa: E402
    PortalClient, RequestsTransport)
from app.datasource.rate import SystemClock  # noqa: E402
from app.sync.bundle import (  # noqa: E402
    asset_refs_for, build_article_bundle, content_type_for, html_to_text,
    sanitize_text, validate_bundle, write_bundle)
from app.sync.ledger import ArticleLedger, now_iso  # noqa: E402

CAS_URL = "https://ca.muc.edu.cn/zfca"
PORTAL_URL = "https://my.muc.edu.cn"
TARGET_IDS = ["246166", "246164", "240863", "240809", "239413", "239151"]

LEDGER_JSON = ROOT / "evidence" / "week1" / "A" / "ledger" / "article_ledger.json"
LEDGER_CSV = ROOT / "evidence" / "week1" / "A" / "ledger" / "collection_ledger.csv"
SUPP_DIR = ROOT / "evidence" / "week1" / "A" / "supplements"
ASSETS_DIR = ROOT.parent / "controlled_assets"  # 仓库外，交接 B 走受控渠道

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/126.0 Safari/537.36")

CSV_FIELDS = [
    "notice_id", "title", "content_type",
    "list_status", "detail_status", "asset_status", "final_status",
    "failure_reason",
    "attempt_count", "first_seen_at", "last_attempt_at",
]


def write_csv(entries: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for e in entries:
            w.writerow({k: e.get(k, "") for k in CSV_FIELDS})


def download_images(detail: dict, sleep_seconds: float = 1.0) -> tuple[int, list]:
    """下载该篇海报原图到仓库外目录并回写 images[i]["sha256"]。

    返回 (成功数, 失败列表)。仅匿名可访问的门户 upload 资源。
    """
    session = requests.Session()
    session.headers["User-Agent"] = UA
    ok, failed = 0, []
    for idx, image in enumerate(detail.get("images") or [], start=1):
        if not isinstance(image, dict) or not image.get("url"):
            continue
        asset_id = f"{detail['notice_id']}-poster-{idx:02d}"
        if image.get("sha256"):
            ok += 1
            continue
        url = image["url"].replace("http://my.muc.edu.cn:80/", "https://my.muc.edu.cn/")
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.content
            if len(data) < 100 or data[:4] not in (
                    b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1",  # JPEG
                    b"\x89PNG", b"GIF8", b"RIFF"):
                failed.append({"asset_id": asset_id, "reason": f"非图片响应({len(data)}B)"})
                continue
        except requests.RequestException as exc:
            failed.append({"asset_id": asset_id, "reason": str(exc)[:120]})
            continue
        import hashlib
        article_dir = ASSETS_DIR / str(detail["notice_id"])
        article_dir.mkdir(parents=True, exist_ok=True)
        (article_dir / f"{asset_id}.jpg").write_bytes(data)
        image["sha256"] = hashlib.sha256(data).hexdigest()
        ok += 1
        print(f"  [asset] {asset_id} <- {len(data)}B sha256={image['sha256'][:16]}…")
        time.sleep(sleep_seconds)
    return ok, failed


def main() -> int:
    print("[S7] 启动（issue #7 补采 6 篇）。即将打开 Playwright 窗口，请登录信息门户。")
    start = time.time()
    session = assisted_login(CAS_URL, PORTAL_URL)

    config = PortalConfig.from_env()
    config.base_url = PORTAL_URL
    client = PortalClient(config, RequestsTransport(session), clock=SystemClock())

    target_set = set(TARGET_IDS)
    found_rows: dict[str, dict] = {}
    print(f"[S7] 迭代就业信息栏目列表，定位 {len(TARGET_IDS)} 篇…")
    for item in client.iterate_notices():
        nid = str(item["notice_id"])
        if nid in target_set and nid not in found_rows:
            found_rows[nid] = client._row_cache[nid]
            print(f"  [list] 找到 {nid}（已定位 {len(found_rows)}/{len(TARGET_IDS)}）")
        if len(found_rows) == len(target_set):
            break
    missing = [i for i in TARGET_IDS if i not in found_rows]
    if missing:
        print(f"[S7][warn] 就业信息栏目列表未找到: {missing}（可能在其他栏目，"
              "这部分稍后单独处理）")

    ledger = ArticleLedger(str(LEDGER_JSON))
    print(f"[S7] 复用已有台账条目: {len(ledger)}")

    report = []
    all_failed_assets = []
    for nid in TARGET_IDS:
        if nid not in found_rows:
            continue
        try:
            detail = client.get_notice(nid)
        except Exception as exc:  # noqa: BLE001
            print(f"  [fail] {nid}: {exc}")
            ledger.upsert(nid, title=ledger.get(nid, {}).get("title", "")
                          if ledger.get(nid) else "")
            ledger.mark_failed(nid, str(exc)[:200])
            continue
        ledger.mark_attempt(nid)
        ctype = content_type_for(detail)
        print(f"  [detail] {nid} 「{detail.get('title')}」 type={ctype}")
        if detail.get("images"):
            ok, failed = download_images(detail)
            all_failed_assets += failed
        else:
            ok, failed = 0, []
        bundle = build_article_bundle(
            notice_id=str(detail["notice_id"]),
            title=detail.get("title") or "(无标题)",
            source_url=detail.get("source_url") or "",
            content_type=ctype,
            published_at=detail.get("published_at"),
            clean_text=(sanitize_text(html_to_text(detail.get("content")))
                        if ctype in ("text", "mixed") else None),
            asset_refs=asset_refs_for(detail),
            fetch_status="processed",
            failure_reason=None,
            fetched_at=now_iso(),
        )
        path = write_bundle(bundle, str(SUPP_DIR))
        validate_bundle(json.loads(Path(path).read_text(encoding="utf-8")))
        print(f"  [bundle] {nid} -> {path}")

        ledger.upsert(
            nid,
            title=detail.get("title") or "",
            content_type=ctype,
            list_status="ok",
            detail_status="fetched" if detail.get("content") else "no_content",
            asset_status="ok" if ok else ("pending" if detail.get("images") else "n/a"),
        )
        ledger.mark_processed(nid)
        report.append({"notice_id": nid, "title": detail.get("title") or "",
                       "content_type": ctype, "bundle": path,
                       "assets_ok": ok, "assets_failed": failed})

    ledger.save()
    write_csv(ledger.all_entries(), LEDGER_CSV)

    # 汇总
    entries = ledger.all_entries()
    stats = ledger.count_by_status()
    elapsed = time.time() - start
    print("=" * 56)
    print(f"[S7] 完成。耗时 {elapsed:.1f}s")
    print(f"[S7] 补采成功 {len(report)}/{len(TARGET_IDS)}")
    for r in report:
        print(f"  - {r['notice_id']} ({r['content_type']}) 「{r['title'][:30]}」"
              f" assets={r['assets_ok']}")
    if missing:
        print(f"[S7][缺] 列表未定位: {missing}")
    if all_failed_assets:
        print(f"[S7][asset失败] {len(all_failed_assets)} 张：")
        for f in all_failed_assets:
            print(f"  - {f['asset_id']}: {f['reason']}")
    print(f"[S7] 台账总条目: {len(entries)}，状态分布: "
          f"{json.dumps(stats, ensure_ascii=False)}")
    print(f"[S7] bundle 目录: {SUPP_DIR}")
    print(f"[S7] 原图目录（仓库外）: {ASSETS_DIR}")

    # REPORT.json（交接 B/C 用）
    report_path = SUPP_DIR / "REPORT.json"
    report_path.write_text(json.dumps(
        {"issue": 7, "requested_by": "B",
         "target_notice_ids": TARGET_IDS,
         "collected": report, "missing": missing,
         "generated_at": now_iso()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[S7] 交接报告: {report_path}")
    return 0 if len(report) == len(TARGET_IDS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
