"""门户 HTTP 客户端：getNoticeByPage（列表）与 getNotice（详情）。

- 传输层可注入（Transport 协议），测试中不访问真实网络。
- 会话只接收 CAS 人工登录后的内存 Cookie，客户端不读取键盘、不落盘。
"""
from __future__ import annotations

import json
from typing import Callable, Protocol

from .config import PortalConfig
from .rate import RateLimiter, RetryPolicy, SystemClock, is_retryable


class PortalError(Exception):
    """门户响应无法解析等永久性错误。"""


class PortalHTTPError(Exception):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(f"门户返回 HTTP {status_code}")


class PortalTimeout(Exception):
    pass


class SessionExpiredError(Exception):
    """CAS 会话失效：停止更新并提示重新登录，不清空已入库结果。"""


class Response(Protocol):
    status_code: int
    text: str

    def json(self) -> object: ...


class Transport(Protocol):
    """可注入的传输层（默认使用内存中的 requests.Session）。"""

    def get(self, url: str, params: dict, timeout: float) -> Response: ...


class RequestsTransport:
    """基于 requests.Session 的默认传输。Session 由调用方注入（内存 Cookie）。"""

    def __init__(self, session):
        self._session = session

    def get(self, url: str, params: dict, timeout: float) -> Response:
        resp = self._session.get(url, params=params, timeout=timeout)
        if resp.status_code in (301, 302) or (
            resp.history and any(r.status_code in (301, 302) for r in resp.history)
        ):
            raise SessionExpiredError("门户重定向到登录页，会话已失效")
        return resp


class PortalClient:
    """配置化门户客户端。"""

    def __init__(self, config: PortalConfig, transport: Transport,
                 clock=None, sleep=None, rng=None):
        self.config = config
        self.transport = transport
        self.rate_limiter = RateLimiter(config.rate_min, config.rate_max,
                                        clock=clock, sleep=sleep, rng=rng)
        self.retry_policy = RetryPolicy(config.max_retries, config.backoff_base,
                                        sleep=sleep)
        # 请求日志：[(开始时间, 端点, 状态)]，供验收核对限速口径
        self.request_log: list[dict] = []

    # ------------------------------------------------------------------
    def _request(self, url: str, params: dict) -> object:
        waited = self.rate_limiter.wait_before_next()
        attempts_used = [0]

        def _do():
            attempts_used[0] += 1
            resp = self.transport.get(url, params=params, timeout=self.config.timeout)
            if resp.status_code in (401, 403):
                raise SessionExpiredError(f"门户返回 HTTP {resp.status_code}，会话已失效")
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise PortalHTTPError(resp.status_code, resp.text[:200])
            if resp.status_code >= 400:
                raise PortalHTTPError(resp.status_code, resp.text[:200])
            try:
                return resp.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise PortalError(f"响应不是合法 JSON: {exc}") from exc

        def _retryable(exc: Exception) -> bool:
            if isinstance(exc, PortalHTTPError):
                return is_retryable(exc.status_code)
            return isinstance(exc, PortalTimeout)

        try:
            payload, attempts = self.retry_policy.run(_do, _retryable)
        except PortalHTTPError as exc:
            self.request_log.append({"start": self.rate_limiter.last_start(),
                                     "url": url, "status": exc.status_code,
                                     "attempts": attempts_used[0]})
            raise
        except SessionExpiredError:
            self.request_log.append({"start": self.rate_limiter.last_start(),
                                     "url": url, "status": 401,
                                     "attempts": attempts_used[0]})
            raise
        self.request_log.append({"start": self.rate_limiter.last_start(),
                                 "url": url, "status": 200,
                                 "attempts": attempts or attempts_used[0]})
        return payload

    # ------------------------------------------------------------------
    def list_notices(self, page: int) -> list[dict]:
        """getNoticeByPage：返回规范化列表项。

        每项包含 notice_id、title、published_at、source_url。
        """
        params = dict(self.config.list_params)
        params.update({"page": page, "pageSize": self.config.page_size})
        payload = self._request(self.config.list_url(), params)
        rows = self._extract_rows(payload)
        return [self._normalize_list_item(row) for row in rows]

    def get_notice(self, notice_id: str) -> dict:
        """getNotice：返回详情（正文、图片引用）。

        详情缺字段时：正文缺失 → clean_text=None；图片缺失 → 空列表；
        notice_id 缺失 → PortalError（无法登记台账）。
        """
        payload = self._request(self.config.detail_url(), {"noticeId": notice_id})
        if not isinstance(payload, dict):
            raise PortalError(f"详情响应不是对象: {notice_id}")
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise PortalError(f"详情 data 不是对象: {notice_id}")
        return {
            "notice_id": data.get("noticeId") or notice_id,
            "title": data.get("title") or "",
            "content": data.get("content") or data.get("text"),
            "published_at": data.get("publishTime"),
            "source_url": data.get("url") or f"{self.config.base_url.rstrip('/')}/notice/{notice_id}",
            "images": data.get("images") or data.get("imageUrls") or [],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_rows(payload: object) -> list:
        if isinstance(payload, dict):
            rows = payload.get("data", payload.get("rows", payload.get("list")))
            if isinstance(rows, dict):
                rows = rows.get("records", rows.get("rows", []))
            if rows is None:
                return []
            if isinstance(rows, list):
                return rows
        if isinstance(payload, list):
            return payload
        raise PortalError("列表响应无法解析为行数组")

    def _normalize_list_item(self, row: dict) -> dict:
        notice_id = row.get("noticeId") or row.get("id")
        if not notice_id:
            raise PortalError(f"列表项缺少 notice_id: {row!r}")
        return {
            "notice_id": str(notice_id),
            "title": row.get("title") or "",
            "published_at": row.get("publishTime"),
            "source_url": row.get("url")
            or f"{self.config.base_url.rstrip('/')}/notice/{notice_id}",
        }

    # ------------------------------------------------------------------
    def iterate_notices(self):
        """分页迭代：保存当前页与最后 notice_id；重复页去重；空列表/无新项终止。

        yields 规范化列表项（同一 notice_id 只出现一次）。
        """
        seen: set[str] = set()
        page = 1
        last_page_ids: tuple = ()
        while True:
            items = self.list_notices(page)
            if not items:
                return
            page_ids = tuple(i["notice_id"] for i in items)
            if page_ids == last_page_ids:
                # 重复页（门户固定返回最后一页）：去重后终止
                return
            last_page_ids = page_ids
            new_items = [i for i in items if i["notice_id"] not in seen]
            if not new_items:
                return
            for item in new_items:
                seen.add(item["notice_id"])
                yield item
            if len(items) < self.config.page_size:
                return
            page += 1

    # ------------------------------------------------------------------
    def validate_session(self) -> bool:
        """同步前调用只读接口验证会话；失效抛 SessionExpiredError。"""
        params = dict(self.config.list_params)
        params.update({"page": 1, "pageSize": 1})
        self._request(self.config.session_check_url(), params)
        return True
