"""SQLite 仓储实现：五张表、幂等 upsert 与查询。

表结构对应接口字典第 5 节（v1.0，2026-09-18 附录 G 更新）：
- articles            notice_id 唯一
- assets              asset_id 唯一，关联 articles
- experience_records  record_key 唯一，关联 articles，一帖多人
- evidence            自增主键，关联 record_key 与字段名
- processing_events   自增主键，保存步骤、状态、时间和失败原因

连接使用 autocommit（isolation_level=None），多语句操作必须由调用方
包在 transaction() 中，保证导入的原子性与回滚。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from ..domain.errors import MissingArticleError, StorageIntegrityError
from ..domain.models import (
    Article,
    Asset,
    Evidence,
    ExperienceRecord,
    ProcessingEvent,
)
from .base import Repository

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
  notice_id      TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  title          TEXT NOT NULL,
  source_url     TEXT NOT NULL,
  published_at   TEXT,
  content_type   TEXT NOT NULL CHECK (content_type IN ('text','poster','mixed','unknown')),
  clean_text     TEXT,
  fetch_status   TEXT NOT NULL CHECK (fetch_status IN ('pending','processed','review_required','failed')),
  failure_reason TEXT,
  fetched_at     TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
  asset_id          TEXT PRIMARY KEY,
  notice_id         TEXT NOT NULL REFERENCES articles(notice_id),
  kind              TEXT NOT NULL CHECK (kind IN ('poster','image','attachment')),
  local_ref         TEXT NOT NULL CHECK (local_ref LIKE 'private://%'),
  sha256            TEXT NOT NULL CHECK (length(sha256) = 64),
  derived_guest_ref TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experience_records (
  record_key        TEXT PRIMARY KEY,
  notice_id         TEXT NOT NULL REFERENCES articles(notice_id),
  extractor_version TEXT NOT NULL,
  cohort            TEXT,
  grade             TEXT,
  education         TEXT,
  college           TEXT,
  major             TEXT,
  city              TEXT,
  position_or_unit  TEXT,
  review_status     TEXT NOT NULL CHECK (review_status IN ('pending','processed','review_required','failed')),
  confidence        REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  visibility        TEXT NOT NULL DEFAULT 'draft' CHECK (visibility IN ('draft','published','withdrawn')),
  person_name       TEXT,
  avatar_ref        TEXT,
  qr_code_ref       TEXT,
  contact_info      TEXT,
  meeting_entry     TEXT,
  original_asset_ref TEXT,
  source_sso_url    TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
  record_key  TEXT NOT NULL REFERENCES experience_records(record_key),
  field       TEXT NOT NULL CHECK (field IN ('cohort','grade','education','college','major','city','position_or_unit')),
  text        TEXT NOT NULL,
  method      TEXT NOT NULL CHECK (method IN ('html_rule','ocr_rule','multimodal','manual')),
  asset_id    TEXT,
  bbox        TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_events (
  event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  notice_id      TEXT,
  step           TEXT NOT NULL,
  status         TEXT NOT NULL CHECK (status IN ('pending','running','processed','review_required','failed')),
  failure_reason TEXT,
  occurred_at    TEXT NOT NULL,
  created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_notice ON experience_records(notice_id);
CREATE INDEX IF NOT EXISTS idx_evidence_record ON evidence(record_key);
CREATE INDEX IF NOT EXISTS idx_events_notice ON processing_events(notice_id);

-- 文章全文索引：外部内容表 + trigram 分词（任务0已验证本机支持）
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title, clean_text, content='articles', content_rowid='rowid', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, clean_text)
  VALUES (new.rowid, new.title, new.clean_text);
END;
CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, clean_text)
  VALUES ('delete', old.rowid, old.title, old.clean_text);
END;
CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, clean_text)
  VALUES ('delete', old.rowid, old.title, old.clean_text);
  INSERT INTO articles_fts(rowid, title, clean_text)
  VALUES (new.rowid, new.title, new.clean_text);
END;
"""

