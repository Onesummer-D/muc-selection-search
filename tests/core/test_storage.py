"""任务1 存储契约测试。

覆盖任务书要求：
- 五张表建立，notice_id / record_key 唯一，一帖多人
- 故意重复导入一次，证明实体总行数不增加（只更新）
- null 字段、review_required、failed 状态与证据关系的持久化行为
- 非法 bundle（未知字段、缺必填键、坏枚举、越界数值等）被拒绝且零写入

运行：python -m unittest discover -s tests/core -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.errors import ContractViolation, MissingArticleError
from app.repository.importer import BundleImporter
from app.repository.sqlite_repository import SQLiteRepository

SHA_A = "A" * 64
SHA_B = "B" * 64


def article_bundle(**overrides):
    bundle = {
        "schema_version": "article_bundle.v1",
        "notice_id": "portal-90001",
        "title": "2026届选调经验分享",
        "source_url": "https://example.invalid/notice/90001",
        "published_at": "2026-09-10T08:00:00+08:00",
        "content_type": "poster",
        "clean_text": None,
        "asset_refs": [
            {
                "asset_id": "portal-90001-poster-01",
                "kind": "poster",
                "local_ref": "private://portal-90001/poster-01",
                "sha256": SHA_A,
            }
        ],
        "fetch_status": "processed",
        "failure_reason": None,
        "fetched_at": "2026-09-17T20:30:00+08:00",
    }
    bundle.update(overrides)
    return bundle


def record_full(record_key="portal-90001-01"):
    return {
        "record_key": record_key,
        "cohort": "2026届",
        "grade": None,
        "education": "本科",
        "college": "信息学院",
        "major": "计算机科学与技术",
        "city": "成都",
        "position_or_unit": "基层岗位",
        "review_status": "processed",
        "confidence": 0.92,
        "evidence": [
            {
                "field": "city",
                "text": "工作地点 成都",
                "method": "ocr_rule",
                "asset_id": "portal-90001-poster-01",
                "bbox": [102, 315, 386, 361],
            },
            {
                "field": "major",
                "text": "专业 计算机科学与技术",
                "method": "html_rule",
                "asset_id": None,
                "bbox": None,
            },
        ],
    }


def record_sparse(record_key="portal-90001-02"):
    return {
        "record_key": record_key,
        "cohort": None,
        "grade": None,
        "education": None,
        "college": "经济学院",
        "major": None,
        "city": None,
        "position_or_unit": None,
        "review_status": "review_required",
        "confidence": 0.41,
        "evidence": [
            {
                "field": "college",
                "text": "经济学院",
                "method": "ocr_rule",
                "asset_id": "portal-90001-poster-01",
                "bbox": [10, 20, 30, 40],
            }
        ],
    }


def extraction_bundle(records=None, **overrides):
    bundle = {
        "schema_version": "extraction_bundle.v1",
        "notice_id": "portal-90001",
        "extractor_version": "ocr-rule-0.1.0",
        "records": [record_full(), record_sparse()],
        "processing_status": "review_required",
        "failure_reason": None,
        "processed_at": "2026-09-18T18:00:00+08:00",
    }
    if records is not None:
        bundle["records"] = records
    bundle.update(overrides)
    return bundle


class StorageContractTests(unittest.TestCase):
    def setUp(self):
        self.repo = SQLiteRepository(":memory:")
        self.importer = BundleImporter(self.repo)

    def tearDown(self):
        self.repo.close()

    def _import_fixed_pair(self):
        self.importer.import_article_bundle(article_bundle())
        self.importer.import_extraction_bundle(extraction_bundle())

    # ---- 表结构与基础写入 ----

    def test_article_and_assets_persisted(self):
        result = self.importer.import_article_bundle(article_bundle())
        self.assertEqual((result.articles, result.assets, result.status), (1, 1, "processed"))
        article = self.repo.get_article("portal-90001")
        self.assertIsNotNone(article)
        self.assertEqual(article.title, "2026届选调经验分享")
        self.assertEqual(article.fetch_status, "processed")
        self.assertEqual(self.repo.count_articles(), 1)
        self.assertEqual(self.repo.count_assets(), 1)
        self.assertEqual(self.repo.count_records(), 0)
        self.assertEqual(self.repo.count_events(), 1)

    def test_multiple_records_per_notice(self):
        """一帖多人：一个 notice 对应两条人物记录，各自带证据。"""
        self._import_fixed_pair()
        self.assertEqual(self.repo.count_records(), 2)
        self.assertEqual(self.repo.count_evidence(), 3)
        keys = {r.record_key for r in self.repo.list_records_for_notice("portal-90001")}
        self.assertEqual(keys, {"portal-90001-01", "portal-90001-02"})
        for record in self.repo.list_records_for_notice("portal-90001"):
            self.assertEqual(record.notice_id, "portal-90001")

    # ---- 幂等导入：故意重复导入一次，证明总数不增加 ----

    def test_deliberate_duplicate_article_import_no_row_growth(self):
        self.importer.import_article_bundle(article_bundle())
        before = (self.repo.count_articles(), self.repo.count_assets())
        updated = article_bundle(
            title="2026届选调经验分享（更新）",
            fetch_status="review_required",
        )
        result = self.importer.import_article_bundle(updated)
        self.assertEqual(result.articles, 1)
        after = (self.repo.count_articles(), self.repo.count_assets())
        self.assertEqual(before, after)
        article = self.repo.get_article("portal-90001")
        self.assertEqual(article.title, "2026届选调经验分享（更新）")
        self.assertEqual(article.fetch_status, "review_required")
        # 事件是审计日志，每次导入追加一条，属于有意行为
        self.assertEqual(self.repo.count_events(), 2)

    def test_deliberate_duplicate_extraction_import_no_row_growth(self):
        self._import_fixed_pair()
        before = (self.repo.count_records(), self.repo.count_evidence())
        reimport = extraction_bundle()
        reimport["records"][0]["city"] = "绵阳"
        reimport["records"][0]["evidence"][0]["text"] = "工作地点 绵阳"
        result = self.importer.import_extraction_bundle(reimport)
        after = (self.repo.count_records(), self.repo.count_evidence())
        self.assertEqual(before, after)
        self.assertEqual((result.records, result.evidence), (2, 3))
        record = self.repo.get_record("portal-90001-01")
        self.assertEqual(record.city, "绵阳")
        evidence = self.repo.list_evidence_for_record("portal-90001-01")
        self.assertEqual(len(evidence), 2)  # 证据整组替换，不追加
        self.assertEqual(evidence[0].text, "工作地点 绵阳")

    # ---- null / review_required / failed ----

    def test_null_fields_stored_as_null(self):
        """字段缺失必须存 null，不得用空串或推测值代替。"""
        self._import_fixed_pair()
        record = self.repo.get_record("portal-90001-02")
        for field_name in ("cohort", "grade", "education", "major", "city", "position_or_unit"):
            self.assertIsNone(getattr(record, field_name), field_name)
        self.assertEqual(record.college, "经济学院")

    def test_review_required_record_is_draft_and_hidden_from_published(self):
        """处理状态与发布状态分离：导入只产生 draft，published 查询看不到。"""
        self._import_fixed_pair()
        record = self.repo.get_record("portal-90001-02")
        self.assertEqual(record.review_status, "review_required")
        self.assertEqual(record.visibility, "draft")
        self.assertEqual(self.repo.list_records(visibility="published"), [])
        self.assertEqual(len(self.repo.list_records(visibility="draft")), 2)

    def test_failed_article_bundle_stores_reason_and_event(self):
        bundle = article_bundle(fetch_status="failed", failure_reason="门户超时")
        self.importer.import_article_bundle(bundle)
        article = self.repo.get_article("portal-90001")
        self.assertEqual(article.fetch_status, "failed")
        self.assertEqual(article.failure_reason, "门户超时")
        events = self.repo.list_events("portal-90001")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].step, "import_article")
        self.assertEqual(events[0].status, "failed")
        self.assertEqual(events[0].failure_reason, "门户超时")

    def test_failed_extraction_bundle_records_event_without_records(self):
        bundle = extraction_bundle(
            records=[], processing_status="failed", failure_reason="OCR 服务不可用"
        )
        self.importer.import_article_bundle(article_bundle())
        result = self.importer.import_extraction_bundle(bundle)
        self.assertEqual((result.records, result.evidence, result.status), (0, 0, "failed"))
        self.assertEqual(self.repo.count_records(), 0)
        event = self.repo.list_events("portal-90001")[-1]
        self.assertEqual(event.step, "import_extraction")
        self.assertEqual(event.status, "failed")
        self.assertEqual(event.failure_reason, "OCR 服务不可用")

    # ---- 证据关系 ----

    def test_evidence_relations(self):
        self._import_fixed_pair()
        first = self.repo.list_evidence_for_record("portal-90001-01")
        self.assertEqual([e.field for e in first], ["city", "major"])
        self.assertEqual(first[0].method, "ocr_rule")
        self.assertEqual(first[0].asset_id, "portal-90001-poster-01")
        self.assertEqual(first[0].bbox, [102, 315, 386, 361])
        self.assertIsNone(first[1].asset_id)
        self.assertIsNone(first[1].bbox)
        second = self.repo.list_evidence_for_record("portal-90001-02")
        self.assertEqual([e.field for e in second], ["college"])
        # 证据必须关联到存在的记录
        for item in first + second:
            self.assertIsNotNone(self.repo.get_record(item.record_key))

    # ---- 边界：先有 extraction 后有 article 必须被拒绝 ----

    def test_extraction_before_article_rejected(self):
        bundle = extraction_bundle(notice_id="portal-99999")
        bundle["records"] = [record_full()]
        with self.assertRaises(MissingArticleError):
            self.importer.import_extraction_bundle(bundle)
        self.assertEqual(self.repo.count_records(), 0)
        self.assertEqual(self.repo.count_evidence(), 0)
        self.assertEqual(self.repo.count_events(), 0)  # 事务回滚，事件不留痕

    # ---- 契约校验：非法 bundle 一律拒绝且零写入 ----

    def test_invalid_bundles_rejected_without_writes(self):
        bad_record = record_full()
        bad_record.pop("grade")  # 键必须存在，值可以是 null
        dup_records = [record_full(), record_full()]
        cases = [
            ("article 未知字段", "article", article_bundle(unknown_field=1)),
            ("article 缺标题", "article", {k: v for k, v in article_bundle().items() if k != "title"}),
            ("article 非法 content_type", "article", article_bundle(content_type="video")),
            ("article failed 无原因", "article", article_bundle(fetch_status="failed", failure_reason=None)),
            ("article 非法 sha256", "article", article_bundle(
                asset_refs=[{"asset_id": "x", "kind": "poster",
                             "local_ref": "private://x", "sha256": "NOT-HEX"}])),
            ("article local_ref 非 private", "article", article_bundle(
                asset_refs=[{"asset_id": "x", "kind": "poster",
                             "local_ref": "https://example.invalid/x", "sha256": SHA_A}])),
            ("article fetched_at 非 ISO", "article", article_bundle(fetched_at="17/09/2026 20:30")),
            ("article source_url 非法", "article", article_bundle(source_url="not-a-url")),
            ("article asset_refs 非数组", "article", article_bundle(asset_refs={"asset_id": "x"})),
            ("extraction 版本号错误", "extraction", extraction_bundle(schema_version="extraction_bundle.v2")),
            ("extraction 非法 processing_status", "extraction",
             extraction_bundle(processing_status="done")),
            ("extraction 记录缺键", "extraction", extraction_bundle(records=[bad_record])),
            ("extraction 记录未知字段", "extraction", extraction_bundle(
                records=[{**record_full(), "salary": "5000"}])),
            ("extraction confidence 越界", "extraction", extraction_bundle(
                records=[{**record_full(), "confidence": 1.5}])),
            ("extraction confidence 是布尔", "extraction", extraction_bundle(
                records=[{**record_full(), "confidence": True}])),
            ("extraction 同 bundle 重复 record_key", "extraction",
             extraction_bundle(records=dup_records)),
            ("extraction 证据非法 field", "extraction", extraction_bundle(
                records=[{**record_full(), "evidence": [
                    {"field": "salary", "text": "x", "method": "manual",
                     "asset_id": None, "bbox": None}]}])),
            ("extraction bbox 只有 3 个数", "extraction", extraction_bundle(
                records=[{**record_full(), "evidence": [
                    {"field": "city", "text": "x", "method": "manual",
                     "asset_id": None, "bbox": [1, 2, 3]}]}])),
            ("extraction 非字符串字段值", "extraction", extraction_bundle(
                records=[{**record_full(), "city": 123}])),
        ]
        for name, kind, bundle in cases:
            with self.subTest(name):
                method = (self.importer.import_article_bundle if kind == "article"
                          else self.importer.import_extraction_bundle)
                with self.assertRaises(ContractViolation):
                    method(bundle)
        # 校验发生在写入之前：非法 bundle 不留下任何行
        self.assertEqual(self.repo.count_articles(), 0)
        self.assertEqual(self.repo.count_assets(), 0)
        self.assertEqual(self.repo.count_records(), 0)
        self.assertEqual(self.repo.count_evidence(), 0)
        self.assertEqual(self.repo.count_events(), 0)

    def test_valid_bundle_with_second_asset_updates_count(self):
        """资产随 bundle 增长：新 asset_id 入库，已有 asset_id 更新。"""
        self.importer.import_article_bundle(article_bundle())
        second_ref = {
            "asset_id": "portal-90001-poster-02",
            "kind": "image",
            "local_ref": "private://portal-90001/poster-02",
            "sha256": SHA_B,
        }
        bundle = article_bundle(asset_refs=[
            article_bundle()["asset_refs"][0], second_ref,
        ])
        self.importer.import_article_bundle(bundle)
        self.assertEqual(self.repo.count_articles(), 1)
        self.assertEqual(self.repo.count_assets(), 2)


if __name__ == "__main__":
    unittest.main()
