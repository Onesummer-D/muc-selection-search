"""SQLite 脱敏备份/恢复工具；只接受显式文件路径，不上传任何密钥或原始素材。"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def backup(source: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        count = {table: int(src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ("articles", "experience_records", "evidence")}
    finally:
        dst.close(); src.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print(backup(args.source, args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
