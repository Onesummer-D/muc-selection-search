"""限速与重试策略。

- 限速：相邻门户请求的开始时间差随机落在 [rate_min, rate_max]（默认 0.8–1.5 秒）。
- 重试：初次尝试 1 次，最多额外重试 3 次（共 4 次上限），等待逐步延长。
- 时钟与休眠均可注入，供测试使用。
"""
from __future__ import annotations

import random
import time
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    def now(self) -> float:
        return time.time()


class RateLimiter:
    """保证相邻请求 *开始时间* 的间隔落在配置范围内。"""

    def __init__(self, rate_min: float, rate_max: float,
                 clock: Clock | None = None,
                 sleep: Callable[[float], None] | None = None,
                 rng: random.Random | None = None):
        if rate_min > rate_max:
            raise ValueError("rate_min 不能大于 rate_max")
        self.rate_min = rate_min
        self.rate_max = rate_max
        self._clock = clock or SystemClock()
        self._sleep = sleep or time.sleep
        self._rng = rng or random.Random()
        self._last_start: float | None = None

    def wait_before_next(self) -> float:
        """在发起下一次请求前调用；返回实际等待的秒数。"""
        target_gap = self._rng.uniform(self.rate_min, self.rate_max)
        now = self._clock.now()
        if self._last_start is None:
            waited = 0.0
        else:
            elapsed = now - self._last_start
            waited = max(0.0, target_gap - elapsed)
            if waited > 0:
                self._sleep(waited)
        # 记录的是“请求真正开始”的时刻
        self._last_start = self._clock.now()
        return waited

    def last_start(self) -> float | None:
        return self._last_start


class RetryExhaustedError(Exception):
    """超过最大重试次数仍失败。"""

    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"重试 {attempts} 次后仍失败: {last_error}")


def is_retryable(status_code: int | None) -> bool:
    """429 与 5xx 可重试；其他 4xx 不可重试。"""
    if status_code is None:
        return True  # 超时 / 连接错误
    return status_code == 429 or 500 <= status_code < 600


class RetryPolicy:
    """初次尝试 1 次 + 最多 max_retries 次额外重试，退避逐步延长。"""

    def __init__(self, max_retries: int = 3, backoff_base: float = 2.0,
                 sleep: Callable[[float], None] | None = None):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep or time.sleep

    def backoff_seconds(self, retry_no: int) -> float:
        """第 retry_no 次重试（从 1 开始）前的等待秒数。"""
        return self.backoff_base * (2 ** (retry_no - 1))

    def run(self, func: Callable[[], object], should_retry: Callable[[Exception], bool]):
        """执行 func；按 should_retry 判断是否重试。返回 (结果, 尝试次数)。"""
        attempts = 0
        last_error: Exception | None = None
        while attempts <= self.max_retries:
            attempts += 1
            try:
                return func(), attempts
            except Exception as exc:  # noqa: BLE001 - 由 should_retry 精确判定
                last_error = exc
                if attempts > self.max_retries or not should_retry(exc):
                    raise
                self._sleep(self.backoff_seconds(attempts))
        raise RetryExhaustedError(attempts, last_error)  # pragma: no cover
