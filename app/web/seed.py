"""演示数据 seed：虚构、已脱敏的样例 bundle，经正式导入器入库。

数据特征（与静态 Demo 的 3 条虚构记录对齐，扩展到 5 篇文章 7 条记录）：
- 4 条 published（guest/student 可见），2 条 review_required（仅 admin 复核视图），1 条 draft
- 所有 sha256 为演示摘要；local_ref 使用 private:// 受限前缀；不含任何真实个人信息
- 姓名、头像等 7 个私有字段一律留空（bundle 契约不携带）

用法：python -m app.web.seed [数据库路径，默认 data/app.db]
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..repository.importer import BundleImporter
from ..repository.sqlite_repository import SQLiteRepository

_SHA = lambda n: (f"{n:064x}")  # noqa: E731  演示用确定性摘要


def _article(notice_id: str, title: str, published_at: str, content_type: str,
             clean_text: str, asset_count: int = 1) -> dict:
    return {
        "schema_version": "article_bundle.v1",
        "notice_id": notice_id,
        "title": title,
        "source_url": f"https://portal.example.invalid/notice/{notice_id}",
        "published_at": published_at,
        "content_type": content_type,
        "clean_text": clean_text,
        "asset_refs": [
            {
                "asset_id": f"{notice_id}-poster-{i:02d}",
                "kind": "poster",
                "local_ref": f"private://{notice_id}/poster-{i:02d}",
                "sha256": _SHA(i + int(notice_id.split("-")[1])),
            }
            for i in range(1, asset_count + 1)
        ],
        "fetch_status": "processed",
        "failure_reason": None,
        "fetched_at": "2026-09-17T20:30:00+08:00",
    }


def _record(record_key: str, **fields) -> dict:
    evidence = fields.pop("evidence")
    review = fields.pop("review_status", "processed")
    return {
        "record_key": record_key,
        "cohort": fields.get("cohort"),
        "grade": fields.get("grade"),
        "education": fields.get("education"),
        "college": fields.get("college"),
        "major": fields.get("major"),
        "city": fields.get("city"),
        "position_or_unit": fields.get("position_or_unit"),
        "review_status": review,
        "confidence": fields.get("confidence", 0.9),
        "evidence": evidence,
    }


def _ev(field: str, text: str, asset_id: str | None = None,
        bbox: list | None = None, method: str = "html_rule") -> dict:
    return {"field": field, "text": text, "method": method,
            "asset_id": asset_id, "bbox": bbox}


def demo_bundles() -> list[dict]:
    """5 篇文章 bundle + 4 个 extraction bundle（其中一篇一帖多人）。"""
    a1 = _article(
        "portal-10001", "2026届选调经验分享（一）", "2026-09-10T08:00:00+08:00", "poster",
        "2026届本科毕业生分享西部基层选调备考经验：计算机科学与技术专业，工作地点成都，"
        "岗位为基层岗位。笔试重点复习资料分析与申论，面试注重基层工作情景题。",
    )
    e1 = {
        "schema_version": "extraction_bundle.v1",
        "notice_id": "portal-10001",
        "extractor_version": "ocr-rule-0.1.0",
        "records": [
            _record("portal-10001-01", cohort="2026届", education="本科",
                    college="信息学院", major="计算机科学与技术", city="成都",
                    position_or_unit="基层岗位",
                    evidence=[
                        _ev("city", "工作地点 成都", "portal-10001-poster-01",
                            [102, 315, 386, 361], "ocr_rule"),
                        _ev("major", "专业 计算机科学与技术", "portal-10001-poster-01",
                            [40, 210, 350, 246], "ocr_rule"),
                    ]),
            _record("portal-10001-02", cohort="2026届", education="本科",
                    college="法学院", major="法学", city="重庆",
                    position_or_unit="基层岗位",
                    evidence=[
                        _ev("city", "定向重庆基层岗位"),
                        _ev("education", "本科应届可报"),
                    ]),
        ],
        "processing_status": "processed",
        "failure_reason": None,
        "processed_at": "2026-09-18T10:00:00+08:00",
    }

    a2 = _article(
        "portal-10002", "软件工程四川选调心得", "2026-09-11T09:00:00+08:00", "text",
        "软件工程专业学长分享四川选调经历：笔试行测申论、面试结构化。"
        "提醒关注四川各市州岗位表发布时间，基层岗位竞争比约 30:1。",
        asset_count=0,
    )
    e2 = {
        "schema_version": "extraction_bundle.v1",
        "notice_id": "portal-10002",
        "extractor_version": "html-rule-0.2.0",
        "records": [
            _record("portal-10002-01", cohort="2025届", education="本科",
                    college="信息学院", major="软件工程", city="绵阳",
                    position_or_unit="基层岗位",
                    evidence=[
                        _ev("major", "软件工程专业"),
                        _ev("city", "绵阳市某县基层岗"),
                    ]),
        ],
        "processing_status": "processed",
        "failure_reason": None,
        "processed_at": "2026-09-18T10:30:00+08:00",
    }

    a3 = _article(
        "portal-10003", "硕士学姐的云南选调记录", "2026-09-12T14:00:00+08:00", "mixed",
        "硕士研究生学姐分享云南省级机关与州市岗位差异，专业为电子信息，"
        "建议硕士关注省直岗位与昆明市岗位。",
    )
    e3 = {
        "schema_version": "extraction_bundle.v1",
        "notice_id": "portal-10003",
        "extractor_version": "ocr-rule-0.1.0",
        "records": [
            _record("portal-10003-01", cohort="2024届", education="硕士",
                    college="信息学院", major="电子信息", city="昆明",
                    position_or_unit="省级机关岗位",
                    evidence=[
                        _ev("education", "硕士学历", "portal-10003-poster-01",
                            [88, 140, 260, 180], "ocr_rule"),
                        _ev("city", "工作地点 昆明", "portal-10003-poster-01",
                            [102, 315, 386, 361], "ocr_rule"),
                    ]),
        ],
        "processing_status": "processed",
        "failure_reason": None,
        "processed_at": "2026-09-18T11:00:00+08:00",
    }

    a4 = _article(
        "portal-10004", "经院基层选调信息帖（待复核）", "2026-09-13T16:00:00+08:00", "poster",
        "经济学院校友分享基层选调信息，部分海报字段置信度较低，待人工复核。",
    )
    e4 = {
        "schema_version": "extraction_bundle.v1",
        "notice_id": "portal-10004",
        "extractor_version": "ocr-rule-0.1.0",
        "records": [
            _record("portal-10004-01", college="经济学院", review_status="review_required",
                    confidence=0.41,
                    evidence=[_ev("college", "经济学院", "portal-10004-poster-01",
                                  [10, 20, 30, 40], "ocr_rule")]),
            _record("portal-10004-02", cohort="2026届", education="本科",
                    review_status="review_required", confidence=0.55,
                    evidence=[_ev("education", "本科可报")]),
        ],
        "processing_status": "review_required",
        "failure_reason": None,
        "processed_at": "2026-09-18T11:30:00+08:00",
    }

    a5 = _article(
        "portal-10005", "往届经验合集（草稿，未发布）", "2026-09-14T18:00:00+08:00", "text",
        "多篇往届经验摘录，正在整理中，尚未通过人工确认发布。",
        asset_count=0,
    )
    e5 = {
        "schema_version": "extraction_bundle.v1",
        "notice_id": "portal-10005",
        "extractor_version": "html-rule-0.2.0",
        "records": [
            _record("portal-10005-01", education="本科", major="汉语言文学",
                    city="西安", position_or_unit="基层岗位",
                    evidence=[_ev("city", "西安市基层岗位")]),
        ],
        "processing_status": "processed",
        "failure_reason": None,
        "processed_at": "2026-09-18T12:00:00+08:00",
    }
    return [a1, e1, a2, e2, a3, e3, a4, e4, a5, e5]


def seed(repository: SQLiteRepository) -> dict:
    """导入演示 bundle 并按演示语义设置发布状态，返回统计。"""
    importer = BundleImporter(repository)
    for bundle in demo_bundles():
        if bundle["schema_version"] == "article_bundle.v1":
            importer.import_article_bundle(bundle)
        else:
            importer.import_extraction_bundle(bundle)
    for key in ("portal-10001-01", "portal-10001-02", "portal-10002-01", "portal-10003-01"):
        repository.set_visibility(key, "published")
    # portal-10004 保持 review_required + draft（仅 admin 可见），portal-10005 为 draft
    return {
        "articles": repository.count_articles(),
        "assets": repository.count_assets(),
        "records": repository.count_records(),
        "evidence": repository.count_evidence(),
        "events": repository.count_events(),
        "published": len(repository.list_records("published")),
    }


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/app.db"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    repo = SQLiteRepository(path)
    stats = seed(repo)
    repo.close()
    print(f"seeded {path}: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
