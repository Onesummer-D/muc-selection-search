"""海报版面规则：OCR 文本框 -> 人物记录。

分段策略 v2（PR #5 复核意见驱动，修三类缺陷）：
1. 按纵坐标把文本框聚成"行"，行内按 x 排序拼接；
2. 以「20XX届」所在行作为人物块起点切分（修复过切分/少切分）；
3. 每个人物块内：字段抽取在"块内拼接文本"上做（修复 OCR 换行截断，
   如"新闻与传播专/业硕士"），单位行取「试用期公务员」前一行的原文；
4. 页眉（首个届别行之前）与页脚（扫码/腾讯会议等）不参与抽取；
5. 无届别行时回退旧锚点分组；乱码块无核心字段命中则不生成记录。
"""

from __future__ import annotations

import re

from . import fields as F
from .rules import FieldResult

_COHORT_RE = F.COHORT_RE
_GRADE_RE = re.compile(r"(20\d{2})\s*级")
# 城市扫描：起点排除 OCR 项目符号噪声字符（米/木/点）
_CITY_SCAN_RE = re.compile(r"((?:(?![米木·])[一-龥]){1,6}?(?:市|盟|地区))")
_LAST_COUNTY_RE = re.compile(r"([一-龥]{2,6}县)")
_NOISE_LEADING_RE = re.compile(r"^[米木·]+")
_MAJOR_SUFFIX_RE = re.compile(r"(?<![:：])([\u4e00-\u9fa5（）()]{2,14})专业")
_GRADE_PREFIX_RE = re.compile(r"^\d{0,4}级?")
_FOOTER_RE = re.compile(r"扫码|腾讯会议|二维码|招生就业工作处|报名|通知群")
_TRIAL_RE = re.compile(r"试用期")


def _y_center(b):
    return (b.bbox[1] + b.bbox[3]) / 2


