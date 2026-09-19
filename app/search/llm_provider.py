"""LLMProvider 接口与 DeepSeek 实现。

边界（ARCHITECTURE 第 7、9 节 + 附录 G）：
- LLM 的输入只有 UserQuery、QueryPlan 和 EvidencePack，不接触数据库、SQL 或门户。
- 输出必须带引用；CitationValidator 校验每个引用都来自证据包，校验失败按降级处理。
- LLM 不可用（未配置、网络失败、超时）时回退规则模板，传统检索不受影响。

DeepSeek 使用 OpenAI 兼容的 /chat/completions 接口，标准库 urllib 实现，不新增依赖。
API Key 只从环境变量读取，不得进入代码或仓库。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_TOKENS = 500


@dataclass
class LLMResult:
    """一次模型调用的原始文本输出。"""

    text: str
    model: str


class LLMProvider(ABC):
    """可插拔模型接口。业务层只依赖本抽象。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResult:
        """单轮补全。失败抛 LLMError，由调用方决定降级。"""


class LLMError(RuntimeError):
    """模型调用失败（网络、超时、HTTP 错误、响应格式）。"""


class DeepSeekProvider(LLMProvider):
    """DeepSeek chat 模型（OpenAI 兼容协议）。"""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return f"deepseek:{self._model}"

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResult:
        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._max_tokens,
            "temperature": 0.3,
            "stream": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise LLMError(f"DeepSeek 调用失败：{exc}") from exc
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"DeepSeek 响应格式异常：{exc}") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMError("DeepSeek 返回了空回答")
        return LLMResult(text=text.strip(), model=self._model)


class NullProvider(LLMProvider):
    """未配置模型时的占位实现；调用即抛错，走降级路径。"""

    @property
    def name(self) -> str:
        return "none"

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResult:
        raise LLMError("LLM 未配置")


def get_llm_provider() -> LLMProvider | None:
    """按环境变量装配模型；LLM_PROVIDER/LLM_API_KEY 缺失时返回 None（降级）。"""
    provider_name = os.environ.get("LLM_PROVIDER", "").strip().lower()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not provider_name or provider_name == "none" or not api_key:
        return None
    if provider_name == "deepseek":
        return DeepSeekProvider(
            api_key=api_key,
            model=os.environ.get("LLM_MODEL", "deepseek-chat"),
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        )
    # 未知供应商不猜测，按未配置处理
    return None
