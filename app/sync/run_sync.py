"""100 篇采集状态台账的命令行入口（需人工 CAS 登录）。

用法（在仓库根目录）：
    python -m app.sync.run_sync --cas-base-url <CAS> --portal-base-url <门户> \
        --target 100 --ledger evidence/week1/A/ledger/article_ledger.json

流程：人工 CAS 登录 → 增量同步（列表登记 → 详情采集 → bundle 输出）→
打印状态统计与 notice_id 唯一性检查（供 A3 验收：无重复 notice_id）。
目标清单不足 target 时显示实际数量与缺口，不补造空记录。
"""
from __future__ import annotations

import argparse
import json

from ..datasource.cas_login import assisted_login
from ..datasource.config import PortalConfig
from ..datasource.portal_client import PortalClient, RequestsTransport
from ..datasource.rate import SystemClock
from .ledger import ArticleLedger
from .sync_service import SyncService


def main() -> int:
    parser = argparse.ArgumentParser(description="增量同步并维护采集状态台账")
    parser.add_argument("--cas-base-url", required=True)
    parser.add_argument("--portal-base-url", required=True)
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--ledger", default="evidence/week1/A/ledger/article_ledger.json")
    parser.add_argument("--bundles", default="evidence/week1/A/ledger/bundles")
    parser.add_argument("--last-cursor", default=None,
                        help="上次游标（断点续采：从台账未完成项继续）")
    args = parser.parse_args()

    config = PortalConfig.from_env()
    config.base_url = args.portal_base_url

    ledger = ArticleLedger(args.ledger)
    before = len(ledger)

    session = assisted_login(args.cas_base_url, args.portal_base_url)
    client = PortalClient(config, RequestsTransport(session), clock=SystemClock())
    service = SyncService(lambda: client, ledger, args.bundles,
                          target_count=args.target,
                          topic_keywords=config.topic_keywords)
    result = service.sync(session, last_cursor=args.last_cursor)

    # ---- 验收输出 ----
    entries = ledger.all_entries()
    ids = [e["notice_id"] for e in entries]
    stats = ledger.count_by_status()
    print("=" * 50)
    print(f"任务ID: {result.task_id}")
    print(f"游标: {result.cursor}")
    print(f"本轮成功: {result.success_count}  失败: {result.failure_count}")
    print(f"状态: {result.status}"
          + (f"（{result.failure_reason}）" if result.failure_reason else ""))
    print(f"台账总条目: {len(entries)}（同步前 {before}）")
    print(f"状态分布: {json.dumps(stats, ensure_ascii=False)}")
    print(f"notice_id 唯一性: {'通过' if len(ids) == len(set(ids)) else '存在重复！'}")
    if len(entries) < args.target:
        print(f"[缺口] 目标 {args.target} 篇，实际登记 {len(entries)} 篇；"
              f"缺口来源=门户列表实际返回数量，未补造空记录。")
    failed = [e for e in entries if e["final_status"] == "failed"]
    for e in failed[:10]:
        print(f"[failed] {e['notice_id']}: {e['failure_reason']}")
    print(f"台账文件: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
