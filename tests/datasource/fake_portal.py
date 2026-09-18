"""可注入的假门户：不访问真实网络，覆盖任务书要求的场景。

场景由 FakePortal 的脚本（script）驱动：
- ("page", page_no, rows)：第 page_no 页返回 rows
- ("status", status_code)：返回该 HTTP 状态（每次消耗一条）
- ("timeout",)：抛超时
- ("delay", seconds)：配合可注入时钟
"""
from __future__ import annotations

import json


class FakeResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        if not self.text:
            raise ValueError("empty body")
        return json.loads(self.text)


class FakePortal:
    """按页提供数据的假门户传输层。"""

    def __init__(self, pages: dict[int, list[dict]] | None = None,
                 details: dict[str, dict] | None = None,
                 script: list[tuple] | None = None):
        self.pages = pages or {}
        self.details = details or {}
        self.script = list(script or [])
        self.calls: list[dict] = []

    def _next_script_step(self):
        return self.script.pop(0) if self.script else None

    def get(self, url: str, params: dict, timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params})
        step = self._next_script_step()
        if step:
            kind = step[0]
            if kind == "status":
                return FakeResponse(step[1], None)
            if kind == "timeout":
                raise TimeoutError("simulated timeout")
        if "getNoticeByPage" in url:
            page = int(params.get("page", params.get("currentPage", 1)))
            rows = self.pages.get(page, [])
            return FakeResponse(200, {"data": rows})
        if "getNotice" in url:
            notice_id = str(params.get("noticeId"))
            detail = self.details.get(notice_id)
            if detail is None:
                return FakeResponse(404, None)
            return FakeResponse(200, {"data": detail})
        return FakeResponse(404, None)

    def post(self, url: str, data: dict, timeout: float) -> FakeResponse:
        """POST 表单模式：真实门户（comsys）走这条路，响应为 datas.tables。"""
        self.calls.append({"url": url, "params": dict(data)})
        step = self._next_script_step()
        if step:
            kind = step[0]
            if kind == "status":
                return FakeResponse(step[1], None)
            if kind == "timeout":
                raise TimeoutError("simulated timeout")
        if "getNoticeByPage" in url:
            page = int(data.get("currentPage", data.get("page", 1)))
            rows = self.pages.get(page, [])
            # 真实门户结构：{"datas": {"tables": [...]}}，字段为 snake_case
            return FakeResponse(200, {"datas": {"tables": rows}})
        return FakeResponse(404, None)


class FakeClock:
    """虚拟时钟：sleep 推进时间，不真实等待。"""

    def __init__(self, start: float = 1000.0):
        self._now = start

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds
