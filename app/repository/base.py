"""Repository 接口。

业务层只依赖本接口，不绑定 sqlite3 或任何具体存储实现
（ARCHITECTURE.md 第 9 节：Application Service → interface → Repository → 实现）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ContextManager

from ..domain.models import (
    Article,
    Asset,
    Evidence,
    ExperienceRecord,
    ProcessingEvent,
)


class Repository(ABC):
    """实体持久化契约。所有方法使用参数化语句，不拼接 SQL。"""

    @abstractmethod
    def init_schema(self) -> None:
        """创建五张表与索引（幂等，可重复执行）。"""

    @abstractmethod
    def transaction(self) -> ContextManager[None]:
        """显式事务：成功提交，异常回滚。多实体导入必须整体处于同一事务。"""

    @abstractmethod
    def upsert_article(self, article: Article) -> None:
        """按 notice_id 插入或更新文章；重复导入不新增行。"""

    @abstractmethod
    def upsert_asset(self, asset: Asset) -> None:
        """按 asset_id 插入或更新素材；derived_guest_ref 不被覆盖。"""

    @abstractmethod
    def upsert_record(self, record: ExperienceRecord) -> None:
        """按 record_key 插入或更新人物记录；visibility 与私有字段不被导入覆盖。"""

    @abstractmethod
    def replace_evidence(self, record_key: str, items: list[Evidence]) -> None:
        """整组替换某条记录的证据；须在事务内调用。"""

    @abstractmethod
    def record_event(self, event: ProcessingEvent) -> None:
        """追加处理事件；事件是审计日志，只增不删。"""

    @abstractmethod
    def get_article(self, notice_id: str) -> Article | None:
        ...

    @abstractmethod
    def get_record(self, record_key: str) -> ExperienceRecord | None:
        ...

    @abstractmethod
    def list_records(self, visibility: str | None = None) -> list[ExperienceRecord]:
        """按可见性筛选记录；visibility=None 返回全部。"""

    @abstractmethod
    def list_records_for_notice(self, notice_id: str) -> list[ExperienceRecord]:
        ...

    @abstractmethod
    def list_evidence_for_record(self, record_key: str) -> list[Evidence]:
        ...

    @abstractmethod
    def list_events(self, notice_id: str | None = None) -> list[ProcessingEvent]:
        ...

    @abstractmethod
    def set_visibility(self, record_key: str, visibility: str) -> None:
        """人工复核后的发布状态变更（draft/published/withdrawn）。"""

    @abstractmethod
    def count_articles(self) -> int:
        ...

    @abstractmethod
    def count_assets(self) -> int:
        ...

    @abstractmethod
    def count_records(self) -> int:
        ...

    @abstractmethod
    def count_evidence(self) -> int:
        ...

    @abstractmethod
    def count_events(self) -> int:
        ...
