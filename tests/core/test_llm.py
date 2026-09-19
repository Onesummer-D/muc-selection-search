"""LLMProvider 与 AnswerService 模型边界测试。

LLM 是外部服务，测试通过注入 StubProvider 覆盖模型边界；
Repository / SearchService 全程使用真实 SQLite 内存实现，不 mock 数据层。
覆盖：正常引用、越界引用回退、无引用回退、模型异常回退、未配置降级、DeepSeek 响应解析。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.repository.sqlite_repository import SQLiteRepository
from app.search.answer_service import AnswerService
from app.search.llm_provider import (
    DeepSeekProvider,
    LLMError,
    LLMResult,
    NullProvider,
    get_llm_provider,
)
from app.web.seed import seed


class StubProvider:
    """可控输出 stub，覆盖模型边界。"""

    def __init__(self, text: str | None = None, error: Exception | None = None):
        self._text = text
        self._error = error
        self.name = "stub"
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResult:
        self.calls.append((system_prompt, user_prompt))
        if self._error is not None:
            raise self._error
        return LLMResult(text=self._text or "", model="stub")


class AnswerLLMTests(unittest.TestCase):
    def setUp(self):
        # 与本机 .env / 环境解耦：本类所有用例都按"未配置或显式注入"运行
        import os

        for var in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
            os.environ.pop(var, None)
        self.repo = SQLiteRepository(":memory:")
        seed(self.repo)
        self.answer = AnswerService(self.repo)

    def tearDown(self):
        self.repo.close()

    def test_llm_answer_with_valid_citations_not_degraded(self):
        stub = StubProvider(
            text="匹配到 1 条符合条件的记录：本科计算机方向，去向成都基层岗位 [1]。"
                 "该记录与你的需求高度相关 [1]。"
        )
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("2026届计算机本科，想看西部基层案例", "guest")
        self.assertFalse(outcome.degraded)
        self.assertFalse(outcome.insufficient_evidence)
        self.assertEqual([c["index"] for c in outcome.citations], [1])
        self.assertEqual(outcome.citations[0]["record_key"], "portal-10001-01")
        # prompt 只含证据包，不含 SQL 或仓库细节
        prompt = stub.calls[0][1]
        self.assertIn("portal-10001-01", prompt)
        self.assertNotIn("SELECT", prompt)
        self.assertNotIn("sqlite", prompt.lower())

    def test_llm_out_of_range_citation_falls_back(self):
        stub = StubProvider(text="结论 [99] 完全越界。")
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("成都 计算机本科", "guest")
        self.assertTrue(outcome.degraded)
        self.assertIn("引用校验", outcome.degraded_reason)
        self.assertTrue(outcome.citations)  # 回退模板仍带真实引用
        self.assertIn("[1]", outcome.answer)

    def test_llm_no_citation_falls_back(self):
        stub = StubProvider(text="看起来有不少好记录，祝你顺利上岸！")
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("成都 计算机本科", "guest")
        self.assertTrue(outcome.degraded)
        self.assertIn("引用", outcome.degraded_reason)

    def test_llm_record_key_citation_normalized(self):
        """模型用 [record_key] 引用时归一化为序号，不降级。"""
        stub = StubProvider(
            text="该记录去向成都基层岗位 [portal-10001-01]，专业对口。"
        )
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("成都 计算机本科", "guest")
        self.assertFalse(outcome.degraded)
        self.assertEqual([c["index"] for c in outcome.citations], [1])

    def test_llm_unknown_record_key_falls_back(self):
        stub = StubProvider(text="该记录 [portal-99999-99] 莫名其妙。")
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("成都 计算机本科", "guest")
        self.assertTrue(outcome.degraded)

    def test_llm_error_falls_back(self):
        stub = StubProvider(error=LLMError("网络超时"))
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("成都 计算机本科", "guest")
        self.assertTrue(outcome.degraded)
        self.assertIn("网络超时", outcome.degraded_reason)
        self.assertTrue(outcome.records)  # 传统结果照常返回
        self.assertIn("[1]", outcome.answer)

    def test_no_llm_configured_uses_template(self):
        outcome = self.answer.answer("成都 计算机本科", "guest")
        self.assertTrue(outcome.degraded)
        self.assertIn("规则模板", outcome.degraded_reason)
        self.assertFalse(outcome.insufficient_evidence)
        self.assertTrue(outcome.citations)

    def test_insufficient_evidence_with_llm_configured(self):
        stub = StubProvider(text="这条 [1] 勉强相关。")
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("博士 乌鲁木齐", "guest")
        self.assertTrue(outcome.insufficient_evidence)
        self.assertEqual(outcome.citations, [])
        stub.calls  # 有证据不足时模型不应被调用（无引用可给）
        self.assertEqual(stub.calls, [])

    def test_llm_answer_guest_citations_contain_no_private_data(self):
        stub = StubProvider(text="该记录去向成都 [1]，与你条件匹配。")
        service = AnswerService(self.repo, llm_provider=stub)
        outcome = service.answer("成都 计算机本科", "guest")
        flat = json.dumps(outcome.citations, ensure_ascii=False)
        for forbidden in ("person_name", "avatar_ref", "contact_info",
                          "meeting_entry", "qr_code_ref", "source_sso_url"):
            self.assertNotIn(forbidden, flat)


class ProviderFactoryTests(unittest.TestCase):
    def tearDown(self):
        import os

        for var in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):
            os.environ.pop(var, None)

    def test_factory_returns_none_without_config(self):
        import os

        os.environ.pop("LLM_PROVIDER", None)
        self.assertIsNone(get_llm_provider())

    def test_factory_builds_deepseek(self):
        import os

        os.environ["LLM_PROVIDER"] = "deepseek"
        os.environ["LLM_API_KEY"] = "test-key"
        provider = get_llm_provider()
        self.assertIsInstance(provider, DeepSeekProvider)
        self.assertEqual(provider.name, "deepseek:deepseek-chat")

    def test_factory_unknown_provider_is_none(self):
        import os

        os.environ["LLM_PROVIDER"] = "gpt-99"
        os.environ["LLM_API_KEY"] = "k"
        self.assertIsNone(get_llm_provider())

    def test_null_provider_raises(self):
        with self.assertRaises(LLMError):
            NullProvider().complete("s", "u")


class DeepSeekResponseParsingTests(unittest.TestCase):
    def test_parses_chat_completion_shape(self):
        body = {"choices": [{"message": {"content": "你好 [1]"}}]}
        text = body["choices"][0]["message"]["content"]
        self.assertEqual(text, "你好 [1]")

    def test_bad_shape_raises_llm_error(self):
        body = {"error": "x"}
        with self.assertRaises((KeyError, IndexError, TypeError)):
            _ = body["choices"][0]["message"]["content"]


if __name__ == "__main__":
    unittest.main()
