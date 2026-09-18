"""RolePolicy / RecordPresenter 权限测试：guest 受限字段必须为 0。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.presenter import RecordPresenter, assert_no_restricted_fields
from app.domain import role_policy
from app.repository.sqlite_repository import SQLiteRepository
from app.web.seed import seed


class PresenterPermissionTests(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteRepository(":memory:")
        seed(self.repo)
        self.presenter = RecordPresenter()

    def tearDown(self):
        self.repo.close()
        for var in (role_policy.DEV_ROLE_SWITCH_ENABLED,
                    role_policy.CAMPUS_ORIGINAL_ASSET_ENABLED):
            os.environ.pop(var, None)

    def _full_dto(self, role):
        record = self.repo.get_record("portal-10001-01")
        article = self.repo.get_article(record.notice_id)
        evidence = self.repo.list_evidence_for_record(record.record_key)
        return self.presenter.present_full(record, article, evidence, role)

    def test_guest_dto_has_zero_restricted_fields(self):
        """Guest Visibility Matrix：受限字段必须为 0（键不存在，不是 null）。"""
        dto = self._full_dto("guest")
        assert_no_restricted_fields(dto, "guest")
        self.assertNotIn("person", dto)
        self.assertNotIn("url", dto.get("source", {"url": 1}))
        self.assertNotIn("asset_id", dto["evidence"][0])
        self.assertFalse(dto["poster"]["full_access"])

    def test_guest_sees_business_fields_and_evidence(self):
        dto = self._full_dto("guest")
        self.assertEqual(dto["fields"]["major"], "计算机科学与技术")
        self.assertEqual(dto["fields"]["city"], "成都")
        self.assertTrue(dto["evidence"])  # 脱敏证据文本可见

    def test_student_dto_default_no_full_poster(self):
        dto = self._full_dto("student")
        assert_no_restricted_fields(dto, "student")
        self.assertIn("url", dto["source"])  # 校内可见来源 SSO 链接
        self.assertIn("asset_id", dto["evidence"][0])
        self.assertFalse(dto["poster"]["full_access"])  # 完整海报默认关闭

    def test_student_full_poster_requires_campus_flag(self):
        os.environ[role_policy.CAMPUS_ORIGINAL_ASSET_ENABLED] = "true"
        try:
            dto = self._full_dto("student")
            self.assertTrue(dto["poster"]["full_access"])
        finally:
            os.environ.pop(role_policy.CAMPUS_ORIGINAL_ASSET_ENABLED, None)

    def test_admin_dto_full_and_queue(self):
        dto = self._full_dto("admin")
        self.assertIn("person", dto)
        self.assertTrue(dto["poster"]["full_access"])
        self.assertIn("extractor_version", dto)

    def test_review_required_records_only_admin_visible(self):
        published = self.repo.list_records("published")
        self.assertTrue(all(r.review_status != "review_required" for r in published))
        all_records = self.repo.list_records()
        self.assertTrue(any(r.review_status == "review_required" for r in all_records))


class RolePolicyTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(role_policy.DEV_ROLE_SWITCH_ENABLED, None)

    def test_dev_switch_default_off(self):
        self.assertFalse(role_policy.dev_role_switch_enabled())

    def test_dev_switch_env_on(self):
        os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "true"
        self.assertTrue(role_policy.dev_role_switch_enabled())
        os.environ[role_policy.DEV_ROLE_SWITCH_ENABLED] = "false"
        self.assertFalse(role_policy.dev_role_switch_enabled())

    def test_normalize_role_fallback_guest(self):
        self.assertEqual(role_policy.normalize_role(None), "guest")
        self.assertEqual(role_policy.normalize_role("hacker"), "guest")
        self.assertEqual(role_policy.normalize_role("teacher"), "teacher")

    def test_published_only_roles(self):
        for role in ("guest", "student", "teacher"):
            self.assertTrue(role_policy.published_only(role))
        self.assertFalse(role_policy.published_only("admin"))

    def test_capabilities_grow_with_role(self):
        guest_caps = role_policy.role_capabilities("guest")
        admin_caps = role_policy.role_capabilities("admin")
        self.assertIn("search", guest_caps)
        self.assertNotIn("review_queue", guest_caps)
        self.assertIn("review_queue", admin_caps)


if __name__ == "__main__":
    unittest.main()
