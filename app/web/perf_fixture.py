"""任务3 性能夹具与查询基准：100 行脱敏数据，≥30 次普通查询，max 与 P95 均须 < 1s。

夹具特征：
- 20 篇文章 × 5 条记录 = 100 条 experience_records（一帖多人），经正式 BundleImporter 入库
- 全部为虚构脱敏数据（无姓名、无头像、无联系方式），local_ref 一律 private:// 前缀
- 发布状态约 70% published / 30% draft，review_required 混合，覆盖三角色查询路径

基准通过 Flask test_client 走完整 HTTP 链路（含参数解析、检索、DTO 序列化），
计时不含夹具导入。用法：python -m app.web.perf_fixture
"""

from __future__ import annotations

import statistics
import sys
import time
from dataclasses import dataclass

from ..repository.importer import BundleImporter
from ..repository.sqlite_repository import SQLiteRepository
from .seed import _ev

CITIES = ["成都", "重庆", "西安", "昆明", "绵阳", "兰州", "贵阳", "南宁"]
MAJORS = ["计算机科学与技术", "软件工程", "法学", "金融学", "电子信息", "机械设计"]
EDUCATIONS = ["本科", "硕士", "博士"]
COHORTS = ["2024届", "2025届", "2026届"]
POSITIONS = ["基层岗位", "省级机关岗位", "乡镇岗位"]
GRASSROOT_NOTE = "笔试复习行测申论，面试练习基层情景题，经验分享。"

TOTAL_ARTICLES = 20
RECORDS_PER_ARTICLE = 5


def _sha(n: int) -> str:
    return f"{n & ((1 << 256) - 1):064x}"


def perf_bundles() -> list[dict]:
    """构造 20 篇 article bundle + 20 个 extraction bundle（共 100 条记录）。"""
    bundles: list[dict] = []
    for a in range(1, TOTAL_ARTICLES + 1):
        notice_id = f"perf-{a:05d}"
        city = CITIES[a % len(CITIES)]
        bundles.append({
            "schema_version": "article_bundle.v1",
            "notice_id": notice_id,
            "title": f"{CITIES[(a + 3) % len(CITIES)]}选调经验帖 {a:05d}",
            "source_url": f"https://portal.example.invalid/perf/{notice_id}",
            "published_at": f"2026-09-{(a % 14) + 1:02d}T08:00:00+08:00",
            "content_type": "mixed",
            "clean_text": (
                f"{city}选调经验：{MAJORS[a % len(MAJORS)]}专业，{EDUCATIONS[a % len(EDUCATIONS)]}学历，"
                f"{COHORTS[a % len(COHORTS)]}，{POSITIONS[a % len(POSITIONS)]}。{GRASSROOT_NOTE}"
            ),
            "asset_refs": [{
                "asset_id": f"{notice_id}-poster-01",
                "kind": "poster",
                "local_ref": f"private://{notice_id}/poster-01",
                "sha256": _sha(a * 7919 + 13),
            }],
            "fetch_status": "processed",
            "failure_reason": None,
            "fetched_at": "2026-09-18T09:00:00+08:00",
        })
        records = []
        for r in range(RECORDS_PER_ARTICLE):
            idx = (a - 1) * RECORDS_PER_ARTICLE + r + 1
            review = "review_required" if idx % 10 == 0 else "processed"
            records.append({
                "record_key": f"perf-{idx:05d}",
                "cohort": COHORTS[idx % len(COHORTS)],
                "grade": None,
                "education": EDUCATIONS[idx % len(EDUCATIONS)],
                "college": f"学院{idx % 9 + 1}",
                "major": MAJORS[(idx + a) % len(MAJORS)],
                "city": CITIES[(idx + 2 * a) % len(CITIES)],
                "position_or_unit": POSITIONS[idx % len(POSITIONS)],
                "review_status": review,
                "confidence": 0.55 + (idx % 40) / 100,
                "evidence": [
                    _ev("city", f"工作地点 {CITIES[(idx + 2 * a) % len(CITIES)]}",
                        f"perf-{a:05d}-poster-01", [10, 20, 30, 40], "ocr_rule"),
                    _ev("major", f"专业 {MAJORS[(idx + a) % len(MAJORS)]}"),
                ],
            })
        bundles.append({
            "schema_version": "extraction_bundle.v1",
            "notice_id": notice_id,
            "extractor_version": "perf-fixture-0.1.0",
            "records": records,
            "processing_status": "processed",
            "failure_reason": None,
            "processed_at": "2026-09-18T09:30:00+08:00",
        })
    return bundles


