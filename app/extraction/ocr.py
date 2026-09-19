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
    """真实 OCR：输出每框文字、置信度、坐标与耗时；失败带 error 状态。

    兼容 PaddleOCR 2.x（.ocr(cls=True) 列表结构）与 3.x（.predict() 字典结构，
    rec_texts/rec_scores/rec_polys 或 rec_boxes）。版本记录在 adapter.version。
    """

    name = "paddleocr"

    def __init__(self):
        try:
            import paddleocr
        except ImportError as exc:  # 环境无 Paddle 时如实失败，不伪造结果
            raise OcrUnavailable(f"paddleocr not importable: {exc}") from exc
        self.version = getattr(paddleocr, "__version__", "unknown")
        from paddleocr import PaddleOCR
        try:  # 3.x 参数
            self._engine = PaddleOCR(lang="ch", use_textline_orientation=True)
        except (TypeError, ValueError):  # 2.x 参数
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
            raw = self._run_engine(str(path))
        except Exception as exc:  # OCR 引擎错误如实上抛状态
            page.error = type(exc).__name__
            page.elapsed_s = time.perf_counter() - start
            return page
        page.elapsed_s = time.perf_counter() - start
        page.boxes = self._normalize(raw)
        return page

    # ---- 引擎调用与输出归一化 ----
    def _run_engine(self, image_path: str):
        if hasattr(self._engine, "predict"):  # 3.x
            return ("predict", self._engine.predict(image_path))
        return ("ocr", self._engine.ocr(image_path, cls=True))  # 2.x

    @staticmethod
    def _normalize(raw) -> list[OcrBox]:
        kind, payload = raw
        boxes: list[OcrBox] = []
        if kind == "predict":  # 3.x：每个 Result 含 rec_texts/rec_scores/rec_polys
            for res in payload:
                texts = list(res.get("rec_texts") or [])
                scores = list(res.get("rec_scores") or [])
                polys = res.get("rec_polys")
                rect = res.get("rec_boxes")
                for i, text in enumerate(texts):
                    conf = float(scores[i]) if i < len(scores) else 0.0
                    boxes.append(OcrBox(
                        text=text, confidence=conf,
                        bbox=_bbox_from(polys, rect, i)))
            return boxes
        for page in payload:  # 2.x：[[points, (text, conf)], ...]
            for line in (page or []):
                points = line[0]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                boxes.append(OcrBox(
                    text=line[1][0], confidence=float(line[1][1]),
                    bbox=[min(xs), min(ys), max(xs), max(ys)]))
        return boxes


def _bbox_from(polys, rect, index):
    """从 3.x 的多边形或矩形数组取第 index 个框的 [x0,y0,x1,y1]。"""
    if polys is not None and index < len(polys):
        pts = [[float(x), float(y)] for x, y in polys[index]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return [min(xs), min(ys), max(xs), max(ys)]
    if rect is not None and index < len(rect):
        x0, y0, x1, y1 = (float(v) for v in rect[index])
        return [x0, y0, x1, y1]
    return [0.0, 0.0, 0.0, 0.0]  # 无坐标时兜底，规则仍可用其文本
