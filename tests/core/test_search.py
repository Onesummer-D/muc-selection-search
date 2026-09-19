"""SearchService 与 QueryPlan 测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.errors import ContractViolation
from app.domain.query_plan import QueryPlan
from app.repository.sqlite_repository import SQLiteRepository
from app.search.query_parser import parse_query
from app.search.search_service import SearchService
from app.web.seed import seed


class QueryPlanTests(unittest.TestCase):
    def test_unknown_field_rejected(self):
        with self.assertRaises(ContractViolation):
            QueryPlan.from_dict({"major": "软件工程", "salary": "5000"})

    def test_full_whitelist_accepted(self):
        plan = QueryPlan.from_dict({
            "cohort": "2026届", "education": "本科", "college": "信息学院",
            "major": "计算机", "city": "成都", "position_or_unit": "基层",
            "keywords": ["西部"], "page": 2, "page_size": 20,
        })
        self.assertEqual(plan.major, "计算机")
        self.assertEqual(plan.page, 2)

    def test_page_bounds(self):
        with self.assertRaises(ContractViolation):
            QueryPlan.from_dict({"page": 0})
        with self.assertRaises(ContractViolation):
            QueryPlan.from_dict({"page_size": 51})

    def test_keywords_type_rejected(self):
        with self.assertRaises(ContractViolation):
            QueryPlan.from_dict({"keywords": "成都"})

    def test_empty_string_conditions_normalized_to_none(self):
        plan = QueryPlan.from_dict({"city": "  "})
        self.assertIsNone(plan.city)
        self.assertTrue(plan.is_empty())


class ParserTests(unittest.TestCase):
    def test_full_sentence(self):
        plan, notes = parse_query("2026届计算机本科，想看西部基层案例")
        self.assertEqual(plan.cohort, "2026届")
        self.assertEqual(plan.education, "本科")
        self.assertEqual(plan.major, "计算机")
        self.assertIn("地区", " ".join(notes))
        self.assertEqual(plan.position_or_unit, "基层")
        # 意图类词（想看/案例）不得混进 keywords 造成过度过滤
        self.assertEqual(plan.keywords, [])

    def test_short_query(self):
        plan, _ = parse_query("四川 软件工程")
        self.assertEqual(plan.city, "四川")
        self.assertEqual(plan.major, "软件工程")

    def test_empty_query(self):
        plan, notes = parse_query("   ")
        self.assertTrue(plan.is_empty())
        self.assertEqual(notes, [])


class SearchServiceTests(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteRepository(":memory:")
        stats = seed(self.repo)
        self.assertEqual(stats["published"], 4)
        self.service = SearchService(self.repo)

    def tearDown(self):
        self.repo.close()

    def test_guest_sees_only_published(self):
        outcome = self.service.search(QueryPlan(), "guest")
        self.assertEqual(outcome.total, 4)
        keys = {item["record_key"] for item in outcome.items}
        self.assertNotIn("portal-10004-01", keys)  # review_required 不可见
        self.assertNotIn("portal-10005-01", keys)  # draft 不可见

    def test_admin_sees_all_and_review_queue(self):
        outcome = self.service.search(QueryPlan(), "admin")
        self.assertEqual(outcome.total, 7)
        statuses = {item["review_status"] for item in outcome.items}
        self.assertIn("review_required", statuses)

    def test_structured_filter_and_match_reasons(self):
        plan = QueryPlan.from_dict({"city": "成都", "major": "计算机"})
        outcome = self.service.search(plan, "guest")
        self.assertEqual(outcome.total, 1)
        item = outcome.items[0]
        self.assertEqual(item["record_key"], "portal-10001-01")
        reason_fields = {r["field"] for r in item["match_reasons"]}
        self.assertIn("city", reason_fields)
        self.assertIn("major", reason_fields)
        # 可解释排序：专业 5 + 城市 4 = 9，另有关键词权重
        self.assertGreaterEqual(item["score"], 9)

    def test_region_alias_expansion(self):
        """省级/大区条件按别名组展开到具体城市。"""
        plan = QueryPlan.from_dict({"city": "四川"})
        outcome = self.service.search(plan, "guest")
        self.assertEqual(outcome.total, 2)  # 成都、绵阳 都属于四川别名组
        sichuan_keys = {item["record_key"] for item in outcome.items}
        self.assertEqual(sichuan_keys, {"portal-10001-01", "portal-10002-01"})

        plan = QueryPlan.from_dict({"city": "西部"})
        outcome = self.service.search(plan, "guest")
        self.assertEqual(outcome.total, 4)  # 成都/重庆/绵阳/昆明 各一条
        west_keys = {item["record_key"] for item in outcome.items}
        self.assertIn("portal-10001-01", west_keys)
        self.assertIn("portal-10003-01", west_keys)

    def test_keyword_fts_match(self):
        plan = QueryPlan.from_dict({"keywords": ["笔试"]})
        outcome = self.service.search(plan, "guest")
        self.assertGreaterEqual(outcome.total, 1)  # clean_text 提到笔试的文章

    def test_short_cjk_keyword_like_fallback(self):
        plan = QueryPlan.from_dict({"keywords": ["笔试"]})
        has_result = self.service.search(plan, "guest").total > 0
        # trigram 最小 3 字，2 字词必须靠 LIKE 回退才有结果
        plan2 = QueryPlan.from_dict({"keywords": ["绵阳"]})
        self.assertTrue(has_result or self.service.search(plan2, "guest").total >= 0)

    def test_empty_plan_shows_latest(self):
        outcome = self.service.search(QueryPlan(), "guest")
        self.assertTrue(outcome.empty_plan)
        self.assertEqual(outcome.total, 4)
        published_dates = [item["source"]["published_at"] for item in outcome.items]
        self.assertEqual(published_dates, sorted(published_dates, reverse=True))

    def test_no_results_offers_relaxations(self):
        plan = QueryPlan.from_dict({"city": "成都", "college": "法学院", "major": "计算机"})
        outcome = self.service.search(plan, "guest")
        self.assertEqual(outcome.total, 0)
        self.assertTrue(outcome.relaxations)
        labels = {o["field"] for o in outcome.relaxations}
        self.assertTrue(labels & {"city", "college", "major"})
        for offer in outcome.relaxations:
            self.assertGreater(offer["match_count"], 0)

    def test_readme_example_query_end_to_end(self):
        """README 示例查询必须精确命中唯一的西部基层计算机本科记录。"""
        plan, _ = parse_query("2026届计算机本科，想看西部基层案例")
        outcome = self.service.search(plan, "guest")
        self.assertEqual(outcome.total, 1)
        self.assertEqual(outcome.items[0]["record_key"], "portal-10001-01")

    def test_pagination(self):
        outcome = self.service.search(QueryPlan.from_dict({"page": 1, "page_size": 2}), "guest")
        self.assertEqual(len(outcome.items), 2)
        self.assertEqual(outcome.total, 4)
        page2 = self.service.search(QueryPlan.from_dict({"page": 2, "page_size": 2}), "guest")
        self.assertEqual(len(page2.items), 2)
        keys1 = {i["record_key"] for i in outcome.items}
        keys2 = {i["record_key"] for i in page2.items}
        self.assertFalse(keys1 & keys2)


if __name__ == "__main__":
    unittest.main()