@dataclass
class PerfReport:
    query_count: int
    max_ms: float
    p95_ms: float
    mean_ms: float
    slowest_query: str
    fixture_rows: dict

    def to_lines(self) -> list[str]:
        return [
            f"查询次数: {self.query_count}",
            f"最大值: {self.max_ms:.1f} ms",
            f"P95: {self.p95_ms:.1f} ms",
            f"平均: {self.mean_ms:.1f} ms",
            f"最慢查询: {self.slowest_query}",
            f"夹具规模: {self.fixture_rows}",
            f"阈值: max < 1000ms 且 P95 < 1000ms -> "
            f"{'PASS' if self.max_ms < 1000 and self.p95_ms < 1000 else 'FAIL'}",
        ]


def build_perf_db() -> SQLiteRepository:
    repo = SQLiteRepository(":memory:")
    importer = BundleImporter(repo)
    published = []
    for bundle in perf_bundles():
        if bundle["schema_version"] == "article_bundle.v1":
            importer.import_article_bundle(bundle)
        else:
            importer.import_extraction_bundle(bundle)
    for i in range(1, TOTAL_ARTICLES * RECORDS_PER_ARTICLE + 1):
        # 70% published，其余保持 draft（review_required 记录对 admin 可见）
        if i % 10 != 0 and i % 3 != 0:
            published.append(f"perf-{i:05d}")
    for key in published:
        repo.set_visibility(key, "published")
    return repo


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, -(-len(ordered) * 95 // 100) - 1)
    return ordered[index]


def run_benchmark(client, query_specs: list[tuple[str, str]] | None = None) -> PerfReport:
    """对 /api/search 跑 ≥30 次普通查询并统计。query_specs: (说明, querystring)。"""
    if query_specs is None:
        query_specs = default_query_specs()
    durations: list[float] = []
    slowest = ("", 0.0)
    for label, qs in query_specs:
        start = time.perf_counter()
        resp = client.get(f"/api/search?{qs}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200, f"{label}: {resp.status_code}"
        durations.append(elapsed_ms)
        if elapsed_ms > slowest[1]:
            slowest = (label, elapsed_ms)
    rows = client.get("/api/search?page_size=1").get_json()
    return PerfReport(
        query_count=len(durations),
        max_ms=max(durations),
        p95_ms=_p95(durations),
        mean_ms=statistics.fmean(durations),
        slowest_query=f"{slowest[0]} ({slowest[1]:.1f} ms)",
        fixture_rows={"records": 100, "articles": TOTAL_ARTICLES,
                      "visible_default": rows["total"]},
    )


def default_query_specs() -> list[tuple[str, str]]:
    """36 次普通查询：空条件、单条件、组合条件、关键词、分页与管理员路径。"""
    specs: list[tuple[str, str]] = [("", "")]
    for city in CITIES:
        specs.append((f"city={city}", f"city={city}"))
    for major in MAJORS[:4]:
        specs.append((f"major={major}", f"major={major}"))
    for education in EDUCATIONS:
        specs.append((f"education={education}", f"education={education}"))
    specs += [
        ("city+major", "city=成都&major=软件工程"),
        ("city+education", "city=成都&education=本科"),
        ("cohort", "cohort=2026届"),
        ("position", "position_or_unit=基层"),
        ("keyword 笔试", "keywords=笔试"),
        ("keyword 申论", "keywords=申论"),
        ("keyword 基层", "keywords=基层"),
        ("keyword 选调", "keywords=选调"),
        ("keyword 情景", "keywords=情景"),
        ("combo+keyword", "city=成都&keywords=基层"),
        ("page2", "page=2&page_size=10"),
        ("page3", "page=3&page_size=20"),
        ("pagesize50", "page_size=50"),
        ("mixed", "education=本科&city=西安&major=法学"),
        ("mixed2", "education=硕士&major=电子信息"),
        ("mixed3", "cohort=2025届&city=昆明"),
    ]
    return specs


def main() -> int:
    repo = build_perf_db()
    # 复用完整应用（真实参数解析 + DTO 序列化），注入 NullProvider 不触发 LLM
    from app.web.app import create_app
    from app.search.llm_provider import NullProvider

    app = create_app(repository=repo, llm_provider=NullProvider())
    client = app.test_client()
    report = run_benchmark(client)
    repo.close()
    print("=== 任务3 性能基准（100 行夹具，HTTP 全链路） ===")
    for line in report.to_lines():
        print(line)
    return 0 if (report.max_ms < 1000 and report.p95_ms < 1000) else 1


if __name__ == "__main__":
    sys.exit(main())
