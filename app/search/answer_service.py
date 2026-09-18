"""AnswerService：自然语言 → QueryPlan → 证据检索 → 带字段引用的回答。

边界（ARCHITECTURE 第 7 节 + 附录 G）：
- 输入只有查询与证据包，不直接访问数据库或生成 SQL。
- 统计由程序计算后注入证据包。
- 证据不足时明确返回"证据不足"并给出可复核记录，不补全未出现的信息。
- 第一周不接入 LLM：回答由规则模板生成（100-200 汉字）；LLM 未配置时
  degraded=true，传统检索结果照常返回。任务3 接入可插拔 LLM 后替换生成器。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..domain.models import Evidence, ExperienceRecord
from ..domain.presenter import RecordPresenter
from ..domain.query_plan import QueryPlan
from ..domain.role_policy import published_only
from ..repository.base import Repository
from .query_parser import parse_query
from .search_service import SearchService

MAX_ANSWER_RECORDS = 5


@dataclass
class EvidencePack:
    """受控输入：只包含当前查询允许使用的记录、字段证据与程序统计。"""

    query_plan: dict
    structured_conditions: dict
    packs: list[dict] = field(default_factory=list)
    computed_statistics: dict = field(default_factory=dict)


@dataclass
class AnswerOutcome:
    answer: str
    insufficient_evidence: bool
    degraded: bool
    degraded_reason: str | None
    citations: list[dict]
    records: list[dict]
    query_plan: dict


class AnswerService:
    def __init__(self, repository: Repository, search: SearchService | None = None,
                 presenter: RecordPresenter | None = None) -> None:
        self._repo = repository
        self._search = search or SearchService(repository)
        self._presenter = presenter or RecordPresenter()

    def llm_configured(self) -> bool:
        return bool(os.environ.get("LLM_PROVIDER")) and bool(os.environ.get("LLM_API_KEY"))

    def answer(self, query: str, role: str) -> AnswerOutcome:
        plan, _notes = parse_query(query)
        outcome = self._search.search(plan, role)

        visibility = "published" if published_only(role) else None
        records_map: dict[str, tuple[ExperienceRecord, list[Evidence]]] = {}
        articles_map: dict[str, str] = {}
        for record, article in self._repo.list_records_with_articles(visibility):
            records_map[record.record_key] = (record, self._repo.list_evidence_for_record(record.record_key))
            articles_map[record.record_key] = article.source_url

        pack = EvidencePack(
            query_plan=plan.to_dict(),
            structured_conditions=plan.structured_conditions(),
        )
        for item in outcome.items[:MAX_ANSWER_RECORDS]:
            record, evidence = records_map[item["record_key"]]
            pack.packs.append({
                "record_key": record.record_key,
                "notice_id": record.notice_id,
                "review_status": record.review_status,
                "source_url": articles_map.get(record.record_key),
                "fields": item["fields"],
                "evidence": [
                    {"field": e.field, "text": e.text, "method": e.method}
                    for e in evidence
                ],
            })
        cities = [p["fields"]["city"] for p in pack.packs if p["fields"]["city"]]
        pack.computed_statistics = {
            "matched_total": outcome.total,
            "listed_records": len(pack.packs),
            "city_distribution": {
                city: cities.count(city) for city in sorted(set(cities))
            },
        }

        degraded = not self.llm_configured()
        degraded_reason = None if not degraded else (
            "LLM 未配置，当前回答由规则模板生成；传统检索不受影响"
        )

        if not pack.packs or all(not p["evidence"] for p in pack.packs):
            return AnswerOutcome(
                answer=self._insufficient_text(plan, outcome.total),
                insufficient_evidence=True,
                degraded=degraded,
                degraded_reason=degraded_reason,
                citations=[],
                records=outcome.items,
                query_plan=plan.to_dict(),
            )

        answer_text, citations = self._compose(plan, pack)
        return AnswerOutcome(
            answer=answer_text,
            insufficient_evidence=False,
            degraded=degraded,
            degraded_reason=degraded_reason,
            citations=citations,
            records=outcome.items,
            query_plan=plan.to_dict(),
        )

    # ---- 内部 ----

    def _insufficient_text(self, plan: QueryPlan, total: int) -> str:
        if total == 0:
            return (
                "证据不足：没有找到满足当前条件的已发布记录。"
                "你可以在结果页逐项放宽条件后重新检索，或查看最新收录的记录。"
            )
        return (
            "证据不足：虽然找到已发布记录，但缺少可引用的字段级证据。"
            "以下结果仅供人工复核，不作为结论引用。"
        )

    def _compose(self, plan: QueryPlan, pack: EvidencePack) -> tuple[str, list[dict]]:
        """模板化回答：只陈述证据包里出现的内容，每句带可检查的引用。"""
        citations: list[dict] = []
        parts: list[str] = []
        stats = pack.computed_statistics
        intro = f"共匹配到 {stats['matched_total']} 条已发布记录"
        if plan.structured_conditions():
            conditions = "、".join(
                f"{v}" for v in plan.structured_conditions().values()
            )
            intro += f"（条件：{conditions}）"
        parts.append(intro + "。")

        city_line = "；".join(
            f"{city} {count} 条" for city, count in stats["city_distribution"].items()
        )
        if city_line:
            parts.append(f"工作地点分布：{city_line}")

        for index, item in enumerate(pack.packs, start=1):
            evidence = item["evidence"][0]
            citations.append({
                "index": index,
                "record_key": item["record_key"],
                "field": evidence["field"],
                "text": evidence["text"],
                "source_url": item["source_url"],
                "review_status": item["review_status"],
            })
            fields = item["fields"]
            summary = "，".join(
                f"{label}{fields[key]}"
                for key, label in (
                    ("education", "学历"), ("major", "专业"),
                    ("city", "去向"), ("position_or_unit", "岗位"),
                ) if fields.get(key)
            )
            if summary:
                parts.append(f"[{index}] {item['record_key']}：{summary}。")

        answer = "".join(parts)
        if len(answer) > 200:
            answer = answer[:197] + "…"
        return answer, citations
