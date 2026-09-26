"""html_rule 文本规则抽取。

输入归一化后的正文，输出每个字段的结果：
value（非空才可信）、confidence、evidence 片段列表。
规则没有证据时不得返回非空值；命中多个冲突值时保留候选、值置 null。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import fields as F


@dataclass
class FieldResult:
    value: str | None = None
    confidence: float = 0.0
    evidence: list[dict] = field(default_factory=list)  # {"text": ...}
    conflict: bool = False


def _unique_hits(term_list, text):
    """返回 [(value, start, end)]，同名术语多次出现只保留第一处。"""
    hits = []
    for term in term_list:
        idx = text.find(term)
        if idx >= 0:
            hits.append((term, idx, idx + len(term)))
    hits.sort(key=lambda h: h[1])
    return hits


def _resolve(hits, context_of=F.context_of, text="") -> FieldResult:
    """单值直接取；多个不同值视为冲突，保留全部候选证据、值置 null。"""
    if not hits:
        return FieldResult()
    values = sorted({h[0] for h in hits})
    ev = [
        {"text": context_of(text, s, e)}
        for _, s, e in hits
    ]
    if len(values) == 1:
        return FieldResult(value=values[0], confidence=0.92, evidence=ev)
    # 冲突：保留候选，不擅自选
    return FieldResult(value=None, confidence=0.0, evidence=ev, conflict=True)


def extract_from_text(raw_text: str) -> dict[str, FieldResult]:
    """对一篇文本正文按字段词典抽取。"""
    text = F.normalize(raw_text)
    out: dict[str, FieldResult] = {}

    # 届别：只认「20XX届」，避免把发布日期当届别
    m = F.COHORT_RE.search(text)
    out["cohort"] = (
        FieldResult(value=f"{m.group(1)}届", confidence=0.95,
                    evidence=[{"text": F.context_of(text, m.start(), m.end())}])
        if m else FieldResult()
    )

    # 学历：明确出现的词；同一词重复不冲突
    # 学历：最长命中（硕士研究生 优先于 硕士）；裸「研究生」按硕士研究生
    edu = next((t for t in F.EDUCATION_TERMS_BY_LEN if t in text), None)
    if edu is None and F.BARE_GRADUATE_RE.search(text):
        edu = "硕士研究生"
    out["education"] = (
        FieldResult(value=edu, confidence=0.92,
                    evidence=[{"text": F.context_of(text, text.find(edu),
                                               text.find(edu) + len(edu))}])
        if edu else FieldResult())

    # 学院与专业：分开记录；学院名不得顶替专业
    out["college"] = _resolve(_unique_hits(F.COLLEGE_TERMS, text), text=text)
    out["major"] = _resolve(_unique_hits(F.MAJOR_TERMS, text), text=text)

    # 城市：以工作/录用地点为准；本文本路径先取词典命中，多值即冲突
    out["city"] = _resolve(_unique_hits(F.CITY_TERMS, text), text=text)

    # 岗位或单位：上下文正则；取第一处命中，其余作为候选证据
    pos_hits = []
    for pat in F.POSITION_PATTERNS:
        for m in pat.finditer(text):
            value = m.group(1).strip()
            if value:
                pos_hits.append((value, m.start(1), m.end(1)))
    pos_hits.sort(key=lambda h: h[1])
    out["position_or_unit"] = _resolve(pos_hits, text=text)

    return out
