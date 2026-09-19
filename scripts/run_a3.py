"""A3 一体化：登录 → 同步 100 篇 → 导出 CSV → 落盘。

供本机运行：人工在弹出的 Playwright 窗口登录一次，脚本接管后续。
不需要任何命令行参数，所有路径相对工作区根。
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # 仓库根（脚本位于 scripts/）
sys.path.insert(0, str(ROOT))

# 关键：A3 任务书要求 100 篇「采集状态台账」，不强制主题过滤；
# 这里清空主题过滤，让台账覆盖整个就业信息栏目的真实表现。
os.environ["PORTAL_TOPIC_KEYWORDS"] = ""

from app.datasource.cas_login import assisted_login  # noqa: E402
from app.datasource.config import PortalConfig  # noqa: E402
from app.datasource.portal_client import (  # noqa: E402
    PortalClient, RequestsTransport)
from app.datasource.rate import SystemClock  # noqa: E402
from app.sync.ledger import ArticleLedger  # noqa: E402
from app.sync.sync_service import SyncService  # noqa: E402

CAS_URL = "https://ca.muc.edu.cn/zfca"
PORTAL_URL = "https://my.muc.edu.cn"
LEDGER_JSON = ROOT / "evidence" / "week1" / "A" / "ledger" / "article_ledger.json"
LEDGER_CSV = ROOT / "evidence" / "week1" / "A" / "ledger" / "collection_ledger.csv"
BUNDLES_DIR = ROOT / "evidence" / "week1" / "A" / "ledger" / "bundles"


def write_csv(entries: list[dict], path: Path) -> None:
    """把台账导出为 CSV（A3 验收交付物）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "notice_id", "title", "content_type",
        "list_status", "detail_status", "asset_status", "final_status",
        "failure_reason",
        "attempt_count", "first_seen_at", "last_attempt_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for e in entries:
            w.writerow({k: e.get(k, "") for k in fields})


def main() -> int:
    print("[A3] 启动。即将打开 Playwright 窗口，请登录中央民族大学信息门户。")
    print(f"[A3] CAS: {CAS_URL}")
    print(f"[A3] Portal: {PORTAL_URL}")
    start = time.time()
    session = assisted_login(CAS_URL, PORTAL_URL)

    config = PortalConfig.from_env()
    config.base_url = PORTAL_URL
    print(f"[A3] 配置: type={config.list_params.get('type')} "
          f"page_size={config.page_size} "
          f"topic_keywords={config.topic_keywords!r}")

    ledger = ArticleLedger(str(LEDGER_JSON))
    print(f"[A3] 复用已有台账条目: {len(ledger)}")

    client = PortalClient(config, RequestsTransport(session), clock=SystemClock())
    service = SyncService(
        lambda: client,
        ledger,
        str(BUNDLES_DIR),
        target_count=100,
        topic_keywords=config.topic_keywords,
    )
    result = service.sync(session)
    ledger.save()

    # CSV 导出
    write_csv(ledger.all_entries(), LEDGER_CSV)

    entries = ledger.all_entries()
    ids = [e["notice_id"] for e in entries]
    stats = ledger.count_by_status()
    elapsed = time.time() - start
    print("=" * 56)
    print(f"[A3] 完成。耗时 {elapsed:.1f}s")
    print(f"[A3] 任务ID: {result.task_id}")
    print(f"[A3] 本轮成功 {result.success_count} / 失败 {result.failure_count}")
    print(f"[A3] 状态: {result.status}"
          + (f"（{result.failure_reason}）" if result.failure_reason else ""))
    print(f"[A3] 台账总条目: {len(entries)}（去重: {len(set(ids))}）")
    print(f"[A3] 状态分布: {json.dumps(stats, ensure_ascii=False)}")
    print(f"[A3] notice_id 唯一性: {'通过' if len(ids) == len(set(ids)) else '存在重复！'}")
    if len(entries) < 100:
        print(f"[A3][缺口] 目标 100，实际 {len(entries)}；"
              "缺口来源=门户列表实际返回数量，未补造空记录。")
    failed = [e for e in entries if e["final_status"] == "failed"]
    for e in failed[:10]:
        print(f"[A3][failed] {e['notice_id']}: {e['failure_reason']}")
    print(f"[A3] 台账 JSON: {LEDGER_JSON}")
    print(f"[A3] 台账 CSV : {LEDGER_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())