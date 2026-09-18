"""100 篇采集状态台账。

- 逐篇保存状态和失败原因（每篇结束立即落盘）。
- notice_id 唯一：重复运行做更新，不产生重复记录。
- 恢复：只处理 pending 或明确允许重试的 failed 项。
- 字段：notice_id、标题、内容类型、列表获取状态、详情获取状态、素材状态、
  最终状态、失败原因、首次发现时间、最后尝试时间、尝试次数。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

LIST_STATUS = ("ok", "failed")
DETAIL_STATUS = ("ok", "failed", "skipped")
ASSET_STATUS = ("ok", "failed", "skipped", "none")
FINAL_STATUS = ("pending", "processed", "review_required", "failed")
# failed 项允许重试的最大尝试次数（超过后需人工决定）
MAX_AUTO_RETRY_ATTEMPTS = 4


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ArticleLedger:
    """基于 JSON 文件的采集台账。"""

    def __init__(self, path: str):
        self.path = path
        self._entries: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            # 兼容两种布局：{entries:[...]} 或 [ ... ]
            rows = data.get("entries", []) if isinstance(data, dict) else data
            for row in rows:
                self._entries[str(row["notice_id"])] = row

    def save(self) -> None:
        """原子写入（临时文件 + 替换），逐篇保存时调用。"""
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"entries": list(self._entries.values())},
                          fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ------------------------------------------------------------------
    def upsert(self, notice_id: str, **fields) -> dict:
        """幂等插入或更新（notice_id 唯一）。返回更新后的条目。"""
        entry = self._entries.get(notice_id)
        if entry is None:
            entry = {
                "notice_id": notice_id,
                "title": "",
                "content_type": "unknown",
                "list_status": "pending",
                "detail_status": "pending",
                "asset_status": "pending",
                "final_status": "pending",
                "failure_reason": None,
                "first_seen_at": now_iso(),
                "last_attempt_at": None,
                "attempt_count": 0,
            }
            self._entries[notice_id] = entry
        entry.update(fields)
        return entry

    def register_from_list(self, item: dict) -> dict:
        """登记/更新列表阶段信息（不覆盖已有进度字段）。"""
        return self.upsert(
            item["notice_id"],
            title=item.get("title", ""),
            list_status="ok",
        )

    def mark_attempt(self, notice_id: str) -> None:
        entry = self._entries.get(notice_id)
        if entry is not None:
            entry["last_attempt_at"] = now_iso()
            entry["attempt_count"] = int(entry.get("attempt_count", 0)) + 1

    def mark_failed(self, notice_id: str, reason: str) -> None:
        self.upsert(notice_id, final_status="failed", failure_reason=reason)
        self.save()

    def mark_processed(self, notice_id: str, **extra) -> None:
        fields = {"final_status": "processed", "failure_reason": None}
        fields.update(extra)
        self.upsert(notice_id, **fields)
        self.save()

    # ------------------------------------------------------------------
    def get(self, notice_id: str) -> dict | None:
        return self._entries.get(notice_id)

    def all_entries(self) -> list[dict]:
        return list(self._entries.values())

    def pending_or_retryable(self) -> list[dict]:
        """恢复入口：只处理 pending 或明确允许重试的 failed 项。"""
        out = []
        for entry in self._entries.values():
            if entry["final_status"] == "pending":
                out.append(entry)
            elif (entry["final_status"] == "failed"
                  and entry.get("attempt_count", 0) < MAX_AUTO_RETRY_ATTEMPTS):
                out.append(entry)
        return out

    def count_by_status(self) -> dict[str, int]:
        stats = {s: 0 for s in FINAL_STATUS}
        for entry in self._entries.values():
            stats[entry["final_status"]] = stats.get(entry["final_status"], 0) + 1
        return stats

    def notice_ids(self) -> set[str]:
        return set(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