_UPSERT_ARTICLE = """
INSERT INTO articles (
  notice_id, schema_version, title, source_url, published_at, content_type,
  clean_text, fetch_status, failure_reason, fetched_at, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(notice_id) DO UPDATE SET
  schema_version = excluded.schema_version,
  title = excluded.title,
  source_url = excluded.source_url,
  published_at = excluded.published_at,
  content_type = excluded.content_type,
  clean_text = excluded.clean_text,
  fetch_status = excluded.fetch_status,
  failure_reason = excluded.failure_reason,
  fetched_at = excluded.fetched_at,
  updated_at = excluded.updated_at
"""

_UPSERT_ASSET = """
INSERT INTO assets (
  asset_id, notice_id, kind, local_ref, sha256, derived_guest_ref, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(asset_id) DO UPDATE SET
  notice_id = excluded.notice_id,
  kind = excluded.kind,
  local_ref = excluded.local_ref,
  sha256 = excluded.sha256,
  updated_at = excluded.updated_at
"""

_UPSERT_RECORD = """
INSERT INTO experience_records (
  record_key, notice_id, extractor_version, cohort, grade, education, college, major,
  city, position_or_unit, review_status, confidence, visibility,
  person_name, avatar_ref, qr_code_ref, contact_info, meeting_entry,
  original_asset_ref, source_sso_url, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(record_key) DO UPDATE SET
  extractor_version = excluded.extractor_version,
  cohort = excluded.cohort,
  grade = excluded.grade,
  education = excluded.education,
  college = excluded.college,
  major = excluded.major,
  city = excluded.city,
  position_or_unit = excluded.position_or_unit,
  review_status = excluded.review_status,
  confidence = excluded.confidence,
  updated_at = excluded.updated_at
"""

