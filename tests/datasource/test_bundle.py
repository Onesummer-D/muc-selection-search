"""article_bundle.v1 构造、脱敏与 Schema 校验测试。"""
from __future__ import annotations

import json
import jsonschema  # 测试依赖，登记 PR 说明
import os
import unittest

from app.sync.bundle import (build_article_bundle, content_type_for,
                             sanitize_text, validate_bundle, write_bundle,
                             asset_refs_for)

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "schemas", "article_bundle.v1.schema.json")


def valid_bundle(**overrides) -> dict:
    base = {
        "schema_version": "article_bundle.v1",
        "notice_id": "portal-12345",
        "title": "某届选调经验分享",
        "source_url": "https://example.invalid/notice/12345",
        "published_at": "2026-09-10T08:00:00+08:00",
        "content_type": "text",
        "clean_text": "正文",
        "asset_refs": [],
        "fetch_status": "processed",
        "failure_reason": None,
        "fetched_at": "2026-09-17T20:30:00+08:00",
    }
    base.update(overrides)
    return base


class TestSchemaValidation(unittest.TestCase):
    def test_valid_bundle_passes(self):
        with open(SCHEMA, encoding="utf-8") as fh:
            schema = json.load(fh)
        jsonschema.validate(valid_bundle(), schema)

    def test_required_fields(self):
        for field in ("notice_id", "title", "source_url", "content_type",
                      "fetch_status", "fetched_at"):
            bundle = valid_bundle()
            del bundle[field]
            with self.assertRaises(jsonschema.ValidationError):
                validate_bundle(bundle)

    def test_failed_requires_reason(self):
        validate_bundle(valid_bundle(fetch_status="failed",
                                     failure_reason="HTTP 500"))
        with self.assertRaises(Exception):
            validate_bundle(valid_bundle(fetch_status="failed",
                                         failure_reason=None))

    def test_success_must_not_keep_reason(self):
        with self.assertRaises(ValueError):
            validate_bundle(valid_bundle(fetch_status="processed",
                                         failure_reason="残留原因"))

    def test_private_ref_pattern(self):
        refs = [{"asset_id": "a1", "kind": "poster",
                 "local_ref": "/etc/passwd", "sha256": "0" * 64}]
        with self.assertRaises(jsonschema.ValidationError):
            validate_bundle(valid_bundle(asset_refs=refs))


class TestSanitize(unittest.TestCase):
    def test_phone_masked(self):
        self.assertNotIn("13812345678",
                         sanitize_text("联系 13812345678 谢谢"))

    def test_email_masked(self):
        self.assertNotIn("a@b.com", sanitize_text("邮箱 a@b.com"))

    def test_id_card_masked(self):
        self.assertNotIn("110101199001011234",
                         sanitize_text("身份证 110101199001011234"))

    def test_normal_text_unchanged(self):
        text = "四川选调，基层岗位，2026届计算机本科。"
        self.assertEqual(sanitize_text(text), text)

    def test_none_stays_none(self):
        self.assertIsNone(sanitize_text(None))


class TestContentType(unittest.TestCase):
    def test_text(self):
        self.assertEqual(content_type_for({"content": "abc", "images": []}), "text")

    def test_poster(self):
        self.assertEqual(content_type_for({"content": "", "images": ["x"]}), "poster")

    def test_mixed(self):
        self.assertEqual(content_type_for({"content": "a", "images": ["x"]}), "mixed")

    def test_unknown(self):
        self.assertEqual(content_type_for({"content": "", "images": []}), "unknown")


class TestAssetRefs(unittest.TestCase):
    def test_poster_refs(self):
        detail = {"notice_id": "p1", "images": [{"sha256": "A" * 64}]}
        refs = asset_refs_for(detail)
        self.assertEqual(refs[0]["local_ref"], "private://p1/poster-01")
        self.assertEqual(refs[0]["sha256"], "A" * 64)
        self.assertTrue(refs[0]["asset_id"])


class TestWriteBundle(unittest.TestCase):
    def test_write_and_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_article_bundle(
                notice_id="n1", title="t", source_url="https://x.invalid/1",
                content_type="text", published_at=None, clean_text="正文",
                asset_refs=[], fetch_status="processed", failure_reason=None,
                fetched_at="2026-09-17T23:00:00+08:00")
            path = write_bundle(bundle, tmp)
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            self.assertEqual(loaded["notice_id"], "n1")


if __name__ == "__main__":
    unittest.main()
