"""任务3 性能回归测试：100 行夹具 ≥30 次查询，max 与 P95 均须 < 1s（任务书硬阈值）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.search.llm_provider import NullProvider
from app.web.app import create_app
from app.web.perf_fixture import build_perf_db, run_benchmark

THRESHOLD_MS = 1000


class PerformanceTests(unittest.TestCase):
    def test_100_row_fixture_30_queries_max_and_p95_under_1s(self):
        repo = build_perf_db()
        try:
            app = create_app(repository=repo, llm_provider=NullProvider())
            app.config["TESTING"] = True
            report = run_benchmark(app.test_client())
        finally:
            repo.close()
        self.assertGreaterEqual(report.query_count, 30)
        self.assertEqual(report.fixture_rows["records"], 100)
        self.assertLess(report.max_ms, THRESHOLD_MS,
                        f"max {report.max_ms:.1f}ms 超过 {THRESHOLD_MS}ms")
        self.assertLess(report.p95_ms, THRESHOLD_MS,
                        f"P95 {report.p95_ms:.1f}ms 超过 {THRESHOLD_MS}ms")


if __name__ == "__main__":
    unittest.main()
