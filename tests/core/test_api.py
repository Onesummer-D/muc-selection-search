"""Flask API 集成测试：五个接口 + healthz + 开发角色开关。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.repository.sqlite_repository import SQLiteRepository
from app.search.llm_provider import NullProvider
from app.web.app import create_app
from app.web.seed import seed
from app.domain import role_policy


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteRepository(":memory:")
        seed(self.repo)
        # 注入 NullProvider 隔离本机 .env：API 集成测试不依赖机器密钥配置
        self.app = create_app(repository=self.repo, llm_provider=NullProvider())
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.repo.close()
        os.environ.pop(role_policy.DEV_ROLE_SWITCH_ENABLED, None)

    # ---- GET /api/search ----

    def test_search_ok(self):
        resp = self.client.get("/api/search?major=计算机")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["role"], "guest")
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["fields"]["major"], "计算机科学与技术")
        self.assertTrue(data["results"][0]["match_reasons"])

    def test_search_unknown_param_rejected(self):
        resp = self.client.get("/api/search?salary=5000")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("salary", resp.get_json()["detail"])

    def test_search_bad_page_rejected(self):
        resp = self.client.get("/api/search?page=abc")
        self.assertEqual(resp.status_code, 400)

    def test_search_empty_shows_latest(self):
        resp = self.client.get("/api/search")
        data = resp.get_json()
        self.assertTrue(data["empty_plan"])
        self.assertEqual(data["total"], 4)

    def test_search_relaxations_offered(self):
        resp = self.client.get("/api/search?city=成都&college=法学院&major=计算机")
        data = resp.get_json()
        self.assertEqual(data["total"], 0)
        self.assertTrue(data["relaxations"])

    # ---- POST /api/query/parse ----

    def test_parse_ok(self):
        resp = self.client.post("/api/query/parse", json={"query": "2026届计算机本科"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["query_plan"]["education"], "本科")
        self.assertEqual(data["source"], "rule")

    def test_parse_unknown_body_field_rejected(self):
        resp = self.client.post("/api/query/parse", json={"query": "x", "sql": "drop table"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("sql", resp.get_json()["detail"])

    def test_parse_missing_query_rejected(self):
        resp = self.client.post("/api/query/parse", json={})
        self.assertEqual(resp.status_code, 400)

    def test_parse_non_json_rejected(self):
        resp = self.client.post("/api/query/parse", data="plain",
                                content_type="text/plain")
        self.assertEqual(resp.status_code, 400)

    # ---- POST /api/query/answer ----

    def test_answer_with_evidence(self):
        resp = self.client.post("/api/query/answer", json={"query": "成都 计算机本科"})
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["insufficient_evidence"])
        self.assertTrue(data["citations"])
        self.assertIn("[1]", data["answer"])
        self.assertEqual(data["citations"][0]["record_key"], "portal-10001-01")
        # 第一周 LLM 未配置 → degraded 明确标注，但传统结果仍然返回
        self.assertTrue(data["degraded"])
        self.assertIn("规则模板", data["degraded_reason"])
        self.assertTrue(data["records"])

    def test_answer_insufficient_evidence(self):
        resp = self.client.post("/api/query/answer", json={"query": "博士 乌鲁木齐"})
        data = resp.get_json()
        self.assertTrue(data["insufficient_evidence"])
        self.assertIn("证据不足", data["answer"])

    # ---- GET /api/records/{record_key} ----

    def test_detail_guest_desensitized(self):
        resp = self.client.get("/api/records/portal-10001-01")
        self.assertEqual(resp.status_code, 200)
        dto = resp.get_json()
        self.assertEqual(dto["fields"]["city"], "成都")
        self.assertNotIn("person", dto)
        self.assertNotIn("url", dto["source"])
        self.assertTrue(dto["evidence"])

    def test_detail_unknown_record_404(self):
        resp = self.client.get("/api/records/no-such-key")
        self.assertEqual(resp.status_code, 404)

    def test_detail_draft_hidden_from_guest_but_admin_ok(self):
        resp_guest = self.client.get("/api/records/portal-10005-01")
        self.assertEqual(resp_guest.status_code, 404)  # 越权/未发布 → 4xx，不暴露存在性

        os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "true"
        self.client.post("/api/dev/role", json={"role": "admin"})
        resp_admin = self.client.get("/api/records/portal-10005-01")
        self.assertEqual(resp_admin.status_code, 200)
        self.assertEqual(resp_admin.get_json()["visibility"], "draft")

    # ---- GET /api/auth/me ----

    def test_auth_me_guest_default(self):
        resp = self.client.get("/api/auth/me")
        data = resp.get_json()
        self.assertEqual(data["role"], "guest")
        self.assertFalse(data["authenticated"])
        self.assertIn("search", data["capabilities"])

    # ---- 开发角色开关 ----

    def test_dev_role_switch_disabled_returns_404(self):
        os.environ.pop(role_policy.DEV_ROLE_SWITCH_ENABLED, None)
        resp = self.client.post("/api/dev/role", json={"role": "student"})
        self.assertEqual(resp.status_code, 404)

    def test_dev_role_switch_enabled_allows_switch(self):
        os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "true"
        resp = self.client.post("/api/dev/role", json={"role": "student"})
        self.assertEqual(resp.status_code, 200)
        me = self.client.get("/api/auth/me").get_json()
        self.assertEqual(me["role"], "student")
        self.assertTrue(me["authenticated"])
        reset = self.client.delete("/api/dev/role")
        self.assertEqual(reset.get_json()["role"], "guest")

    def test_dev_role_invalid_value_rejected(self):
        os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "true"
        resp = self.client.post("/api/dev/role", json={"role": "superadmin"})
        self.assertEqual(resp.status_code, 400)

    # ---- GET /healthz ----

    def test_healthz_ok(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["components"]["database"], "ok")
        self.assertEqual(data["components"]["embedding"], "disabled_by_decision")


if __name__ == "__main__":
    unittest.main()
