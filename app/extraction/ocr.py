"""OCR 适配层。

OcrAdapter 协议：extract_records(article) -> (records, failure_reason)。
PaddleOcrAdapter 是真实实现（懒加载 paddleocr，环境无 Paddle 时如实报错）；
测试通过注入识别框结果的适配器来覆盖版面规则，不 mock 规则本身。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import poster_rules


@dataclass
class OcrBox:
    text: str
    confidence: float
    bbox: list[float]  # [x0, y0, x1, y1]


@dataclass
class OcrPage:
    asset_id: str
    boxes: list[OcrBox] = field(default_factory=list)
    elapsed_s: float = 0.0
    error: str | None = None


def resolve_asset_path(local_ref: str) -> Path | None:
    """private://notice_id/asset_id -> 受控本地目录中的实际文件。

    受控目录由环境变量 EXTRACTION_ASSET_DIR 指定（不入仓库）。
    """
    if not local_ref.startswith("private://"):
        return None
    rel = local_ref.removeprefix("private://")
    root = os.environ.get("EXTRACTION_ASSET_DIR")
    if not root:
        return None
    base = Path(root) / rel
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = base.with_suffix(suffix)
        if candidate.exists():
            return candidate
    return base if base.exists() else None


class OcrUnavailable(RuntimeError):
    pass


class PaddleOcrAdapter:
    """真实 OCR：输出每框文字、置信度、坐标与耗时；失败带 error 状态。"""

    name = "paddleocr"

    def __init__(self):
        try:
            from paddleocr import PaddleOCR  # noqa: F401
        except ImportError as exc:  # 环境无 Paddle 时如实失败，不伪造结果
            raise OcrUnavailable(f"paddleocr not importable: {exc}") from exc
        from paddleocr import PaddleOCR
        self._engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    def extract_records(self, article: dict):
        records, failure = [], None
        index = 0
        for asset in article.get("asset_refs", []):
            if asset.get("kind") != "poster":
                continue
            page = self._run_one(asset)
            if page.error:
                failure = f"ocr_error:{page.error}"
                continue
            if not page.boxes:
                failure = "ocr_empty"
                continue
            block_records = poster_rules.records_from_boxes(
                article["notice_id"], page, start_index=index)
            index += len(block_records)
            records.extend(block_records)
        return records, failure

    def _run_one(self, asset: dict) -> OcrPage:
        page = OcrPage(asset_id=asset["asset_id"])
        path = resolve_asset_path(asset.get("local_ref", ""))
        if path is None:
            page.error = "asset_not_found"
            return page
        start = time.perf_counter()
        try:
            result = self._engine.ocr(str(path), cls=True)
        except Exception as exc:  # OCR 引擎错误如实上抛状态
            page.error = type(exc).__name__
            page.elapsed_s = time.perf_counter() - start
            return page
        page.elapsed_s = time.perf_counter() - start
        for line in (result[0] or []):
            points = line[0]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            page.boxes.append(OcrBox(
                text=line[1][0], confidence=float(line[1][1]),
                bbox=[min(xs), min(ys), max(xs), max(ys)]))
        return page
