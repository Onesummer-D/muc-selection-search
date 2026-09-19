"""bundle 导入编排：契约校验 → 事务内幂等写入 → 记录 processing_event。

幂等语义（任务1）：
- 重复导入同一 article bundle：articles / assets 按 notice_id / asset_id 更新，不增行。
- 重复导入同一 extraction bundle：experience_records 按 record_key 更新；
  evidence 按 record_key 整组替换，不追加；总行数不变。
- 导入不写入 visibility（保持人工发布状态）与七个私有字段。
- processing_events 是审计日志，每次导入追加一条，这是有意行为。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..domain.models import Article, Asset, Evidence, ExperienceRecord, ProcessingEvent
from ..domain.validation import validate_article_bundle, validate_extraction_bundle
from .base import Repository


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class ImportResult:
    """一次导入的结果摘要，用于日志与测试断言。"""

    notice_id: str
    step: str
    status: str
    articles: int = 0
    assets: int = 0
    records: int = 0
    evidence: int = 0


class BundleImporter:
    """把 article_bundle.v1 / extraction_bundle.v1 导入仓储。"""

    def __init__(self, repository: Repository) -> None:
        self._repo = repository

    def import_article_bundle(self, bundle: dict) -> ImportResult:
        validate_article_bundle(bundle)
        article = Article.from_bundle(bundle)
        assets = [Asset.from_bundle(article.notice_id, ref) for ref in bundle["asset_refs"]]
        occurred_at = _now()
        with self._repo.transaction():
            # 先文章后素材：assets.notice_id 有外键依赖
            self._repo.upsert_article(article)
            for asset in assets:
                self._repo.upsert_asset(asset)
            self._repo.record_event(ProcessingEvent(
                notice_id=article.notice_id,
                step="import_article",
                status=article.fetch_status,
                occurred_at=occurred_at,
                failure_reason=article.failure_reason,
            ))
        return ImportResult(
            notice_id=article.notice_id,
            step="import_article",
            status=article.fetch_status,
            articles=1,
            assets=len(assets),
        )

    def import_extraction_bundle(self, bundle: dict) -> ImportResult:
        validate_extraction_bundle(bundle)
        notice_id = bundle["notice_id"]
        extractor_version = bundle["extractor_version"]
        occurred_at = _now()
        evidence_count = 0
        with self._repo.transaction():
            for raw_record in bundle["records"]:
                record = ExperienceRecord.from_bundle(notice_id, extractor_version, raw_record)
                self._repo.upsert_record(record)
                items = [Evidence.from_bundle(record.record_key, ev)
                         for ev in raw_record["evidence"]]
                self._repo.replace_evidence(record.record_key, items)
                evidence_count += len(items)
            self._repo.record_event(ProcessingEvent(
                notice_id=notice_id,
                step="import_extraction",
                status=bundle["processing_status"],
                occurred_at=occurred_at,
                failure_reason=bundle.get("failure_reason"),
            ))
        return ImportResult(
            notice_id=notice_id,
            step="import_extraction",
            status=bundle["processing_status"],
            records=len(bundle["records"]),
            evidence=evidence_count,
        )
