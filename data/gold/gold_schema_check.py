"""20 样本金标准格式校验（对齐验收台账 P1-03 整改后的机器校验）。

规则：
- 样本 ID 固定为 P01–P20，两条路线共用同一集合；
- sha256 必须是 64 位十六进制；
- 学历 ∈ {本科, 硕士, 博士} 或 null；
- cohort 为 null 或「20XX届」；
- 五个核心字段缺失一律 null，不允许空字符串或占位值；
- 标注人必填（匿名 ID，如 B-annotator-1），金标准必须人工标注。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

VALID_IDS = [f"P{i:02d}" for i in range(1, 21)]
EDUCATION_ENUM = {"本科", "硕士", "博士"}
CORE = ("cohort", "education", "major", "city", "position_or_unit")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COHORT_RE = re.compile(r"^20\d{2}届$")

REQUIRED_TOP = ("sample_set", "annotator", "frozen_at", "samples")


def validate_gold(data: dict) -> list[str]:
    errors = []
    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"缺少必填顶层字段 {key}")
    if errors:
        return errors

    samples = data["samples"]
    if len(samples) != 20:
        errors.append(f"样本数必须为 20，实际 {len(samples)}")
    ids = [s.get("sample_id") for s in samples]
    if ids != VALID_IDS:
        bad = [i for i in ids if i not in VALID_IDS]
        dup = [i for i in set(ids) if ids.count(i) > 1]
        if bad:
            errors.append(f"样本 ID 不在 P01–P20 范围: {bad[:5]}")
        if dup:
            errors.append(f"样本 ID 重复: {dup}")
        if len(ids) != len(VALID_IDS):
            missing = [i for i in VALID_IDS if i not in ids]
            errors.append(f"缺少样本 ID: {missing[:5]}")

    for s in samples:
        sid = s.get("sample_id", "?")
        if not SHA256_RE.match(s.get("image_sha256") or ""):
            errors.append(f"{sid}: image_sha256 必须为 64 位十六进制")
        if not s.get("annotated_by"):
            errors.append(f"{sid}: 缺少标注人")
        if not s.get("evidence_summary"):
            errors.append(f"{sid}: 缺少证据摘要（可定位原文/海报位置的说明）")
        cohort = s.get("fields", {}).get("cohort")
        if cohort is not None and not (isinstance(cohort, str) and COHORT_RE.match(cohort)):
            errors.append(f"{sid}: cohort 必须为 null 或 20XX届，实际 {cohort!r}")
        education = s.get("fields", {}).get("education")
        if education is not None and education not in EDUCATION_ENUM:
            errors.append(f"{sid}: education 必须为 {sorted(EDUCATION_ENUM)} 或 null，实际 {education!r}")
        for f in CORE:
            v = s.get("fields", {}).get(f)
            if v == "":
                errors.append(f"{sid}: 字段 {f} 不得用空字符串占位，缺失请写 null")
            if v is not None and not isinstance(v, str):
                errors.append(f"{sid}: 字段 {f} 必须为字符串或 null")
    return errors


def load_and_validate(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_gold(data)
    if errors:
        raise SystemExit("金标准校验失败:\n" + "\n".join(errors))
    return data
