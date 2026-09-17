"""SyncService：唯一增量同步入口。

- 接收上次游标和当前会话，返回任务 ID、游标、成功数、失败数与状态。
- 逐篇保存状态与失败原因；notice_id 幂等；中断后只继续未完成项。
- CAS 会话失效时任务暂停（状态 failed + failure_reason=session_expired），
  已入库查询不受影响、不清空。
- Scheduler 只负责周期、单实例锁和调用本服务，采集逻辑只在这里。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from ..datasource.portal_client import PortalClient, SessionExpiredError
from .bundle import (build_article_bundle, content_type_for, sanitize_text,
                     asset_refs_for, write_bundle)
from .ledger import ArticleLedger, now_iso

SESSION_EXPIRED = "session_expired"


@dataclass
class SyncResult:
    task_id: str
    cursor: str | None
    success_count: int
    failure_count: int
    status: str  # processed / review_required / failed / running / pending
    failure_reason: str | None = None
    processed_ids: list = field(default_factory=list)


class SyncService:
    """增量同步：列表登记 → 详情采集 → bundle 输出 → 台账更新。"""

    def __init__(self, client_factory: Callable[[], PortalClient],
                 ledger: ArticleLedger, bundle_dir: str,
                 target_count: int = 100):
        self.client_factory = client_factory
        self.ledger = ledger
        self.bundle_dir = bundle_dir
        self.target_count = target_count

    # ------------------------------------------------------------------
    def sync(self, session, last_cursor: str | None = None,
             client: PortalClient | None = None) -> SyncResult:
        """执行一次增量同步。session 为内存中的已登录会话。"""
        client = client or self.client_factory()
        task_id = uuid.uuid4().hex[:12]
        success = 0
        failure = 0
        processed_ids: list[str] = []
        cursor = last_cursor

        # 1. 同步前验证会话（只读接口）
        try:
            client.validate_session()
        except SessionExpiredError:
            return SyncResult(task_id, cursor, 0, 0, "failed",
                              failure_reason=SESSION_EXPIRED)

        # 2. 列表阶段：登记目标（幂等 upsert）
        try:
            for item in client.iterate_notices():
                if len(self.ledger) >= self.target_count:
                    break
                self.ledger.register_from_list(item)
                cursor = item["notice_id"]
            self.ledger.save()
        except SessionExpiredError:
            return SyncResult(task_id, cursor, success, failure, "failed",
                              failure_reason=SESSION_EXPIRED)

        # 3. 详情阶段：只处理 pending 或允许重试的 failed 项
        for entry in self.ledger.pending_or_retryable():
            notice_id = entry["notice_id"]
            self.ledger.mark_attempt(notice_id)
            try:
                detail = client.get_notice(notice_id)
            except SessionExpiredError:
                self.ledger.mark_failed(notice_id, SESSION_EXPIRED)
                return SyncResult(task_id, cursor, success, failure, "failed",
                                  failure_reason=SESSION_EXPIRED)
            except Exception as exc:  # noqa: BLE001 - 失败原因逐篇落账
                self.ledger.mark_failed(notice_id, f"detail: {exc}")
                failure += 1
                continue

            try:
                bundle = self._build_bundle(detail)
                write_bundle(bundle, self.bundle_dir)
            except Exception as exc:  # noqa: BLE001
                self.ledger.mark_failed(notice_id, f"bundle: {exc}")
                failure += 1
                continue

            self.ledger.mark_processed(
                notice_id,
                title=detail.get("title") or entry.get("title", ""),
                content_type=bundle["content_type"],
                detail_status="ok",
                asset_status="ok" if bundle["asset_refs"] else "none",
            )
            success += 1
            processed_ids.append(notice_id)

        status = "processed" if failure == 0 else "review_required"
        return SyncResult(task_id, cursor, success, failure, status,
                          processed_ids=processed_ids)

    # ------------------------------------------------------------------
    def _build_bundle(self, detail: dict) -> dict:
        content_type = content_type_for(detail)
        return build_article_bundle(
            notice_id=str(detail["notice_id"]),
            title=detail.get("title") or "(无标题)",
            source_url=detail.get("source_url") or "",
            content_type=content_type,
            published_at=detail.get("published_at"),
            clean_text=sanitize_text(detail.get("content"))
            if content_type in ("text", "mixed") else None,
            asset_refs=asset_refs_for(detail),
            fetch_status="processed",
            failure_reason=None,
            fetched_at=now_iso(),
        )
