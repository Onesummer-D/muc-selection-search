"""extraction_bundle.v1 组装与校验。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "extraction_bundle.v1.schema.json"

_cache: dict | None = None


def _schema() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _cache


def validate_bundle(bundle: dict) -> list[str]:
    """返回违反 Schema 的错误列表；空列表即通过。"""
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    return [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
            for e in validator.iter_errors(bundle)]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
