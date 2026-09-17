"""台账测试：幂等、恢复、逐篇保存、重复运行不增量。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from app.sync.ledger import ArticleLedger


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "ledger.json")

    def test_upsert_idempotent(self):
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "n1", "title": "t1"})
        ledger.register_from_list({"notice_id": "n1", "title": "t1-updated"})
        ledger.save()
        self.assertEqual(len(ledger), 1)  # notice_id 唯一：更新而非新增
        self.assertEqual(ledger.get("n1")["title"], "t1-updated")

    def test_rerun_does_not_increase(self):
        ledger = ArticleLedger(self.path)
        for i in range(5):
            ledger.register_from_list({"notice_id": f"n{i}", "title": f"t{i}"})
        ledger.save()
        # 重新加载并重复登记（模拟重复运行）
        ledger2 = ArticleLedger(self.path)
        for i in range(5):
            ledger2.register_from_list({"notice_id": f"n{i}", "title": f"t{i}"})
        ledger2.save()
        self.assertEqual(len(ledger2), 5)

    def test_mark_failed_saves_immediately(self):
        # 逐篇保存：不调用 save() 也应落盘（中断后已完成项仍在）
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "n1", "title": "t"})
        ledger.mark_failed("n1", "detail: HTTP 500")
        ledger2 = ArticleLedger(self.path)
        self.assertEqual(ledger2.get("n1")["final_status"], "failed")
        self.assertIn("500", ledger2.get("n1")["failure_reason"])

    def test_pending_or_retryable_filters(self):
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "p1", "title": "t"})
        ledger.register_from_list({"notice_id": "p2", "title": "t"})
        ledger.mark_processed("p1")
        ledger.register_from_list({"notice_id": "f1", "title": "t"})
        ledger.mark_failed("f1", "x")
        # f1 尝试次数已达上限（mark_attempt 一次 + 失败时已 1 次）
        for _ in range(5):
            ledger.mark_attempt("f1")
        todo = [e["notice_id"] for e in ledger.pending_or_retryable()]
        self.assertIn("p2", todo)       # pending 继续
        self.assertNotIn("p1", todo)    # processed 不再处理
        self.assertNotIn("f1", todo)    # 超过重试上限的 failed 不自动处理

    def test_failed_within_retry_still_processed(self):
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "f2", "title": "t"})
        ledger.mark_failed("f2", "temporary")
        todo = [e["notice_id"] for e in ledger.pending_or_retryable()]
        self.assertIn("f2", todo)  # 明确允许重试的 failed 继续

    def test_count_by_status(self):
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "a", "title": ""})
        ledger.register_from_list({"notice_id": "b", "title": ""})
        ledger.mark_processed("a")
        self.assertEqual(ledger.count_by_status(),
                         {"pending": 1, "processed": 1,
                          "review_required": 0, "failed": 0})

    def test_ledger_fields_complete(self):
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "n9", "title": "t"})
        entry = ledger.get("n9")
        expected = {"notice_id", "title", "content_type", "list_status",
                    "detail_status", "asset_status", "final_status",
                    "failure_reason", "first_seen_at", "last_attempt_at",
                    "attempt_count"}
        self.assertTrue(expected.issubset(entry.keys()))

    def test_json_serializable(self):
        ledger = ArticleLedger(self.path)
        ledger.register_from_list({"notice_id": "n1", "title": "中文标题"})
        ledger.save()
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["entries"][0]["title"], "中文标题")


if __name__ == "__main__":
    unittest.main()
