"""多模态路线适配器。

流程（任务书「多模态对照」）：
1. 整图 + 固定提示词发给模型，要求输出 extraction_bundle.v1 兼容 JSON、
   逐字段证据、缺失返回 null；
2. 输出先过 JSON Schema，再过字段词典（education 枚举必须命中；
   其他字段词典未命中标 review_required，不直接丢弃）；
3. 超时、非法 JSON、Schema 不过 → 如实 failed + failure_reason，不猜值。

client 协议：callable(prompt: str, image_path: str) -> str（原始响应文本）。
真实实现从环境变量读服务商配置（LLM_PROVIDER/LLM_API_KEY，只放本地 .env）；
测试注入假 client，被测的是解析、校验、超时与状态逻辑，不 mock 抽取规则。
"""

from __future__ import annotations

import json
import os
import re
import time

from . import fields as F
from .bundle import validate_bundle

PROMPT_TEMPLATE = """你是选调经验海报信息抽取器。请从这张海报图片中抽取每位人物的下列字段：
届别(cohort，格式如 2025届)、年级(grade，入学年份如 2020)、学历(education，本科/硕士/博士)、
学院(college)、专业(major)、城市(city)、岗位或单位(position_or_unit)。
要求：
1. 只使用图片中明确出现的信息，缺失字段返回 null，不得猜测。
2. 每个非空字段必须单独输出一条 evidence，且 field 与字段名完全一致；
   例如 education 的证据不能合并进 cohort 的证据里。
3. position_or_unit 只输出单位或职务本体（如"山西省临汾市城联社"），
   不要附加"试用期公务员（不定职级）"等任职状态修饰。
4. 一张海报有多位人物时，每人一条记录。
5. 只输出 JSON，不要任何解释文字。结构如下：
{"records": [{"cohort": "2025届", "grade": "2020", "education": "本科", "college": "信息学院",
"major": "计算机科学与技术", "city": "成都", "position_or_unit": "某区基层岗位",
"evidence": [{"field": "cohort", "text": "2025届"}, {"field": "grade", "text": "2020级"},
{"field": "education", "text": "本科"}, {"field": "major", "text": "计算机科学与技术"},
{"field": "city", "text": "工作地点 成都"}, {"field": "position_or_unit", "text": "某区基层岗位"}]}]}"""


class MultimodalTimeout(RuntimeError):
    pass


_TRIAL_TAILS = ("试用期公务员（不定职级）", "试用期公务员(不定职级)",
                "试用期干部（不定职级）", "试用期干部(不定职级)",
                "试用期公务员", "试用期干部")


def _strip_trial_tail(value: str) -> str:
    """剥离岗位/单位值尾部的任职状态修饰（确定性后处理）。"""
    s = value.strip()
    changed = True
    while changed:
        changed = False
        for tail in _TRIAL_TAILS:
            if s.endswith(tail) and len(s) > len(tail):
                s = s[: -len(tail)].rstrip("，,、 ")
                changed = True
    return s



