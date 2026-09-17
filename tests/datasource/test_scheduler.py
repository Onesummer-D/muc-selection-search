"""Scheduler 测试：周期触发、单实例锁、会话失效暂停与恢复。"""
from __future__ import annotations

import os
import tempfile
import unittest

from app.sync.scheduler import LockBusyError, Scheduler, SingleInstanceLock


class TestSingleInstanceLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.tmp, "scheduler.lock")

    def test_second_instance_rejected(self):
        lock1 = SingleInstanceLock(self.lock_path, pid=100)
        lock1.acquire()
        lock2 = SingleInstanceLock(self.lock_path, pid=200)
        with self.assertRaises(LockBusyError):
            lock2.acquire()
        lock1.release()
        # 释放后可再次获取
        lock2.acquire()
        lock2.release()

    def test_stale_lock_reclaimed(self):
        lock = SingleInstanceLock(self.lock_path, pid=100)
        lock.acquire()
        # 篡改时间戳为很久以前 → 视为陈旧锁回收
        with open(self.lock_path, "w", encoding="utf-8") as fh:
            fh.write('{"pid": 100, "timestamp": 0}')
        lock2 = SingleInstanceLock(self.lock_path, pid=200)
        lock2.acquire()  # 不应抛 LockBusyError
        lock2.release()


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.tmp, "scheduler.lock")
        self.runs = []

    def _scheduler(self, interval, result=None):
        def runner():
            self.runs.append(1)
            return result
        return Scheduler(runner, interval_seconds=interval,
                         lock_path=self.lock_path)

    def test_periodic_trigger(self):
        sched = self._scheduler(interval=60.0)
        self.assertTrue(sched.tick(now=0))       # 首次立即触发
        self.assertFalse(sched.tick(now=30))     # 未到周期：不触发
        self.assertTrue(sched.tick(now=60))      # 到期触发
        self.assertEqual(len(self.runs), 2)

    def test_no_concurrent_second_instance(self):
        # 外部进程占用锁时，run_once 不并发启动
        external = SingleInstanceLock(self.lock_path, pid=999)
        external.acquire()
        sched = self._scheduler(interval=60.0)
        with self.assertRaises(LockBusyError):
            sched.run_once()
        external.release()

    def test_reentrant_guard_inside_instance(self):
        sched = self._scheduler(interval=60.0)
        sched._running = True  # 模拟正在运行
        self.assertFalse(sched.run_once())

    def test_session_expired_pauses(self):
        class R:
            failure_reason = "session_expired"
            status = "failed"
        sched = self._scheduler(interval=10.0, result=R())
        self.assertTrue(sched.tick(now=0))
        self.assertTrue(sched.needs_login)
        self.assertFalse(sched.tick(now=100))  # 暂停：不再触发
        sched.resume_after_login()
        self.assertTrue(sched.tick(now=200))   # 人工登录后恢复

    def test_normal_result_does_not_pause(self):
        class R:
            failure_reason = None
            status = "processed"
        sched = self._scheduler(interval=10.0, result=R())
        sched.tick(now=0)
        self.assertFalse(sched.needs_login)


if __name__ == "__main__":
    unittest.main()
