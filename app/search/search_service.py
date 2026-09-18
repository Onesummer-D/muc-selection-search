"""SearchService：结构化过滤 + FTS5/LIKE 关键词召回 + 可解释排序。

排序权重（附录 G G9）：专业 5、地区/城市 4、单位/岗位 4、学院 4、学历 3、届别 2；
同分按证据完整度、发布时间排序。用户显式条件是硬过滤，不自动放宽；
无结果时返回逐项放宽候选（由用户确认后重查）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.models import Article, ExperienceRecord
from ..domain.presenter import RecordPresenter
from ..domain.query_plan import FIELD_LABELS_ZH, QueryPlan
from ..domain.role_policy import published_only
from ..repository.base import Repository

STRUCTURED_WEIGHTS: dict[str, int] = {
    "major": 5,
    "city": 4,
    "position_or_unit": 4,
    "college": 4,
    "education": 3,
    "cohort": 2,
}
KEYWORD_HIT_WEIGHT = 2
# 精确匹配字段与包含匹配字段的语义划分（match_reason 里如实呈现）
EXACT_FIELDS = ("education", "cohort")
CONTAINS_FIELDS = ("college", "major", "city", "position_or_unit")

# 地区别名组：解析器可能产出省级行政区或大区词（如"西部"），
# 而记录的 city 存的是具体城市；匹配时按别名组展开，保证省份/大区查询可召回
REGION_ALIASES: dict[str, frozenset[str]] = {
    "西部": frozenset({
        "成都", "重庆", "西安", "昆明", "贵阳", "南宁", "兰州", "乌鲁木齐",
        "西宁", "银川", "呼和浩特", "拉萨", "绵阳", "德阳", "宜宾", "泸州",
    }),
    "四川": frozenset({"成都", "绵阳", "德阳", "宜宾", "泸州"}),
    "陕西": frozenset({"西安"}),
    "云南": frozenset({"昆明"}),
    "贵州": frozenset({"贵阳"}),
    "广西": frozenset({"南宁"}),
    "甘肃": frozenset({"兰州"}),
}


@dataclass
class SearchOutcome:
    """一次检索的完整结果，供 API 层直接序列化。"""

    plan: QueryPlan
    total: int = 0
    page: int = 1
    page_size: int = 10
    items: list[dict] = field(default_factory=list)
    relaxations: list[dict] = field(default_factory=list)
    empty_plan: bool = False


def _normalized(value: str | None) -> str:
    return (value or "").strip().casefold()


def _field_matches(field_name: str, condition: str, record_value: str | None) -> bool:
    record_value = _normalized(record_value)
    condition = _normalized(condition)
    if not record_value:
        return False
    if field_name in EXACT_FIELDS:
        return record_value == condition
    if field_name == "city" and condition in REGION_ALIASES:
        return record_value in {c.casefold() for c in REGION_ALIASES[condition]}
    return condition in record_value or record_value in condition


class SearchService:
    """传统检索主链。AI/降级路径与本服务共享同一套可见性与证据链。"""

    def __init__(self, repository: Repository, presenter: RecordPresenter | None = None) -> None:
        self._repo = repository
        self._presenter = presenter or RecordPresenter()

    def search(self, plan: QueryPlan, role: str) -> SearchOutcome:
        visibility = "published" if published_only(role) else None
        candidates = self._repo.list_records_with_articles(visibility)
        evidence_counts = self._repo.count_evidence_by_record()

        keyword_hit_notices: set[str] | None = None
        if plan.keywords:
            keyword_hit_notices = self._repo.find_notice_ids_by_keywords(plan.keywords)

        scored: list[tuple[int, list[dict], ExperienceRecord, Article]] = []
        for record, article in candidates:
            reasons: list[dict] = []
            failed_condition = False
            for field_name, condition in plan.structured_conditions().items():
                record_value = getattr(record, field_name)
                if _field_matches(field_name, condition, record_value):
                    weight = STRUCTURED_WEIGHTS.get(field_name, 1)
                    reasons.append({
                        "field": field_name,
                        "label": f"{FIELD_LABELS_ZH[field_name]}匹配：{condition}",
                        "weight": weight,
                    })
                else:
                    failed_condition = True
                    break
            if failed_condition:
                continue

            keyword_hits = 0
            if plan.keywords:
                assert keyword_hit_notices is not None
                record_text = " ".join(
                    filter(None, (getattr(record, f) for f in CONTAINS_FIELDS))
                )
                article_text = f"{article.title} {article.clean_text or ''}"
                for keyword in plan.keywords:
                    if (article.notice_id in keyword_hit_notices
                            or keyword in article_text or keyword in record_text):
                        keyword_hits += 1
                if keyword_hits == 0:
                    continue
                reasons.append({
                    "field": "keywords",
                    "label": f"关键词命中 {keyword_hits} 项：{'、'.join(plan.keywords)}",
                    "weight": keyword_hits * KEYWORD_HIT_WEIGHT,
                })

            score = sum(r["weight"] for r in reasons)
            scored.append((score, reasons, record, article))

        # 排序：匹配分 → 证据完整度 → 发布时间
        scored.sort(
            key=lambda item: (
                item[0],
                evidence_counts.get(item[2].record_key, 0),
                _normalized(item[3].published_at or ""),
            ),
            reverse=True,
        )

        outcome = SearchOutcome(
            plan=plan,
            total=len(scored),
            page=plan.page,
            page_size=plan.page_size,
            empty_plan=plan.is_empty(),
        )
        start = (plan.page - 1) * plan.page_size
        for score, reasons, record, article in scored[start:start + plan.page_size]:
            dto = self._presenter.present_summary(record, article, role)
            dto["score"] = score
            dto["match_reasons"] = reasons
            dto["evidence_count"] = evidence_counts.get(record.record_key, 0)
            outcome.items.append(dto)

        if not scored and not plan.is_empty():
            outcome.relaxations = self._relaxations(plan, candidates)
        return outcome

    def _relaxations(
        self,
        plan: QueryPlan,
        candidates: list[tuple[ExperienceRecord, Article]],
    ) -> list[dict]:
        """逐项放宽候选：去掉一个条件后能命中的记录数，供用户选择。"""
        offers: list[dict] = []
        droppable = list(plan.structured_conditions().items())
        if plan.keywords:
            droppable.append(("keywords", " ".join(plan.keywords)))
        for field_name, condition in droppable:
            remaining = {f: c for f, c in plan.structured_conditions().items() if f != field_name}
            count = 0
            for record, _article in candidates:
                # 放宽 = 去掉该条件后只检查剩余条件；keywords 同理不再要求命中
                if all(
                    _field_matches(f, c, getattr(record, f)) for f, c in remaining.items()
                ):
                    count += 1
            if count > 0:
                offers.append({
                    "field": field_name,
                    "label": FIELD_LABELS_ZH.get(field_name, field_name),
                    "removed_condition": condition,
                    "match_count": count,
                })
        offers.sort(key=lambda item: -item["match_count"])
        return offers