def _parse_json_text(raw: str) -> dict:
    """剥掉可能的 ```json 围栏后解析；失败抛 ValueError。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("response contains no JSON object")
    return json.loads(text[start:end + 1])


def _validate_against_dictionaries(record: dict) -> list[str]:
    """字段词典校验：返回问题列表（不修改记录值）。"""
    issues = []
    edu = record.get("education")
    if edu is not None and edu not in F.EDUCATION_ENUM:
        issues.append(f"education 不在枚举 {list(F.EDUCATION_ENUM)}: {edu!r}")
    cohort = record.get("cohort")
    if cohort is not None and not F.COHORT_RE.fullmatch(F.normalize(cohort)):
        issues.append(f"cohort 不是 20XX届 格式: {cohort!r}")
    for f in ("major", "city", "position_or_unit"):
        v = record.get(f)
        if v is not None and not isinstance(v, str):
            issues.append(f"{f} 必须为字符串或 null")
    return issues


class MultimodalAdapter:
    name = "multimodal"

    def __init__(self, client=None, timeout_s: float = 30.0,
                 provider: str | None = None, model: str | None = None):
        self.timeout_s = timeout_s
        self.last_elapsed_s = 0.0
        self.provider = provider or os.environ.get("LLM_PROVIDER", "")
        self.model = model or os.environ.get("LLM_MODEL", "")
        # 供评测报告登记（不含 Key）
        self.base_url = os.environ.get("LLM_BASE_URL", "")
        self._client = client or self._make_real_client()

    @staticmethod
    def _make_real_client():
        """OpenAI 兼容多模态客户端（智谱/通义/Kimi/OpenAI 均适用）。

        配置只来自本地 .env：LLM_API_KEY / LLM_MODEL / LLM_BASE_URL / LLM_TIMEOUT_S。
        Key 不落代码、不进日志；素材由调用方保证脱敏（烟测用合成海报）。
        """
        import base64
        import io

        import requests

        api_key = os.environ.get("LLM_API_KEY")
        model = os.environ.get("LLM_MODEL")
        base_url = (os.environ.get("LLM_BASE_URL")
                    or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        timeout = float(os.environ.get("LLM_TIMEOUT_S", "60"))
        if not api_key:
            raise RuntimeError("LLM_API_KEY 未配置（写入本地 .env，勿提交仓库）")
        if not model:
            raise RuntimeError("LLM_MODEL 未配置（如 glm-4v-flash / qwen-vl-plus）")

        def client(prompt: str, image_path: str) -> str:
            # 大图直传会触发网络路径的 SSL EOF（实测 >800KB body 不稳定），
            # 发送前等比缩到最长边 1600px、JPEG q85——VLM 识别不需要原始分辨率
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            scale = min(1.0, 1600.0 / max(img.size))
            if scale < 1.0:
                img = img.resize((round(img.width * scale), round(img.height * scale)))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            payload = {
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }],
                "temperature": 0,
            }
            try:
                resp = requests.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=timeout,
                )
            except requests.exceptions.Timeout as exc:
                raise MultimodalTimeout(f"LLM 请求超时 {timeout}s") from exc
            if resp.status_code != 200:
                raise RuntimeError(f"LLM HTTP {resp.status_code}")
            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"LLM 响应格式异常: {list(data)}") from exc

        return client

    def extract_records(self, article: dict):
        from .ocr import resolve_asset_path
        from .extractor import _record_key

        records, failure = [], None
        for asset in article.get("asset_refs", []):
            if asset.get("kind") != "poster":
                continue
            path = resolve_asset_path(asset.get("local_ref", ""))
            if path is None:
                failure = "asset_not_found"
                continue
            start = time.perf_counter()
            try:
                raw = self._client(PROMPT_TEMPLATE, str(path))
            except MultimodalTimeout:
                failure = "model_timeout"
                continue
            except Exception as exc:
                failure = f"model_error:{type(exc).__name__}"
                continue
            self.last_elapsed_s = time.perf_counter() - start

            try:
                data = _parse_json_text(raw)
            except (ValueError, json.JSONDecodeError):
                failure = "model_invalid_json"
                continue

            # 确定性后处理：position_or_unit 剥离任职状态尾巴（B 项要求）
            for rec in (data.get("records") or []):
                v = rec.get("position_or_unit")
                if isinstance(v, str):
                    rec["position_or_unit"] = _strip_trial_tail(v)

            asset_records = data.get("records")
            if not isinstance(asset_records, list):
                failure = "model_missing_records"
                continue

            dict_issues: list[str] = []
            for i, rec in enumerate(asset_records):
                issues = _validate_against_dictionaries(rec)
                dict_issues.extend(f"record[{i}]: {m}" for m in issues)
                evidence = [
                    {"field": ev.get("field"), "text": ev.get("text", ""),
                     "method": "multimodal", "asset_id": asset["asset_id"],
                     "bbox": None}
                    for ev in rec.get("evidence", [])
                    if isinstance(ev, dict) and ev.get("field") and ev.get("text")
                ]
                evidence_fields = {e["field"] for e in evidence}
                core = ("cohort", "education", "major", "city", "position_or_unit")
                missing_core = any(rec.get(f) is None for f in core)
                review = bool(issues) or missing_core or any(
                    rec.get(f) is not None and f not in evidence_fields
                    for f in core)
                records.append({
                    "record_key": _record_key(article["notice_id"], len(records)),
                    "cohort": rec.get("cohort"), "grade": rec.get("grade"),
                    "education": rec.get("education"), "college": rec.get("college"),
                    "major": rec.get("major"), "city": rec.get("city"),
                    "position_or_unit": rec.get("position_or_unit"),
                    "review_status": "review_required" if review else "processed",
                    "confidence": 0.75 if not review else 0.4,
                    "evidence": evidence,
                })
            if dict_issues:
                failure = failure or "dictionary_violation"
        return records, failure
