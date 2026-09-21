from __future__ import annotations

import os
import unittest

from app.domain import role_policy
from app.repository.sqlite_repository import SQLiteRepository
from app.search.llm_provider import NullProvider
from app.web.app import create_app
from app.web.seed import seed


class Week2ProfileApiTests(unittest.TestCase):
    def setUp(self):
        os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "true"
        self.repo = SQLiteRepository(":memory:")
        seed(self.repo)
        self.app = create_app(repository=self.repo, llm_provider=NullProvider())
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.post("/api/dev/role", json={"role": "student"})

    def tearDown(self):
        self.repo.close()
        os.environ.pop(role_policy.DEV_ROLE_SWITCH_ENABLED, None)

    def test_saved_search_is_query_plan_only_and_isolated(self):
        headers = {"X-Demo-User": "alice"}
        response = self.client.post("/api/saved-searches", headers=headers, json={"query_plan": {"major": "计算机", "keywords": ["成都"]}, "alert_frequency": "weekly", "query": "不要保存"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/saved-searches", headers=headers, json={"query_plan": {"major": "计算机", "keywords": ["成都"]}})
        self.assertEqual(response.status_code, 201)
        saved_id = response.get_json()["saved_search_id"]
        self.assertNotIn("query", response.get_json())
        other = self.client.get("/api/saved-searches", headers={"X-Demo-User": "bob"})
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.get_json()["items"], [])
        self.assertEqual(self.client.patch(f"/api/saved-searches/{saved_id}/alert", headers=headers, json={"alert_frequency": "daily"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/saved-searches/{saved_id}", headers=headers).status_code, 200)

    def test_privacy_default_and_incognito(self):
        headers = {"X-Demo-User": "alice"}
        self.assertFalse(self.client.get("/api/me/privacy", headers=headers).get_json()["history_enabled"])
        self.client.patch("/api/me/privacy", headers=headers, json={"history_enabled": True, "recommendation_enabled": True})
        self.client.get("/api/search?major=计算机", headers=headers)
        before = self.repo.insight_summary("alice")["history_count"]
        self.client.get("/api/search?major=计算机", headers={**headers, "X-Incognito-Mode": "1"})
        self.assertEqual(self.repo.insight_summary("alice")["history_count"], before)
        self.assertEqual(self.client.delete("/api/me/history", headers=headers).status_code, 200)
        self.assertEqual(self.repo.insight_summary("alice")["history_count"], 0)

    def test_guest_cannot_access_personal_data(self):
        self.client.delete("/api/dev/role")
        self.assertEqual(self.client.get("/api/saved-searches").status_code, 401)
        self.assertEqual(self.client.get("/api/me/privacy").status_code, 401)

    def test_sync_contract_is_admin_only_and_conditional(self):
        self.client.post("/api/dev/role", json={"role": "admin"})
        self.assertEqual(self.client.get("/api/admin/sync/status").status_code, 200)
        self.assertEqual(self.client.post("/api/admin/sync").status_code, 503)
        self.client.delete("/api/dev/role")
        self.assertEqual(self.client.get("/api/admin/sync/status").status_code, 403)

    def test_published_record_emits_one_deduplicated_notification(self):
        alice = {"X-Demo-User": "alice"}
        self.client.post("/api/saved-searches", headers=alice, json={"query_plan": {"major": "计算机"}})
        self.client.post("/api/dev/role", json={"role": "admin"})
        self.assertEqual(self.client.post("/api/admin/records/portal-10005-01/publish").status_code, 200)
        self.assertEqual(self.repo.list_notifications("alice").__len__(), 1)
        self.client.post("/api/admin/records/portal-10005-01/publish")
        self.assertEqual(self.repo.list_notifications("alice").__len__(), 1)


if __name__ == "__main__":
    unittest.main()
