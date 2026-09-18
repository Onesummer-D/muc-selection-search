"""Scheduler：周期配置、单实例锁和调用 SyncService。

- 不复制任何采集逻辑（采集只在 SyncService）。
- 单实例锁：锁文件原子创建（O_CREAT|O_EXCL），含 PID 与时间戳，
  可检测陈旧锁；同机第二实例拒绝启动。
- CAS 会话失效时任务暂停并提示人工登录（needs_login 状态），
  已入库查询继续可用。
- 时钟与触发可注入：测试中直接调用 tick() 验证调度触发与不并发。
"""
from __future__ import annotations

import json
import os
import time
import uuid


class LockBusyError(Exception):
    """另一个 Scheduler 实例正在运行。"""


class SingleInstanceLock:
    """跨进程单实例锁（本机文件锁）。"""

    def __init__(self, lock_path: str, stale_seconds: float = 3600.0,
                 pid: int | None = None):
        self.lock_path = lock_path
        self.stale_seconds = stale_seconds
        self.pid = pid or os.getpid()
        self._held = False

    def acquire(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.lock_path)), exist_ok=True)
        if os.path.exists(self.lock_path):
            try:
                with open(self.lock_path, encoding="utf-8") as fh:
                    info = json.load(fh)
                age = time.time() - float(info.get("timestamp", 0))
                if age > self.stale_seconds:
                    os.unlink(self.lock_path)  # 陈旧锁回收
                else:
                    raise LockBusyError(
                        f"另一实例正在运行 pid={info.get('pid')} "
                        f"lock={self.lock_path}")
            except (json.JSONDecodeError, OSError):
                # 损坏的锁文件视为陈旧，回收
                try:
                    os.unlink(self.lock_path)
                except OSError:
                    pass
        fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": self.pid, "timestamp": time.time()}, fh)
        self._held = True

    def release(self) -> None:
        if self._held and os.path.exists(self.lock_path):
            os.unlink(self.lock_path)
        self._held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


class Scheduler:
    """周期调度器。测试中调用 tick(now) 模拟时间推进。"""

    def __init__(self, sync_runner, interval_seconds: float,
                 lock_path: str = ".sync_scheduler.lock"):
        """sync_runner: () -> SyncResult（通常为闭包调用 SyncService.sync）。"""
        self.sync_runner = sync_runner
        self.interval_seconds = interval_seconds
        self.lock_path = lock_path
        self._last_run_at: float | None = None
        self._running = False
        self.last_result = None
        self.needs_login = False

    # ------------------------------------------------------------------
    def tick(self, now: float):
        """时间推进到 now；到期则触发一次同步。返回是否触发。"""
        if self.needs_login:
            return False  # 会话失效：暂停调度，等待人工重新登录
        if self._last_run_at is None or (now - self._last_run_at) >= self.interval_seconds:
            return self.run_once(now=now)
        return False

    def run_once(self, now: float | None = None):
        """加锁执行一次同步；锁被占用时不并发启动第二实例。"""
        if self._running:
            return False  # 同一实例内防重入
        with SingleInstanceLock(self.lock_path) as lock:
            self._running = True
            try:
                result = self.sync_runner()
            finally:
                self._running = False
                self._last_run_at = time.time() if now is None else now
        self.last_result = result
        if getattr(result, "failure_reason", None) == "session_expired":
            self.needs_login = True  # 暂停并提示人工登录
        return True

    def resume_after_login(self):
        """人工重新登录后恢复调度。"""
        self.needs_login = False

    # ------------------------------------------------------------------
    def run_forever(self, sleep=time.sleep, clock=time.time):
        """阻塞式循环（生产路径）；测试不使用。"""
        while True:
            if not self.tick(clock()):
                sleep(min(self.interval_seconds, 1.0))
