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


def box_field_results(boxes) -> dict[str, FieldResult]:
    """在一组文本框上抽七个字段（grade 本周规则不抽取，恒 null）。"""
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
    pos_hits = []
    for pat in F.POSITION_PATTERNS:
        for b in boxes:
            m = pat.search(F.normalize(b.text))
            if m and m.group(1).strip():
                pos_hits.append((m.group(1).strip(), b))
    out["position_or_unit"] = _resolve_position(pos_hits)
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