def _to_lines(boxes):
    """按 y 中心聚行；返回 [[box,...]]（行内按 x 排序）。"""
    if not boxes:
        return []
    items = sorted(boxes, key=lambda b: (_y_center(b), b.bbox[0]))
    heights = [b.bbox[3] - b.bbox[1] for b in items]
    med_h = sorted(heights)[len(heights) // 2] or 1.0
    lines: list[list] = [[items[0]]]
    for prev, cur in zip(items, items[1:]):
        if _y_center(cur) - _y_center(prev) > med_h * 0.6:
            lines.append([cur])
        else:
            lines[-1].append(cur)
    return [sorted(line, key=lambda b: b.bbox[0]) for line in lines]


def _line_text(line) -> str:
    return F.normalize("".join(b.text for b in line))


def split_person_blocks(boxes):
    """按届别行切人物块；返回 [(line_texts, block_boxes)]。

    line_texts 为该人物块的行文本（已归一、页脚已截断、姓名徽章行已丢弃）。
    """
    lines = _to_lines(boxes)
    texts = [_line_text(l) for l in lines]
    cohort_idx = [i for i, t in enumerate(texts) if _COHORT_RE.search(t)]

    def to_block(idxs):
        kept = [i for i in idxs if not _FOOTER_RE.search(texts[i])]
        # 试用期行之后的内容（下一位人物的姓名徽章）不参与本块
        trial = [i for i in kept if _TRIAL_RE.search(texts[i])]
        if trial:
            kept = [i for i in kept if i <= trial[-1]]
        if not kept:
            return None
        block_boxes = [b for i in kept for b in lines[i]]
        return [texts[i] for i in kept], block_boxes

    if cohort_idx:
        blocks = []
        for n, start in enumerate(cohort_idx):
            end = cohort_idx[n + 1] if n + 1 < len(cohort_idx) else len(texts)
            blk = to_block(list(range(start, end)))
            if blk:
                blocks.append(blk)
        return blocks

    # 回退：无届别行时按旧锚点分组（姓名/学历/届别词起块）
    _ANCHOR_RE = re.compile(r"姓名\s*[:：]|" + "|".join(F.EDUCATION_TERMS))
    med_h = sorted(b.bbox[3] - b.bbox[1] for b in boxes)[len(boxes) // 2] or 1.0
    ordered = sorted(boxes, key=lambda b: (_y_center(b), b.bbox[0]))
    blocks: list[list] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        anchored = bool(_ANCHOR_RE.search(F.normalize(cur.text))) \
            or bool(_COHORT_RE.search(F.normalize(cur.text)))
        if _y_center(cur) - _y_center(prev) > med_h * 1.6 and anchored:
            blocks.append([cur])
        else:
            blocks[-1].append(cur)
    out = []
    for blk in blocks:
        blk_lines = _to_lines(blk)
        kept = [(i, t) for i, t in enumerate(_line_text(l) for l in blk_lines)
                if not _FOOTER_RE.search(t)]
        if kept:
            out.append(([t for _, t in kept],
                        [b for i, _ in kept for b in blk_lines[i]]))
    return out


def _unique_term(term_list, text):
    """词典命中：唯一值返回，多值视为冲突候选。"""
    return sorted({t for t in term_list if t in text})


def _geo_city(raw: str) -> str:
    """「XX市/盟/地区」归一：剥省/自治区前缀与后缀（保定市→保定）。

    注意不剥「州」——荆州/兰州/郑州等本身是市名。
    """
    raw = raw.split("省")[-1].split("自治区")[-1]
    for suffix in ("地区", "盟", "市", "县"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            return raw[: -len(suffix)]
    return raw


def _unit_value(line: str) -> str | None:
    """从单位行取岗位/单位值：录用句式优先，否则机构后缀+左侧连续汉字。"""
    for pat in F.POSITION_PATTERNS:
        m = pat.search(line)
        if m and m.group(1).strip():
            return m.group(1).strip()
    best = None
    for m in F.UNIT_SUFFIX_RE.finditer(line):
        start = m.start()
        run_start = start
        limit = max(0, start - 14)
        while run_start > limit and re.match(r"[\u4e00-\u9fa5（）()]",
                                             line[run_start - 1]):
            run_start -= 1
        value = line[run_start:m.end()]
        if best is None or len(value) > len(best):
            best = value
    return best


def extract_person_fields(line_texts):
    """在人物块的行文本上抽七字段（grade/college 照实抽取）。

    单位行定位：试用期行前一行优先；多行含机构后缀且无试用期行 →
    视为冲突（不擅自选）。城市取单位行/块内最后一个「XX市」级匹配。
    返回 (fields: dict[str, FieldResult], field_lines: {field: line_text})。
    """
    joined = "".join(line_texts)
    res: dict[str, FieldResult] = {f: FieldResult() for f in
                                   ("cohort", "grade", "education", "college",
                                    "major", "city", "position_or_unit")}
    src_line: dict[str, str] = {}

    def set_value(f, value, line, conf=0.9):
        res[f] = FieldResult(value=value, confidence=conf,
                             evidence=[{"text": line}])
        src_line[f] = line

    # 届别 / 年级
    m = _COHORT_RE.search(joined)
    if m:
        line = next((t for t in line_texts if _COHORT_RE.search(t)), joined)
        set_value("cohort", f"{m.group(1)}届", line, 0.95)
    m = _GRADE_RE.search(joined)
    if m:
        line = next((t for t in line_texts if _GRADE_RE.search(t)), joined)
        set_value("grade", m.group(1), line, 0.85)

    # 学历（最长命中：硕士研究生 优先于 硕士；裸「研究生」按硕士研究生）
    edu = None
    for term in F.EDUCATION_TERMS_BY_LEN:
        if term in joined:
            edu = term
            break
    if edu is None and F.BARE_GRADUATE_RE.search(joined):
        edu = "硕士研究生"
    if edu is not None:
        set_value("education", edu,
                  next((t for t in line_texts if edu in t), joined), 0.92)

    # 学院（唯一词典命中）
    hits = _unique_term(F.COLLEGE_TERMS, joined)
    if len(hits) == 1:
        set_value("college", hits[0],
                  next((t for t in line_texts if hits[0] in t), joined), 0.9)
    elif len(hits) > 1:
        res["college"] = FieldResult(confidence=0.0, conflict=True,
                                     evidence=[{"text": t} for t in line_texts
                                               if any(h in t for h in hits)])

    # 专业：「XX专业」模式优先（含全角括号，剥年级前缀），词典兜底
    m = _MAJOR_SUFFIX_RE.search(joined)
    if m:
        value = _GRADE_PREFIX_RE.sub("", m.group(1))
        value = _NOISE_LEADING_RE.sub("", value)  # OCR 项目符号噪声（米/木）
        line = next((t for t in line_texts if "专业" in t), joined)
        set_value("major", value, line, 0.9)
    else:
        hits = _unique_term(F.MAJOR_TERMS, joined)
        if len(hits) == 1:
            set_value("major", hits[0],
                      next((t for t in line_texts if hits[0] in t), joined), 0.85)
        elif len(hits) > 1:
            res["major"] = FieldResult(confidence=0.0, conflict=True,
                                       evidence=[{"text": t} for t in line_texts
                                                 if any(h in t for h in hits)])

    # 单位行定位
    trial_idx = [i for i, t in enumerate(line_texts) if _TRIAL_RE.search(t)]
    unit_lines = [t for t in line_texts
                  if F.UNIT_SUFFIX_RE.search(t)
                  or any(p.search(t) for p in F.POSITION_PATTERNS)]
    unit_line = None
    unit_conflict = False
    if trial_idx and trial_idx[0] > 0:
        unit_line = line_texts[trial_idx[0] - 1]
    elif len(unit_lines) == 1:
        unit_line = unit_lines[0]
    elif len(unit_lines) > 1:
        # 多候选：入职/录用/考取 行优先（gold 口径=录用单位）；
        # 恰有一条带标记则消歧，否则冲突
        marked = [t for t in unit_lines
                  if re.search(r"入职|录用|考取", t)]
        if len(marked) == 1:
            unit_line = marked[0]
        else:
            unit_conflict = True

    # 城市：单位行（或整块）内最后一个「XX市」级匹配；多单位行 → 冲突
    if unit_conflict:
        res["city"] = FieldResult(confidence=0.0, conflict=True,
                                  evidence=[{"text": t} for t in unit_lines])
        res["position_or_unit"] = FieldResult(
            confidence=0.0, conflict=True,
            evidence=[{"text": t} for t in unit_lines])
    else:
        scope = unit_line or joined
        value = None
        # 规则1：工作地点/任职地点标签后紧跟的城市（按行搜索，行即终止符）；
        # 多个不同值 → 冲突
        label_hits = [m.group(1) for lt in line_texts for m in re.finditer(
            r"(?:工作地点|任职地点|录用地点)[：:]"
            r"([\u4e00-\u9fa5]{2,8}?)(?=市|区|县|州|盟|地区|，|,|录用|任职|$)",
            lt)]
        if len(set(label_hits)) == 1:
            value = label_hits[0]
        elif len(set(label_hits)) > 1:
            res["city"] = FieldResult(
                confidence=0.0, conflict=True,
                evidence=[{"text": t} for t in line_texts
                          if any(h in t for h in label_hits)])
        if value is None and not res["city"].conflict:
            # 规则2：动词短语打断后，最后一个市级匹配（最具体，如 泉州市晋江市→晋江）
            scope2 = re.sub(r"(?:录用为|考取|考录|任职于|任命为|聘任为)", "，", scope)
            hits = [_geo_city(m.group(1))
                    for m in _CITY_SCAN_RE.finditer(scope2)]
            hits = [c for c in hits if c]
            if hits:
                value = hits[-1]
            elif scope is not joined:
                # 规则3：单位行无市级地名 → 整块回退（「XX市」在入职行），
                # 仍无再县级回退（石阡县→石阡）
                hits = [_geo_city(m.group(1))
                        for m in _CITY_SCAN_RE.finditer(joined)]
                hits = [c for c in hits if c]
                if hits:
                    value = hits[-1]
                else:
                    m = _LAST_COUNTY_RE.search(joined)
                    if m:
                        value = _geo_city(m.group(1))
        if value is None and unit_line is None:
            # 无单位行时按行找城市词典命中，跨行不同值视为冲突
            per_line = sorted({t for t in F.CITY_TERMS
                               for lt in line_texts if t in lt})
            if len(per_line) == 1:
                value = per_line[0]
            elif len(per_line) > 1:
                res["city"] = FieldResult(
                    confidence=0.0, conflict=True,
                    evidence=[{"text": lt} for lt in line_texts
                              if any(t in lt for t in per_line)])
        if value is not None:
            set_value("city", value, unit_line or joined, 0.85)

        # 岗位或单位：录用句式捕获优先，否则单位行原文（判定侧剥任职尾巴）
        if unit_line:
            pv = _unit_value(unit_line) or unit_line
            set_value("position_or_unit", pv, unit_line, 0.85)

    return res, src_line


def records_from_boxes(notice_id: str, page, start_index: int = 0):
    """一页 OCR 结果 -> 人物记录列表（method=ocr_rule，证据带 bbox）。"""
    from .extractor import CORE_FIELDS, _build_record

    records = []
    for offset, (line_texts, block_boxes) in enumerate(
            split_person_blocks(boxes=page.boxes)):
        results, src_line = extract_person_fields(line_texts)
        if not any(results[f].value for f in CORE_FIELDS):
            continue
        union = [
            min(b.bbox[0] for b in block_boxes),
            min(b.bbox[1] for b in block_boxes),
            max(b.bbox[2] for b in block_boxes),
            max(b.bbox[3] for b in block_boxes),
        ]
        ocr_conf = min(b.confidence for b in block_boxes) \
            if block_boxes else 0.9

        record = {
            "record_key": f"{notice_id}-{start_index + offset + 1:02d}",
            **{f: results[f].value for f in
               ("cohort", "grade", "education", "college", "major",
                "city", "position_or_unit")},
            "review_status": "processed",
            "confidence": round(min(
                (results[f].confidence for f in CORE_FIELDS
                 if results[f].value is not None), default=0.9)
                * min(1.0, ocr_conf / 0.9), 2),
            "evidence": [],
        }
        # 证据：有值字段或冲突字段都引用来源行（冲突候选必须可追溯）
        for f in ("cohort", "grade", "education", "college", "major",
                  "city", "position_or_unit"):
            if record[f] is None and not results[f].conflict:
                continue
            line = src_line.get(f, "".join(line_texts))
            line_boxes = [b for b in block_boxes
                          if F.normalize(b.text) and F.normalize(b.text) in line] \
                or block_boxes
            lb = [
                min(b.bbox[0] for b in line_boxes),
                min(b.bbox[1] for b in line_boxes),
                max(b.bbox[2] for b in line_boxes),
                max(b.bbox[3] for b in line_boxes),
            ]
            record["evidence"].append({
                "field": f, "text": line, "method": "ocr_rule",
                "asset_id": page.asset_id, "bbox": lb,
            })

        # 复核判定：核心字段缺失 / 冲突 / 低置信度
        missing = any(record[f] is None for f in CORE_FIELDS)
        conflict = any(results[f].conflict for f in results)
        low = record["confidence"] < 0.60
        if missing or conflict or low:
            record["review_status"] = "review_required"
        records.append(record)
    return records
