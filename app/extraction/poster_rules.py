"""海报版面规则：OCR 文本框 -> 人物记录。

1. 按纵向间距把文本框分成版面块（一帖多人：每人一个版面块）。
2. 块内按届别、学历、学院/专业词典、城市、岗位上下文抽字段，method=ocr_rule。
3. 单块出现多个届别且无法按块切分时，边界不清 → 整页 review_required。
"""

from __future__ import annotations

import re

from . import fields as F
from .rules import FieldResult

_COHORT_RE = F.COHORT_RE


_ANCHOR_RE = re.compile(r"姓名\s*[:：]|" + "|".join(F.EDUCATION_TERMS))


def group_blocks(boxes, gap_factor: float = 1.6):
    """把文本框聚类成版面块，返回 [[box, ...]]（按阅读顺序）。

    分块条件：与上一框的 y 中心间距超过中位框高的 gap_factor 倍，
    且新框本身带人物锚点（届别/姓名/学历）。仅有大间距的普通行
    （如「工作地点」行）跟随前块，避免把单人海报切成本人多块。
    """
    if not boxes:
        return []
    items = sorted(boxes, key=lambda b: ((b.bbox[1] + b.bbox[3]) / 2, b.bbox[0]))
    heights = [b.bbox[3] - b.bbox[1] for b in items]
    med_h = sorted(heights)[len(heights) // 2] or 1.0

    blocks: list[list] = [[items[0]]]
    for prev, cur in zip(items, items[1:]):
        prev_cy = (prev.bbox[1] + prev.bbox[3]) / 2
        cur_cy = (cur.bbox[1] + cur.bbox[3]) / 2
        anchored = bool(_ANCHOR_RE.search(F.normalize(cur.text))) \
            or bool(F.COHORT_RE.search(F.normalize(cur.text)))
        if cur_cy - prev_cy > med_h * gap_factor and anchored:
            blocks.append([cur])
        else:
            blocks[-1].append(cur)
    return blocks


def _resolve_box(term_list, boxes, prefer_context: str | None = None) -> FieldResult:
    """在文本框集合上跑词典；证据带 bbox；OCR 置信度折算进字段置信度。"""
    ctx = re.compile(prefer_context) if prefer_context else None
    hits = []
    for b in boxes:
        text = F.normalize(b.text)
        for term in term_list:
            if term in text:
                hits.append((term, b, 1 if (ctx and ctx.search(text)) else 0))
    if not hits:
        return FieldResult()
    values = sorted({h[0] for h in hits})
    evidence = [{"text": b.text, "bbox": b.bbox, "ocr_conf": b.confidence}
                for term, b, _ in hits if term in values]
    if len(values) == 1:
        ocr_conf = min(b.confidence for t, b, _ in hits if t == values[0])
        boost = max(boost for _, _, boost in hits)
        conf = round(0.92 * min(1.0, ocr_conf / 0.9) + 0.05 * boost, 2)
        return FieldResult(value=values[0], confidence=min(conf, 0.99), evidence=evidence)
    return FieldResult(value=None, confidence=0.0, evidence=evidence, conflict=True)


def _resolve_position(hits) -> FieldResult:
    if not hits:
        return FieldResult()
    values = sorted({v for v, _ in hits})
    evidence = [{"text": b.text, "bbox": b.bbox, "ocr_conf": b.confidence}
                for v, b in hits]
    if len(values) == 1:
        ocr_conf = min(b.confidence for _, b in hits)
        return FieldResult(value=values[0],
                           confidence=round(0.9 * min(1.0, ocr_conf / 0.9), 2),
                           evidence=evidence)
    return FieldResult(value=None, confidence=0.0, evidence=evidence, conflict=True)


def _pattern_hits(pattern, boxes, value_group=1):
    """按正则模式在文本框上取候选；返回 [(value, box)]。"""
    hits = []
    for b in boxes:
        m = pattern.search(F.normalize(b.text))
        if m and m.group(value_group).strip():
            hits.append((m.group(value_group).strip(), b))
    return hits


def _geo_value(raw: str) -> str:
    """城市值归一：剥省/自治区前缀，再去「市/州/盟/地区」后缀。

    山西省临汾市 → 临汾；新疆维吾尔自治区吐鲁番市 → 吐鲁番。
    """
    raw = raw.split("省")[-1].split("自治区")[-1]
    for suffix in ("地区", "盟", "州", "市"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            return raw[: -len(suffix)]
    return raw


_GRADE_PREFIX_RE = re.compile(r"^\d{0,4}级")


def _resolve_hits_with_bbox(hits, strip_grade_prefix: bool = False) -> FieldResult:
    """同值合并；唯一值给置信度，多值冲突保留候选证据。"""
    if not hits:
        return FieldResult()
    if strip_grade_prefix:  # 「2021级汉语言文字学」→「汉语言文字学」
        hits = [(_GRADE_PREFIX_RE.sub("", v), b) for v, b in hits]
    values = sorted({v for v, _ in hits})
    evidence = [{"text": b.text, "bbox": b.bbox, "ocr_conf": b.confidence}
                for v, b in hits]
    if len(values) == 1:
        ocr_conf = min(b.confidence for _, b in hits)
        return FieldResult(value=values[0],
                           confidence=round(0.85 * min(1.0, ocr_conf / 0.9), 2),
                           evidence=evidence)
    return FieldResult(value=None, confidence=0.0, evidence=evidence, conflict=True)


def box_field_results(boxes) -> dict[str, FieldResult]:
    """在一组文本框上抽七个字段（grade 本周规则不抽取，恒 null）。

    词典优先，未命中时用通用模式补（城市「XX市」、专业「XX专业」、
    机构后缀单位行），模式是海报领域的通用版式规则，非针对特定样本。
    """
    out: dict[str, FieldResult] = {
        "cohort": FieldResult(), "education": FieldResult(),
        "college": FieldResult(), "major": FieldResult(),
        "city": FieldResult(), "position_or_unit": FieldResult(),
        "grade": FieldResult(),
    }
    # 届别：只认「20XX届」
    for b in boxes:
        m = _COHORT_RE.search(F.normalize(b.text))
        if m:
            out["cohort"] = FieldResult(
                value=f"{m.group(1)}届", confidence=round(0.95 * min(1.0, b.confidence / 0.9), 2),
                evidence=[{"text": b.text, "bbox": b.bbox, "ocr_conf": b.confidence}])
            break
    out["education"] = _resolve_box(F.EDUCATION_TERMS, boxes)
    out["college"] = _resolve_box(F.COLLEGE_TERMS, boxes)
    out["major"] = _resolve_box(F.MAJOR_TERMS, boxes)
    out["city"] = _resolve_box(F.CITY_TERMS, boxes, prefer_context="工作地点|任职|录用|去向")

    # 专业模式兜底：词典未命中时取「XX专业」（剥掉「2021级」等年级前缀）
    if out["major"].value is None and not out["major"].conflict:
        out["major"] = _resolve_hits_with_bbox(
            _pattern_hits(F.MAJOR_SUFFIX_RE, boxes), strip_grade_prefix=True)

    # 城市模式兜底：词典未命中时，带机构/工作地点上下文的「XX市」行
    if out["city"].value is None and not out["city"].conflict:
        ctx_hits = []
        for b in boxes:
            if not (F.UNIT_SUFFIX_RE.search(F.normalize(b.text))
                    or re.search(r"工作地点|任职|录用|去向", F.normalize(b.text))):
                continue
            for m in F.CITY_SUFFIX_RE.finditer(F.normalize(b.text)):
                ctx_hits.append((_geo_value(m.group(1)), b))
        out["city"] = _resolve_hits_with_bbox(ctx_hits)

    # 岗位或单位：录用类句式优先；未命中时取机构后缀单位行
    pos_hits = []
    for pat in F.POSITION_PATTERNS:
        for b in boxes:
            m = pat.search(F.normalize(b.text))
            if m and m.group(1).strip():
                pos_hits.append((m.group(1).strip(), b))
    if pos_hits:
        out["position_or_unit"] = _resolve_position(pos_hits)
    else:
        out["position_or_unit"] = _resolve_hits_with_bbox(
            _pattern_hits(F.UNIT_SUFFIX_RE, boxes))
    out["grade"] = FieldResult()  # Schema 必填，规则本周不抽取，恒 null
    return out


def records_from_boxes(notice_id: str, page, start_index: int = 0):
    """一页 OCR 结果 -> 人物记录列表（method=ocr_rule，证据带 bbox）。"""
    from .extractor import _build_record

    blocks = group_blocks(page.boxes)
    cohort_blocks = sum(
        1 for block in blocks
        if any(_COHORT_RE.search(F.normalize(b.text)) for b in block))
    # 两个及以上版面块各出现届别 = 多人海报（每人一块，正常处理）；
    # 但单块内出现 ≥2 个届别且无法切分 = 边界不清。
    ambiguous = any(
        sum(len(_COHORT_RE.findall(F.normalize(b.text))) for b in block) >= 2
        for block in blocks) and len(blocks) == 1

    records = []
    record_index = start_index
    for block in blocks:
        results = box_field_results(block)
        # 纯标题/装饰块：五个核心字段全无命中，不生成人物记录
        from .extractor import CORE_FIELDS
        if not any(results[f].value for f in CORE_FIELDS) and not ambiguous:
            continue
        record = _build_record(notice_id, record_index, results,
                               method="ocr_rule", asset_id=page.asset_id)
        record_index += 1
        if ambiguous or (cohort_blocks >= 2 and len(blocks) == 1):
            record["review_status"] = "review_required"
            record["confidence"] = 0.0
        # Schema 证据对象不允许额外属性，ocr_conf 只用于内部置信度折算
        for ev in record["evidence"]:
            ev.pop("ocr_conf", None)
        records.append(record)
    return records
