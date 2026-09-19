"""AnswerService：自然语言 → QueryPlan → 证据检索 → 带字段引用的回答。

边界（ARCHITECTURE 第 7 节 + 附录 G）：
- LLM 输入只有 UserQuery、QueryPlan、EvidencePack，不接触数据库或 SQL。
- 统计由程序计算后注入证据包。
- 每个引用必须通过 CitationValidator：引用编号必须来自证据包，越界引用按降级处理。
- 证据不足时明确返回"证据不足"并给出可复核记录，不补全未出现的信息。
- 模型未配置/调用失败/引用校验失败 → 回退规则模板，degraded=true，传统结果照常返回。
- 回答风格遵循附录 G G9：100-200 汉字，只做资料相关性、共同点和差异总结。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..domain.models import Evidence, ExperienceRecord
from ..domain.presenter import RecordPresenter
from ..domain.query_plan import QueryPlan
from ..domain.role_policy import published_only
from ..repository.base import Repository
from .llm_provider import LLMError, LLMProvider, NullProvider
from .query_parser import parse_query
from .search_service import SearchService

MAX_ANSWER_RECORDS = 5
CITATION_PATTERN = re.compile(r"\[(\d{1,2})\]")
RE_KEY_CITATION = re.compile(r"\[(portal-[A-Za-z0-9-]+)\]")


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
    def __init__(
        self,
        repository: Repository,
        search: SearchService | None = None,
        presenter: RecordPresenter | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._repo = repository
        self._search = search or SearchService(repository)
        self._presenter = presenter or RecordPresenter()
        # 显式传入则直接使用（测试注入 stub）；未传入时按环境变量自动装配
        self._llm_provider = llm_provider

    def _resolve_llm(self) -> LLMProvider | None:
        llm = self._llm_provider
        if llm is None:
            from .llm_provider import get_llm_provider

            llm = get_llm_provider()
        if isinstance(llm, NullProvider):
            return None  # 显式未配置：走模板路径，而不是"调用失败"
        return llm

    def llm_configured(self) -> bool:
        if isinstance(self._llm_provider, NullProvider):
            return False
        if self._llm_provider is not None:
            return True
        provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
        return bool(provider) and provider != "none" and bool(os.environ.get("LLM_API_KEY"))

    def answer(self, query: str, role: str) -> AnswerOutcome:
        plan, _notes = parse_query(query)
        outcome = self._search.search(plan, role)

        visibility = "published" if published_only(role) else None
        records_map: dict[str, tuple[ExperienceRecord, list[Evidence]]] = {}
        articles_map: dict[str, str] = {}
        for record, article in self._repo.list_records_with_articles(visibility):
            records_map[record.record_key] = (
                record,
                self._repo.list_evidence_for_record(record.record_key),
            )
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

        citations = self._citations_from_pack(pack)

        if not pack.packs or all(not p["evidence"] for p in pack.packs):
            return AnswerOutcome(
                answer=self._insufficient_text(plan, outcome.total),
                insufficient_evidence=True,
                degraded=not self.llm_configured(),
                degraded_reason=None if self.llm_configured() else "LLM 未配置，降级提示由规则模板生成",
                citations=[],
                records=outcome.items,
                query_plan=plan.to_dict(),
            )

        llm = self._resolve_llm()
        if llm is not None:
            try:
                result = llm.complete(
                    system_prompt=self._system_prompt(),
                    user_prompt=self._user_prompt(plan, pack),
                )
                text = result.text
            except LLMError as exc:
                text, fallback_reason = None, f"模型调用失败，已回退规则总结：{exc}"
            else:
                cited = self._validate_citations(text, pack.packs)
                if cited is None:
                    text, fallback_reason = None, "模型回答引用越界，未通过引用校验，已回退规则总结"
                else:
                    fallback_reason = None
                    citations = [c for c in citations if c["index"] in cited]
            if text is None:
                return AnswerOutcome(
                    answer=self._template(plan, pack),
                    insufficient_evidence=False,
                    degraded=True,
                    degraded_reason=fallback_reason,
                    citations=citations,
                    records=outcome.items,
                    query_plan=plan.to_dict(),
                )
            return AnswerOutcome(
                answer=text,
                insufficient_evidence=False,
                degraded=False,
                degraded_reason=None,
                citations=citations,
                records=outcome.items,
                query_plan=plan.to_dict(),
            )

        return AnswerOutcome(
            answer=self._template(plan, pack),
            insufficient_evidence=False,
            degraded=True,
            degraded_reason="LLM 未配置，当前回答由规则模板生成；传统检索不受影响",
            citations=citations,
            records=outcome.items,
            query_plan=plan.to_dict(),
        )

    # ---- 引用 ----

    def _citations_from_pack(self, pack: EvidencePack) -> list[dict]:
        citations: list[dict] = []
        for index, item in enumerate(pack.packs, start=1):
            if not item["evidence"]:
                continue
            evidence = item["evidence"][0]
            citations.append({
                "index": index,
                "record_key": item["record_key"],
                "field": evidence["field"],
                "text": evidence["text"],
                "source_url": item["source_url"],
                "review_status": item["review_status"],
            })
        return citations

    @staticmethod
    def _validate_citations(text: str, packs: list[dict]) -> set[int] | None:
        """CitationValidator：回答中的引用必须落在证据包内。

        接受两种形式并归一化为序号：[数字]（引用序号）与 [record_key]（记录键）。
        合法返回引用序号集合；存在越界引用或完全没有引用返回 None（触发降级）。
        """
        key_to_index = {p["record_key"]: i + 1 for i, p in enumerate(packs)}
        cited: set[int] = set()
        for m in CITATION_PATTERN.findall(text):
            n = int(m)
            if not 1 <= n <= len(packs):
                return None
            cited.add(n)
        for raw in RE_KEY_CITATION.findall(text):
            if raw not in key_to_index:
                return None
            cited.add(key_to_index[raw])
        if not cited:
            return None  # 没有任何引用同样不通过：每个结论必须可检查
        return cited

    # ---- Prompt ----

    def _system_prompt(self) -> str:
        return (
            "你是校园选调信息检索系统的回答组件。你只能依据用户消息中 JSON 证据包里的内容回答，"
            "不得使用证据包之外的任何知识，不得推测或补全缺失字段。"
            "回答为 100-200 个汉字；只做资料相关性、共同点和差异总结；"
            "不得生成'你应该去哪里'、录取概率、个人能力或价值排序。"
            "每个事实性结论后面必须紧跟方括号数字引用，例如 [1]；"
            "方括号里只能写证据包中记录的'引用序号'数字，不要写 record_key，不要编造序号。"
            "没有证据支持的内容不要写。直接输出回答正文，不要输出标题或客套话。"
        )

    def _user_prompt(self, plan: QueryPlan, pack: EvidencePack) -> str:
        import json

        payload = {
            "query": plan.to_dict(),
            "records": [
                {
                    "引用序号": index,
                    "record_key": item["record_key"],
                    "复核状态": item["review_status"],
                    "字段": item["fields"],
                    "字段证据": item["evidence"],
                }
                for index, item in enumerate(pack.packs, start=1)
            ],
            "程序统计": pack.computed_statistics,
        }
        return (
            f"用户查询条件：{json.dumps(pack.structured_conditions, ensure_ascii=False)}\n"
            f"证据包（引用时只使用其中记录的'引用序号'）：\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=1)}"
        )

    # ---- 模板回退 ----

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

    def _template(self, plan: QueryPlan, pack: EvidencePack) -> str:
        """模板化回答：只陈述证据包里出现的内容，每句带可检查的引用。"""
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
            if not item["evidence"]:
                continue
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
        return answer
