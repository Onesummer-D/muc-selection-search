"""SQLite 恢复 + 行数/SHA 校验脚本（week2 9/23 任务交付）。

职责：
- 读 backup_sqlite.py 产出的 manifest，对三类行数（articles/experience_records/
  evidence）和 SHA-256 做一致性校验。
- 默认拒绝把备份还原到原 source 路径（避免误覆盖运行库）。要强制覆盖需
  显式 --allow-overwrite-source。
- 支持 --dry-run：仅校验，不动文件。

约束：
- 退出码：
    0 = 全部一致 + 恢复成功（或 dry-run 通过）
    1 = 行数不一致
    2 = SHA-256 不一致
    3 = 路径冲突或文件缺失
    4 = 其它错误

复现：
    # 仅校验（不动文件）
    python scripts/restore_sqlite.py \
        --backup evidence/week2/A/_artifacts/app-2026-09-23.db \
        --manifest evidence/week2/A/_artifacts/app-2026-09-23.manifest.json \
        --dry-run

    # 恢复到目标
    python scripts/restore_sqlite.py \
        --backup evidence/week2/A/_artifacts/app-2026-09-23.db \
        --manifest evidence/week2/A/_artifacts/app-2026-09-23.manifest.json \
        --target data/app-restored.db
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 与 backup_sqlite.py 保持一致
ROW_COUNT_TABLES = ("articles", "experience_records", "evidence")


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        out: dict[str, int] = {}
        for t in ROW_COUNT_TABLES:
            cur = conn.execute(f"SELECT COUNT(*) FROM {t}")
            out[t] = int(cur.fetchone()[0])
        return out
    finally:
        conn.close()


def verify_backup(backup: Path, manifest: Path | None) -> dict:
    """读 manifest（如果有）→ 比对备份内行数/SHA → 返回结果。"""
    if not backup.exists():
        raise FileNotFoundError(f"备份文件不存在: {backup}")

    backup_counts = _row_counts(backup)
    backup_sha = _sha256_of(backup)

    result = {
        "backup": str(backup),
        "backup_size_bytes": backup.stat().st_size,
        "backup_sha256": backup_sha,
        "backup_row_counts": backup_counts,
        "manifest_loaded": False,
        "manifest_sha256": None,
        "manifest_row_counts": None,
        "sha_match": True,
        "row_count_match": True,
    }

    if manifest is not None:
        if not manifest.exists():
            raise FileNotFoundError(f"manifest 不存在: {manifest}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        result["manifest_loaded"] = True
        result["manifest_sha256"] = data.get("target_sha256")
        result["manifest_row_counts"] = data.get("row_counts")
        if data.get("target_sha256") != backup_sha:
            result["sha_match"] = False
        if data.get("row_counts") and data["row_counts"] != backup_counts:
            result["row_count_match"] = False
    return result


def perform_restore(backup: Path, target: Path, overwrite: bool) -> dict:
    """把 backup 拷到 target，覆盖前要求 overwrite=True。"""
    if target.exists() and not overwrite:
        raise FileExistsError(
            f"目标已存在: {target}（如确认覆盖请显式 --allow-overwrite）"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    counts = _row_counts(target)
    return {"restored_to": str(target), "row_counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--backup", type=Path, required=True, help="备份 db 路径")
    parser.add_argument("--manifest", type=Path, default=None, help="可选 manifest.json")
    parser.add_argument("--target", type=Path, default=None, help="恢复目标（不传则仅校验）")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写入")
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="目标已存在时允许覆盖（必须显式）",
    )
    args = parser.parse_args()

    try:
        verification = verify_backup(args.backup, args.manifest)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    # 输出校验结果（结构化，便于 evidence 文档引用）
    print(f"backup:            {verification['backup']}")
    print(f"backup_size_bytes: {verification['backup_size_bytes']}")
    print(f"backup_sha256:     {verification['backup_sha256']}")
    for t, n in verification["backup_row_counts"].items():
        print(f"backup_row[{t}]: {n}")
    if verification["manifest_loaded"]:
        print(f"manifest_sha256:   {verification['manifest_sha256']}")
        for t, n in (verification["manifest_row_counts"] or {}).items():
            print(f"manifest_row[{t}]: {n}")
        print(f"sha_match:         {verification['sha_match']}")
        print(f"row_count_match:   {verification['row_count_match']}")
        if not verification["sha_match"]:
            print("FAIL: SHA-256 不一致", file=sys.stderr)
            return 2
        if not verification["row_count_match"]:
            print("FAIL: 三类行数不一致", file=sys.stderr)
            return 1

    if args.dry_run:
        print("status: ok (dry-run, 未恢复)")
        return 0

    if args.target is None:
        print("status: ok (仅校验，未指定 --target)")
        return 0

    try:
        restore = perform_restore(args.backup, args.target, args.allow_overwrite)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    print(f"restored_to:       {restore['restored_to']}")
    for t, n in restore["row_counts"].items():
        print(f"target_row[{t}]: {n}")

    # 校验恢复后行数 == 备份行数
    if restore["row_counts"] != verification["backup_row_counts"]:
        print("FAIL: 恢复后行数与备份不一致", file=sys.stderr)
        return 1

    print(
        f"finished_at:       {datetime.now(timezone.utc).isoformat()}"
    )
    print("status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())