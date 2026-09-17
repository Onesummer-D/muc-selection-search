"""article_bundle.v1 构造、脱敏与 Schema 校验。"""
from __future__ import annotations

import hashlib
import json
import os
import re

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "schemas", "article_bundle.v1.schema.json")

CONTENT_TYPES = ("text", "poster", "mixed", "unknown")

# ---------------------------------------------------------------------------
# 脱敏规则（clean_text）：掩码手机号、邮箱、身份证号、长数字串
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{9,}(?!\d)")


def sanitize_text(text: str | None) -> str | None:
    """对文本帖正文脱敏：命中后先判断再掩码（保守全部掩码）。"""
    if text is None:
        return None
    text = _ID_CARD.sub("[身份证已脱敏]", text)
    text = _PHONE.sub("[手机号已脱敏]", text)
    text = _EMAIL.sub("[邮箱已脱敏]", text)
    text = _LONG_DIGITS.sub("[长数字已脱敏]", text)
    return text


def html_to_text(html: str | None) -> str | None:
    """HTML 正文转纯文本：去标签、解码实体、折叠空白（零依赖）。"""
    if html is None:
        return None
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    extractor = _TextExtractor()
    extractor.feed(html)
    text = "".join(extractor.parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
def build_article_bundle(*, notice_id: str, title: str, source_url: str,
                         content_type: str, published_at: str | None,
                         clean_text: str | None, asset_refs: list[dict],
                         fetch_status: str, failure_reason: str | None,
                         fetched_at: str) -> dict:
    """构造 article_bundle.v1 对象（字段与 Schema 一一对应）。"""
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"未知 content_type: {content_type}")
    bundle = {
        "schema_version": "article_bundle.v1",
        "notice_id": str(notice_id),
        "title": title,
        "source_url": source_url,
        "published_at": published_at,
        "content_type": content_type,
        "clean_text": clean_text,
        "asset_refs": asset_refs,
        "fetch_status": fetch_status,
        "failure_reason": failure_reason,
        "fetched_at": fetched_at,
    }
    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle: dict) -> None:
    """按 schemas/article_bundle.v1.schema.json 校验；失败抛 ValidationError。"""
    import jsonschema  # 延迟导入：仅校验时需要

    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.validate(bundle, schema)
    # Schema 之外的契约检查：成功样本不得残留失败原因
    if bundle["fetch_status"] != "failed":
        if bundle.get("failure_reason"):
            raise ValueError("成功样本不得残留 failure_reason")
    else:
        if not bundle.get("failure_reason"):
            raise ValueError("失败样本 failure_reason 不能为空")


def write_bundle(bundle: dict, directory: str) -> str:
    """把单个 bundle 写为 JSON 文件，返回路径。"""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{bundle['notice_id']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, indent=2)
    return path


def content_type_for(detail: dict) -> str:
    """根据详情判断内容类型：图片→poster，正文+图片→mixed，正文→text。

    文本存在性以标签剥离后的纯文本为准（整篇只有 <img> 的海报帖不含文本）。
    """
    has_text = html_to_text(detail.get("content")) is not None
    has_images = bool(detail.get("images"))
    if has_text and has_images:
        return "mixed"
    if has_images:
        return "poster"
    if has_text:
        return "text"
    return "unknown"


def asset_refs_for(detail: dict) -> list[dict]:
    """构造 asset_refs：海报/图片只给 private:// 引用与 SHA-256。

    真实原图通过受控渠道交给 B，不进入仓库。
    `image_hashes`（asset_id → bytes 的 SHA-256）由采集侧在下载后注入；
    测试或未提供时使用占位摘要并在交接表说明。
    """
    refs = []
    for idx, image in enumerate(detail.get("images") or [], start=1):
        asset_id = f"{detail['notice_id']}-poster-{idx:02d}"
        digest = None
        if isinstance(image, dict):
            digest = image.get("sha256")
        refs.append({
            "asset_id": asset_id,
            "kind": "poster",
            "local_ref": f"private://{detail['notice_id']}/poster-{idx:02d}",
            "sha256": digest or ("0" * 64),
        })
    return refs