_INSERT_EVIDENCE = """
INSERT INTO evidence (record_key, field, text, method, asset_id, bbox, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_EVENT = """
INSERT INTO processing_events (notice_id, step, status, failure_reason, occurred_at, created_at)
VALUES (?, ?, ?, ?, ?, ?)
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class SQLiteRepository(Repository):
    """SQLite 实现；file 路径或 ':memory:'。"""

    def __init__(self, path: str = ":memory:") -> None:
        # Flask 在请求线程中访问连接，check_same_thread=False + 全局锁串行化
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def close(self) -> None:
        self._conn.close()

    # ---- 基础设施 ----

    def init_schema(self) -> None:
        self._conn.executescript(SCHEMA_SQL)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _execute(self, sql: str, params: tuple) -> None:
        """执行写入语句，并把完整性错误翻译成领域异常。"""
        with self._lock:
            try:
                self._conn.execute(sql, params)
            except sqlite3.IntegrityError as exc:
                message = str(exc)
                if "FOREIGN KEY" in message:
                    raise MissingArticleError(
                        f"外键约束失败：引用的 notice_id 尚未导入，请先导入对应 article bundle（{message}）"
                    ) from exc
                raise StorageIntegrityError(f"完整性约束失败：{message}") from exc

    # ---- 写入 ----

    def upsert_article(self, article: Article) -> None:
        now = _now()
        self._execute(
            _UPSERT_ARTICLE,
            (
                article.notice_id, article.schema_version, article.title,
                article.source_url, article.published_at, article.content_type,
                article.clean_text, article.fetch_status, article.failure_reason,
                article.fetched_at, now, now,
            ),
        )

    def upsert_asset(self, asset: Asset) -> None:
        now = _now()
        self._execute(
            _UPSERT_ASSET,
            (asset.asset_id, asset.notice_id, asset.kind, asset.local_ref,
             asset.sha256, asset.derived_guest_ref, now, now),
        )

    def upsert_record(self, record: ExperienceRecord) -> None:
        now = _now()
        self._execute(
            _UPSERT_RECORD,
            (
                record.record_key, record.notice_id, record.extractor_version,
                record.cohort, record.grade, record.education, record.college,
                record.major, record.city, record.position_or_unit,
                record.review_status, record.confidence, record.visibility,
                record.person_name, record.avatar_ref, record.qr_code_ref,
                record.contact_info, record.meeting_entry,
                record.original_asset_ref, record.source_sso_url, now, now,
            ),
        )

    def replace_evidence(self, record_key: str, items: list[Evidence]) -> None:
        now = _now()
        self._conn.execute("DELETE FROM evidence WHERE record_key = ?", (record_key,))
        for item in items:
            self._execute(
                _INSERT_EVIDENCE,
                (
                    item.record_key, item.field, item.text, item.method,
                    item.asset_id,
                    json.dumps(item.bbox) if item.bbox is not None else None,
                    now, now,
                ),
            )

    def record_event(self, event: ProcessingEvent) -> None:
        self._execute(
            _INSERT_EVENT,
            (event.notice_id, event.step, event.status,
             event.failure_reason, event.occurred_at, _now()),
        )

    def set_visibility(self, record_key: str, visibility: str) -> None:
        if visibility not in ("draft", "published", "withdrawn"):
            raise StorageIntegrityError(f"非法的发布状态：{visibility!r}")
        self._execute(
            "UPDATE experience_records SET visibility = ?, updated_at = ? WHERE record_key = ?",
            (visibility, _now(), record_key),
        )

    # ---- 查询 ----

    def _query_one(self, sql: str, params: tuple) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _query_all(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def get_article(self, notice_id: str) -> Article | None:
        row = self._query_one("SELECT * FROM articles WHERE notice_id = ?", (notice_id,))
        return _article_from_row(row) if row else None

    def get_record(self, record_key: str) -> ExperienceRecord | None:
        row = self._query_one(
            "SELECT * FROM experience_records WHERE record_key = ?", (record_key,)
        )
        return _record_from_row(row) if row else None

    def list_records(self, visibility: str | None = None) -> list[ExperienceRecord]:
        if visibility is None:
            rows = self._query_all(
                "SELECT * FROM experience_records ORDER BY created_at DESC, record_key", ()
            )
        else:
            rows = self._query_all(
                "SELECT * FROM experience_records WHERE visibility = ? "
                "ORDER BY created_at DESC, record_key",
                (visibility,),
            )
        return [_record_from_row(row) for row in rows]

    def list_records_for_notice(self, notice_id: str) -> list[ExperienceRecord]:
        rows = self._query_all(
            "SELECT * FROM experience_records WHERE notice_id = ? ORDER BY record_key",
            (notice_id,),
        )
        return [_record_from_row(row) for row in rows]

    def list_evidence_for_record(self, record_key: str) -> list[Evidence]:
        rows = self._query_all(
            "SELECT * FROM evidence WHERE record_key = ? ORDER BY evidence_id",
            (record_key,),
        )
        return [_evidence_from_row(row) for row in rows]

    def list_events(self, notice_id: str | None = None) -> list[ProcessingEvent]:
        if notice_id is None:
            rows = self._query_all(
                "SELECT * FROM processing_events ORDER BY event_id", ()
            )
        else:
            rows = self._query_all(
                "SELECT * FROM processing_events WHERE notice_id = ? ORDER BY event_id",
                (notice_id,),
            )
        return [_event_from_row(row) for row in rows]

    # ---- 检索支持 ----

    def find_notice_ids_by_keywords(self, keywords: list[str]) -> set[str]:
        """关键词召回：FTS5 trigram MATCH（≥3字）+ 归一化 LIKE 回退（1-2字中文短词）。

        关键词是参数化传入的用户输入，MATCH 查询把每个词用双引号包裹成短语，
        防止词内特殊字符被解释为 FTS 查询语法。
        """
        matched: set[str] = set()
        with self._lock:
            for keyword in keywords:
                fts_rows = self._conn.execute(
                    "SELECT notice_id FROM articles WHERE rowid IN "
                    "(SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?)",
                    (f'"{keyword}"',),
                ).fetchall()
                matched.update(row["notice_id"] for row in fts_rows)
                if not fts_rows:
                    like_rows = self._conn.execute(
                        "SELECT notice_id FROM articles WHERE title LIKE ? OR clean_text LIKE ?",
                        (f"%{keyword}%", f"%{keyword}%"),
                    ).fetchall()
                    matched.update(row["notice_id"] for row in like_rows)
        return matched

    def list_records_with_articles(
        self, visibility: str | None = None
    ) -> list[tuple[ExperienceRecord, Article]]:
        """记录与文章联查（角色可见性过滤在调用方按 RolePolicy 决定）。"""
        if visibility is None:
            rows = self._query_all(
                "SELECT r.*, a.title AS a_title, a.source_url AS a_source_url, "
                "a.published_at AS a_published_at, a.content_type AS a_content_type, "
                "a.fetch_status AS a_fetch_status, a.clean_text AS a_clean_text, "
                "a.schema_version AS a_schema_version, a.fetched_at AS a_fetched_at, "
                "a.failure_reason AS a_failure_reason "
                "FROM experience_records r JOIN articles a ON r.notice_id = a.notice_id",
                (),
            )
        else:
            rows = self._query_all(
                "SELECT r.*, a.title AS a_title, a.source_url AS a_source_url, "
                "a.published_at AS a_published_at, a.content_type AS a_content_type, "
                "a.fetch_status AS a_fetch_status, a.clean_text AS a_clean_text, "
                "a.schema_version AS a_schema_version, a.fetched_at AS a_fetched_at, "
                "a.failure_reason AS a_failure_reason "
                "FROM experience_records r JOIN articles a ON r.notice_id = a.notice_id "
                "WHERE r.visibility = ?",
                (visibility,),
            )
        results: list[tuple[ExperienceRecord, Article]] = []
        for row in rows:
            record = _record_from_row(row)
            article = Article(
                notice_id=row["notice_id"],
                title=row["a_title"],
                source_url=row["a_source_url"],
                content_type=row["a_content_type"],
                fetch_status=row["a_fetch_status"],
                fetched_at=row["a_fetched_at"],
                published_at=row["a_published_at"],
                clean_text=row["a_clean_text"],
                failure_reason=row["a_failure_reason"],
                schema_version=row["a_schema_version"],
            )
            results.append((record, article))
        return results

    def count_evidence_by_record(self) -> dict[str, int]:
        rows = self._query_all(
            "SELECT record_key, COUNT(*) AS n FROM evidence GROUP BY record_key", ()
        )
        return {row["record_key"]: row["n"] for row in rows}

    def database_ok(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    # ---- 计数 ----

    def _count(self, table: str) -> int:
        # 表名来自本模块内部常量调用点，不接收外部输入
        with self._lock:
            return int(self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def count_articles(self) -> int:
        return self._count("articles")

    def count_assets(self) -> int:
        return self._count("assets")

    def count_records(self) -> int:
        return self._count("experience_records")

    def count_evidence(self) -> int:
        return self._count("evidence")

    def count_events(self) -> int:
        return self._count("processing_events")


# ---- 行 → 领域模型 ----


def _article_from_row(row: sqlite3.Row) -> Article:
    return Article(
        notice_id=row["notice_id"],
        title=row["title"],
        source_url=row["source_url"],
        content_type=row["content_type"],
        fetch_status=row["fetch_status"],
        fetched_at=row["fetched_at"],
        published_at=row["published_at"],
        clean_text=row["clean_text"],
        failure_reason=row["failure_reason"],
        schema_version=row["schema_version"],
    )


def _record_from_row(row: sqlite3.Row) -> ExperienceRecord:
    return ExperienceRecord(
        record_key=row["record_key"],
        notice_id=row["notice_id"],
        extractor_version=row["extractor_version"],
        review_status=row["review_status"],
        confidence=row["confidence"],
        cohort=row["cohort"],
        grade=row["grade"],
        education=row["education"],
        college=row["college"],
        major=row["major"],
        city=row["city"],
        position_or_unit=row["position_or_unit"],
        visibility=row["visibility"],
        person_name=row["person_name"],
        avatar_ref=row["avatar_ref"],
        qr_code_ref=row["qr_code_ref"],
        contact_info=row["contact_info"],
        meeting_entry=row["meeting_entry"],
        original_asset_ref=row["original_asset_ref"],
        source_sso_url=row["source_sso_url"],
    )


def _evidence_from_row(row: sqlite3.Row) -> Evidence:
    return Evidence(
        record_key=row["record_key"],
        field=row["field"],
        text=row["text"],
        method=row["method"],
        asset_id=row["asset_id"],
        bbox=json.loads(row["bbox"]) if row["bbox"] else None,
    )


def _event_from_row(row: sqlite3.Row) -> ProcessingEvent:
    return ProcessingEvent(
        notice_id=row["notice_id"],
        step=row["step"],
        status=row["status"],
        occurred_at=row["occurred_at"],
        failure_reason=row["failure_reason"],
        event_id=row["event_id"],
    )
