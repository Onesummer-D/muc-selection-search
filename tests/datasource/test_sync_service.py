"""SyncService 测试：游标、成功/失败计数、会话失效暂停、恢复与幂等。"""
from __future__ import annotations

import os
import tempfile
import unittest

from app.datasource.config import PortalConfig
from app.datasource.portal_client import PortalClient
from app.sync.ledger import ArticleLedger
from app.sync.sync_service import SyncService
from tests.datasource.fake_portal import FakeClock, FakePortal


def make_service(portal: FakePortal, details: dict, tmp: str,
                 pages=None, target=100):
    clock = FakeClock()
    config = PortalConfig(base_url="https://portal.invalid")
    client = PortalClient(config, portal, clock=clock, sleep=clock.sleep)
    ledger = ArticleLedger(os.path.join(tmp, "ledger.json"))
    svc = SyncService(lambda: client, ledger, os.path.join(tmp, "bundles"),
                      target_count=target)
    return svc, ledger, portal


def detail(nid: str, content="正文", images=None) -> dict:
    return {"noticeId": nid, "title": f"标题{nid}", "content": content,
            "publishTime": "2026-09-10T08:00:00+08:00",
            "url": f"https://portal.invalid/notice/{nid}",
            "images": images or []}


class TestSyncService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_sync_counts_and_cursor(self):
        details = {f"n{i}": detail(f"n{i}") for i in range(3)}
        portal = FakePortal(pages={1: [{"noticeId": f"n{i}"} for i in range(3)]},
                            details=details)
        svc, ledger, _ = make_service(portal, details, self.tmp)
        result = svc.sync(session=None)
        self.assertEqual(result.success_count, 3)
        self.assertEqual(result.failure_count, 0)
        self.assertEqual(result.status, "processed")
        self.assertEqual(result.cursor, "n2")

    def test_failed_detail_recorded(self):
        details = {"n1": detail("n1")}  # n2 无详情 → 404
        portal = FakePortal(pages={1: [{"noticeId": "n1"}, {"noticeId": "n2"}]},
                            details=details)
        svc, ledger, _ = make_service(portal, details, self.tmp)
        result = svc.sync(session=None)
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failure_count, 1)
        self.assertEqual(result.status, "review_required")
        self.assertEqual(ledger.get("n2")["final_status"], "failed")
        self.assertTrue(ledger.get("n2")["failure_reason"])

    def test_session_expired_before_sync(self):
        portal = FakePortal(script=[("status", 401)])
        svc, ledger, _ = make_service(portal, {}, self.tmp)
        result = svc.sync(session=None)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_reason, "session_expired")
        # 会话失效不清空已入库结果
        self.assertEqual(len(ledger), 0)

    def test_session_expired_midway_keeps_processed(self):
        details = {"n1": detail("n1")}
        # 列表正常（第1页1条），详情阶段会话失效
        portal = FakePortal(pages={1: [{"noticeId": "n1"}, {"noticeId": "n2"}]},
                            details=details)
        svc, ledger, _ = make_service(portal, details, self.tmp)
        # 让 n1 先成功，n2 详情时 401
        original_get = portal.get

        state = {"n1_done": False}

        def scripted_get(url, params, timeout):
            if "getNotice" in url and params.get("noticeId") == "n2":
                from tests.datasource.fake_portal import FakeResponse
                return FakeResponse(401, None)
            return original_get(url, params, timeout)

        portal.get = scripted_get
        result = svc.sync(session=None)
        self.assertEqual(result.failure_reason, "session_expired")
        # n1 已完成，n2 标记失败且原因可追溯
        self.assertEqual(ledger.get("n1")["final_status"], "processed")
        self.assertEqual(ledger.get("n2")["final_status"], "failed")

    def test_resume_after_interrupt(self):
        details = {f"n{i}": detail(f"n{i}") for i in range(3)}
        portal = FakePortal(pages={1: [{"noticeId": f"n{i}"} for i in range(3)]},
                            details=details)
        svc, ledger, _ = make_service(portal, details, self.tmp)
        # 模拟中断：n1 已 processed，n2/n3 pending
        ledger.register_from_list({"notice_id": "n1", "title": "标题n1"})
        ledger.mark_processed("n1", content_type="text")
        result = svc.sync(session=None)
        self.assertEqual(result.success_count, 2)  # 只补 n2/n3
        self.assertEqual(len(ledger), 3)           # 不重复

    def test_rerun_idempotent(self):
        details = {f"n{i}": detail(f"n{i}") for i in range(3)}
        portal = FakePortal(pages={1: [{"noticeId": f"n{i}"} for i in range(3)]},
                            details=details)
        svc, ledger, _ = make_service(portal, details, self.tmp)
        first = svc.sync(session=None)
        second = svc.sync(session=None)
        self.assertEqual(len(ledger), 3)           # 连续运行两次文章数不增加
        self.assertEqual(second.success_count, 0)  # 无未完成项

    def test_target_count_limit(self):
        details = {f"n{i}": detail(f"n{i}") for i in range(10)}
        portal = FakePortal(pages={1: [{"noticeId": f"n{i}"} for i in range(10)]},
                            details=details)
        svc, ledger, _ = make_service(portal, details, self.tmp, target=5)
        svc.sync(session=None)
        self.assertEqual(len(ledger), 5)


if __name__ == "__main__":
    unittest.main()


class TestTopicFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_off_topic_not_registered(self):
        details = {"n1": detail("n1"), "n2": detail("n2"),
                   "off1": detail("off1", content="无关内容")}
        portal = FakePortal(pages={1: [{"noticeId": "n1", "title": "选调公告"},
                                       {"noticeId": "n2", "title": "选调经验分享"},
                                       {"noticeId": "off1", "title": "普通通知"}]},
                            details=details)
        clock = FakeClock()
        config = PortalConfig(base_url="https://portal.invalid")
        client = PortalClient(config, portal, clock=clock, sleep=clock.sleep)
        ledger = ArticleLedger(os.path.join(self.tmp, "ledger.json"))
        svc = SyncService(lambda: client, ledger,
                          os.path.join(self.tmp, "bundles"),
                          topic_keywords=("选调",))
        result = svc.sync(session=None)
        self.assertEqual(result.success_count, 2)
        self.assertIsNone(ledger.get("off1"))  # 非主题文章未登记

    def test_no_keywords_disables_filter(self):
        details = {"n1": detail("n1"), "off1": detail("off1")}
        portal = FakePortal(pages={1: [{"noticeId": "n1", "title": "选调公告"},
                                       {"noticeId": "off1", "title": "普通通知"}]},
                            details=details)
        clock = FakeClock()
        config = PortalConfig(base_url="https://portal.invalid")
        client = PortalClient(config, portal, clock=clock, sleep=clock.sleep)
        ledger = ArticleLedger(os.path.join(self.tmp, "ledger.json"))
        svc = SyncService(lambda: client, ledger,
                          os.path.join(self.tmp, "bundles"))
        result = svc.sync(session=None)
        self.assertEqual(result.success_count, 2)


class TestMatchesTopic(unittest.TestCase):
    def test_keyword_in_title_or_content(self):
        from app.sync.collect_fixed import matches_topic
        self.assertTrue(matches_topic({"title": "选调生经验", "content": ""}, ("选调",)))
        self.assertTrue(matches_topic({"title": "分享", "content": "关于选调的体会"}, ("选调",)))
        self.assertFalse(matches_topic({"title": "运动会", "content": "报名"}, ("选调",)))
        self.assertTrue(matches_topic({"title": "任意", "content": ""}, ()))  # 空=不过滤
