"""门户客户端测试：限速、重试、分页终止/重复页/空列表、详情缺字段、会话失效。"""
from __future__ import annotations

import unittest

from app.datasource.config import PortalConfig
from app.datasource.portal_client import (PortalClient, PortalHTTPError,
                                          SessionExpiredError)
from tests.datasource.fake_portal import FakeClock, FakePortal


def make_client(portal: FakePortal, clock: FakeClock, **cfg) -> PortalClient:
    config = PortalConfig(base_url="https://portal.invalid",
                          rate_min=0.8, rate_max=1.5, max_retries=3,
                          backoff_base=2.0, **cfg)
    return PortalClient(config, portal, clock=clock, sleep=clock.sleep)


class TestRateLimit(unittest.TestCase):
    def test_adjacent_start_gap_in_range(self):
        clock = FakeClock()
        portal = FakePortal(pages={1: [{"noticeId": f"n{i}"} for i in range(3)]})
        client = make_client(portal, clock)
        for _ in range(5):
            client.list_notices(1)
        starts = [r["start"] for r in client.request_log]
        gaps = [round(b - a, 6) for a, b in zip(starts, starts[1:])]
        for gap in gaps:
            self.assertGreaterEqual(gap, 0.8)
            self.assertLessEqual(gap, 1.5)

    def test_rate_min_must_not_exceed_max(self):
        from app.datasource.rate import RateLimiter
        with self.assertRaises(ValueError):
            RateLimiter(1.5, 0.8)


class TestRetry(unittest.TestCase):
    def test_429_retries_then_succeeds(self):
        clock = FakeClock()
        portal = FakePortal(
            script=[("status", 429), ("status", 429)],
            pages={1: [{"noticeId": "n1"}]},
        )
        client = make_client(portal, clock)
        items = client.list_notices(1)
        self.assertEqual(items[0]["notice_id"], "n1")
        # 初次 + 2 次重试
        self.assertEqual(client.request_log[-1]["attempts"], 3)

    def test_429_exhausts_after_four_attempts(self):
        clock = FakeClock()
        portal = FakePortal(script=[("status", 429)] * 4)
        client = make_client(portal, clock)
        with self.assertRaises(PortalHTTPError):
            client.list_notices(1)
        self.assertEqual(client.request_log[-1]["attempts"], 4)  # 总尝试上限 4

    def test_backoff_increases(self):
        from app.datasource.rate import RetryPolicy
        policy = RetryPolicy(max_retries=3, backoff_base=2.0)
        self.assertEqual([policy.backoff_seconds(n) for n in (1, 2, 3)],
                         [2.0, 4.0, 8.0])

    def test_404_not_retried(self):
        clock = FakeClock()
        portal = FakePortal(script=[("status", 404)])
        client = make_client(portal, clock)
        with self.assertRaises(PortalHTTPError):
            client.list_notices(1)
        # 不可重试：只尝试 1 次
        self.assertEqual(client.request_log[-1]["attempts"], 1)

    def test_timeout_retried(self):
        clock = FakeClock()
        portal = FakePortal(script=[("timeout",)])
        client = make_client(portal, clock)
        portal.pages = {1: [{"noticeId": "n1"}]}
        with self.assertRaises(TimeoutError):
            client.list_notices(1)


class TestPagination(unittest.TestCase):
    def test_multi_page_and_termination(self):
        clock = FakeClock()
        portal = FakePortal(pages={
            1: [{"noticeId": f"a{i}"} for i in range(20)],
            2: [{"noticeId": f"b{i}"} for i in range(20)],
            3: [{"noticeId": "c0"}, {"noticeId": "c1"}],  # 不足 page_size → 终止
        })
        client = make_client(portal, clock, page_size=20)
        ids = [i["notice_id"] for i in client.iterate_notices()]
        self.assertEqual(len(ids), 42)
        self.assertEqual(len(set(ids)), 42)

    def test_empty_list_terminates(self):
        clock = FakeClock()
        portal = FakePortal(pages={})
        client = make_client(portal, clock)
        self.assertEqual(list(client.iterate_notices()), [])

    def test_duplicate_page_deduped(self):
        # 门户固定返回最后一页（重复页）：总数不变
        same_page = [{"noticeId": f"x{i}"} for i in range(20)]
        clock = FakeClock()
        portal = FakePortal(pages={1: same_page, 2: same_page})
        client = make_client(portal, clock, page_size=20)
        ids = [i["notice_id"] for i in client.iterate_notices()]
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20)

    def test_missing_notice_id_raises(self):
        clock = FakeClock()
        portal = FakePortal(pages={1: [{"title": "no id"}]})
        client = make_client(portal, clock)
        with self.assertRaises(Exception):
            client.list_notices(1)


class TestDetail(unittest.TestCase):
    def test_detail_missing_content_fields(self):
        clock = FakeClock()
        portal = FakePortal(details={"n1": {"noticeId": "n1", "title": "t"}})
        client = make_client(portal, clock)
        detail = client.get_notice("n1")
        self.assertIsNone(detail["content"])
        self.assertEqual(detail["images"], [])

    def test_detail_404(self):
        clock = FakeClock()
        portal = FakePortal(details={})
        client = make_client(portal, clock)
        with self.assertRaises(PortalHTTPError):
            client.get_notice("missing")


class TestSession(unittest.TestCase):
    def test_session_expired_on_401(self):
        clock = FakeClock()
        portal = FakePortal(script=[("status", 401)])
        client = make_client(portal, clock)
        with self.assertRaises(SessionExpiredError):
            client.validate_session()

    def test_session_check_ok(self):
        clock = FakeClock()
        portal = FakePortal(pages={1: [{"noticeId": "n1"}]})
        client = make_client(portal, clock)
        self.assertTrue(client.validate_session())


if __name__ == "__main__":
    unittest.main()
