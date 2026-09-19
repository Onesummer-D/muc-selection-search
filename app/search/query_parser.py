"""规则查询解析器：自然语言 → 白名单 QueryPlan。

第一周不接入 LLM（附录 G6/G7：自然语言查询走白名单 QueryPlan、结构化/FTS5/LIKE
检索和可选 LLM 带引用总结）。本解析器是确定性的规则实现，也是模型不可用时的
降级路径（source="rule"，degraded 语义见 answer_service）。

只产出 QueryPlan 白名单字段，绝不生成 SQL。
"""

from __future__ import annotations

import re

from ..domain.query_plan import QueryPlan

_EDUCATION_PATTERNS = [
    (re.compile(r"博士"), "博士"),
    (re.compile(r"硕士|研究生"), "硕士"),
    (re.compile(r"本科|学士"), "本科"),
]
_COHORT_PATTERN = re.compile(r"(20\d{2})\s*届?")
_GEO_KEYWORDS = [
    "成都", "重庆", "西安", "昆明", "贵阳", "南宁", "兰州", "乌鲁木齐",
    "西宁", "银川", "呼和浩特", "拉萨", "绵阳", "德阳", "宜宾", "泸州",
    "四川", "陕西", "云南", "贵州", "广西", "甘肃", "青海", "宁夏",
    "新疆", "内蒙古", "西藏", "西部", "基层",
]
_MAJOR_KEYWORDS = [
    "计算机科学与技术", "计算机", "软件工程", "软件", "电子信息", "电子",
    "法学", "金融", "会计", "机械", "土木", "汉语言文学", "新闻", "经济学",
]
_GRASSROOTS_PATTERN = re.compile(r"基层|乡镇|驻村|选调生")
_SPLIT_PATTERN = re.compile(r"[，,。；;、\s！!？?？]+")
# 意图/请求类停用词：不是检索条件，混进 keywords 会造成过度过滤
_STOPWORDS = (
    "想看", "想要", "想了解", "想找", "看看", "了解一下", "求", "找一下",
    "推荐", "案例", "经验", "分享", "帖子", "相关", "情况", "资料", "学长", "学姐",
)


def parse_query(query: str) -> tuple[QueryPlan, list[str]]:
    """解析自然语言，返回 (QueryPlan, 命中说明列表)。纯函数，无副作用。"""
    text = (query or "").strip()
    plan = QueryPlan()
    notes: list[str] = []
    if not text:
        return plan, notes

    for pattern, value in _EDUCATION_PATTERNS:
        if pattern.search(text):
            plan.education = value
            notes.append(f"学历：{value}")
            break

    cohort = _COHORT_PATTERN.search(text)
    if cohort:
        plan.cohort = f"{cohort.group(1)}届"
        notes.append(f"届别：{plan.cohort}")

    for keyword in _GEO_KEYWORDS:
        if keyword in text:
            plan.city = keyword
            notes.append(f"地区：{keyword}")
            break

    for keyword in _MAJOR_KEYWORDS:
        if keyword in text:
            plan.major = keyword
            notes.append(f"专业：{keyword}")
            break

    if _GRASSROOTS_PATTERN.search(text):
        plan.position_or_unit = "基层"
        notes.append("岗位：基层")

    covered = [plan.education or "", plan.cohort or "", plan.city or "",
               plan.major or "", plan.position_or_unit or ""]
    remainder = text
    for value in covered:
        if value:
            remainder = remainder.replace(value, " ")
    for stopword in _STOPWORDS:
        remainder = remainder.replace(stopword, " ")
    tokens = [t for t in _SPLIT_PATTERN.split(remainder)
              if len(t) >= 2 and not re.fullmatch(r"20\d{2}", t)]
    plan.keywords = tokens[:5]
    if plan.keywords:
        notes.append(f"关键词：{'、'.join(plan.keywords)}")
    return plan, notes
