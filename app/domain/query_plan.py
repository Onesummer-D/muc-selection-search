"""查询计划：白名单字段模型与解析。

QueryPlan 只允许 cohort、education、college、major、city、position_or_unit、
keywords、page、page_size（接口字典第 6 节）。模型不得生成 SQL；
任何未知字段在入口处被拒绝（返回 400），不进入检索层。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from .errors import ContractViolation

PLAN_FIELDS = ("cohort", "education", "college", "major", "city", "position_or_unit")
MAX_PAGE_SIZE = 50

# 展示用的中文字段名（无结果放宽提示用）
FIELD_LABELS_ZH: dict[str, str] = {
    "cohort": "届别",
    "education": "学历",
    "college": "学院",
    "major": "专业",
    "city": "城市",
    "position_or_unit": "岗位/单位",
    "keywords": "关键词",
}


@dataclass
class QueryPlan:
    """结构化检索计划。字符串条件为精确/包含匹配，keywords 为词元列表。"""

    cohort: str | None = None
    education: str | None = None
    college: str | None = None
    major: str | None = None
    city: str | None = None
    position_or_unit: str | None = None
    keywords: list[str] = field(default_factory=list)
    page: int = 1
    page_size: int = 10

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ContractViolation("query_plan.page: 必须大于等于 1")
        if not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise ContractViolation(
                f"query_plan.page_size: 必须在 1 到 {MAX_PAGE_SIZE} 之间"
            )
        self.keywords = [k for k in self.keywords if k]

    @classmethod
    def from_dict(cls, data: object, *, allow_empty: bool = True) -> "QueryPlan":
        """从请求体构造计划；未知字段一律拒绝。"""
        if not isinstance(data, dict):
            raise ContractViolation("query_plan: 必须是 JSON 对象")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ContractViolation(f"query_plan: 存在不允许的查询字段 {unknown}")
        kwargs: dict = {}
        for name in PLAN_FIELDS:
            value = data.get(name)
            if value is not None and not isinstance(value, str):
                raise ContractViolation(f"query_plan.{name}: 必须是字符串或 null")
            if isinstance(value, str) and not value.strip():
                value = None
            kwargs[name] = value.strip() if isinstance(value, str) else None
        if "keywords" in data:
            raw = data["keywords"]
            if not isinstance(raw, list) or not all(isinstance(k, str) for k in raw):
                raise ContractViolation("query_plan.keywords: 必须是字符串数组")
            if len(raw) > 10:
                raise ContractViolation("query_plan.keywords: 最多 10 个词元")
            kwargs["keywords"] = [k.strip() for k in raw if k.strip()]
        for name in ("page", "page_size"):
            if name in data:
                value = data[name]
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ContractViolation(f"query_plan.{name}: 必须是整数")
                kwargs[name] = value
        plan = cls(**kwargs)
        if not allow_empty and plan.is_empty():
            raise ContractViolation("query_plan: 至少需要一个条件或关键词")
        return plan

    def is_empty(self) -> bool:
        structured = any(getattr(self, name) for name in PLAN_FIELDS)
        return not structured and not self.keywords

    def structured_conditions(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in PLAN_FIELDS if getattr(self, name)}

    def to_dict(self) -> dict:
        return {
            "cohort": self.cohort,
            "education": self.education,
            "college": self.college,
            "major": self.major,
            "city": self.city,
            "position_or_unit": self.position_or_unit,
            "keywords": self.keywords,
            "page": self.page,
            "page_size": self.page_size,
        }
