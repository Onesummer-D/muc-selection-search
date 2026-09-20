"""角色 B：识别抽取模块。

按第一周接口与数据字典 v1.0 输出 extraction_bundle.v1。
文本帖走 html_rule，海报走 ocr_rule，混合帖保留两类证据。
缺失字段一律 null，不补值；冲突或低置信度进入 review_required。
"""

from .extractor import Extractor, CONFIDENCE_THRESHOLD
from .bundle import validate_bundle

__all__ = ["Extractor", "CONFIDENCE_THRESHOLD", "validate_bundle"]
