"""门户数据源配置。

端点、栏目、分页大小和筛选关键词全部集中在此，代码中不得散落硬编码。
真实值通过环境变量（.env，不入库）注入；测试使用显式构造的配置对象。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PortalConfig:
    """学校门户采集配置。"""

    base_url: str = ""
    list_endpoint: str = "getNoticeByPage"
    detail_endpoint: str = "getNotice"
    # 栏目 / 筛选参数（键值对会原样并入列表请求）
    list_params: dict = field(default_factory=lambda: {"columnId": "", "keyword": ""})
    page_size: int = 20
    # 超时（秒）
    timeout: float = 10.0
    # 相邻门户请求开始时间差范围（秒）
    rate_min: float = 0.8
    rate_max: float = 1.5
    # 初次尝试之外最多额外重试次数
    max_retries: int = 3
    # 重试退避基数（秒）：第 n 次重试等待 base * 2**(n-1)
    backoff_base: float = 2.0
    # 只读会话验证接口
    session_check_endpoint: str = "getNoticeByPage"
    # 主题过滤关键词（逗号分隔，命中标题或正文任一即视为相关；空 = 不过滤）
    topic_keywords: tuple = ("选调",)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "PortalConfig":
        """从环境变量构造（生产路径：.env + os.environ）。"""
        e = dict(os.environ if env is None else env)
        params = {"columnId": e.get("PORTAL_COLUMN_ID", ""),
                  "keyword": e.get("PORTAL_KEYWORD", "")}
        return cls(
            base_url=e.get("PORTAL_BASE_URL", ""),
            list_params=params,
            page_size=int(e.get("PORTAL_PAGE_SIZE", "20")),
            timeout=float(e.get("PORTAL_TIMEOUT", "10")),
            rate_min=float(e.get("PORTAL_RATE_MIN", "0.8")),
            rate_max=float(e.get("PORTAL_RATE_MAX", "1.5")),
            max_retries=int(e.get("PORTAL_MAX_RETRIES", "3")),
            topic_keywords=tuple(
                kw.strip() for kw in e.get("PORTAL_TOPIC_KEYWORDS", "选调").split(",")
                if kw.strip()
            ),
        )

    def list_url(self) -> str:
        if not self.base_url:
            raise ValueError("PORTAL_BASE_URL 未配置（见 progress/week1/A/BLOCKED.md B-1）")
        return f"{self.base_url.rstrip('/')}/{self.list_endpoint}"

    def detail_url(self) -> str:
        if not self.base_url:
            raise ValueError("PORTAL_BASE_URL 未配置（见 progress/week1/A/BLOCKED.md B-1）")
        return f"{self.base_url.rstrip('/')}/{self.detail_endpoint}"

    def session_check_url(self) -> str:
        if not self.base_url:
            raise ValueError("PORTAL_BASE_URL 未配置")
        return f"{self.base_url.rstrip('/')}/{self.session_check_endpoint}"
