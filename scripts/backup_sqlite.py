"""SQLite 脱敏备份脚本（week2 9/23 任务交付）。

职责：
- 用 sqlite3.Connection.backup 做在线热备（不锁库、不停服务）。
- 备份前对 experience_records 中 6 类敏感字段清空（person_name/avatar_ref/
  qr_code_ref/contact_info/meeting_entry/source_sso_url），证据表 text
  字段保留（受字段白名单约束，原文不含学号/Cookie/原始海报）。
- 写出三类行数（articles/experience_records/evidence）和 SHA-256，便于
  恢复脚本对照。
- 可选输出 JSON manifest（--manifest），给 restore 脚本自动比对。

约束：
- 只接受显式文件路径参数；不接受环境变量或 stdin 注入。
- 备份文件写入 git 仓库外（如 evidence/week2/A/_artifacts/），目标 .gitignore 已
  覆盖 *.db 与 _artifacts/，避免误提交原始库或备份。
- 扫描命中 Cookie/密码/API Key/真实姓名/原始海报/绝对路径等敏感字面量，命中则
  让脚本非 0 退出，避免证据落入库。

复现：
    python scripts/backup_sqlite.py \
        data/app.db \
        evidence/week2/A/_artifacts/app-2026-09-23.db \
        --manifest evidence/week2/A/_artifacts/app-2026-09-23.manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---- 三类行数 + 全部表清单（与 sqlite_repository.SCHEMA_SQL 同步） ----
ROW_COUNT_TABLES = ("articles", "experience_records", "evidence")
ALL_TABLES = (
    "articles",
    "assets",
    "experience_records",
    "evidence",
    "processing_events",
    "app_users",
    "user_privacy",
    "saved_searches",
    "search_history",
    "notifications",
    "articles_fts",  # FTS5 影子表，触发器会同步
)

# experience_records 中需在备份阶段置空的字段（私密/易泄露原始海报外链）
SENSITIVE_RECORD_FIELDS = (
    "person_name",
    "avatar_ref",
    "qr_code_ref",
    "contact_info",
    "meeting_entry",
    "source_sso_url",
)

# 备份产物字面量扫描关键词：命中即拒绝（避免误把原始海报/cookie 拷进证据目录）
FORBIDDEN_LITERALS = (
    re.compile(r"PHPSESSID=[A-Za-z0-9]+"),
    re.compile(r"(?i)\bpassword\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+\S+"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\", re.IGNORECASE),  # Windows 绝对路径
    re.compile(r"private://[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|webp)$"),
)


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in ROW_COUNT_TABLES:
        cur = conn.execute(f"SELECT COUNT(*) FROM {t}")
        out[t] = int(cur.fetchone()[0])
    return out


def _scrub_records(conn: sqlite3.Connection) -> int:
    """把 experience_records 的 6 个敏感字段清空，返回受影响行数。"""
    if not SENSITIVE_RECORD_FIELDS:
        return 0
    set_clause = ", ".join(f"{c} = NULL" for c in SENSITIVE_RECORD_FIELDS)
    cur = conn.execute(f"UPDATE experience_records SET {set_clause}")
    return cur.rowcount


def _scan_forbidden(db_path: Path) -> list[str]:
    """导出每行文本，扫禁字面量（命中即列出，便于人工复核）。"""
    conn = sqlite3.connect(db_path)
    hits: list[str] = []
    try:
        for table in ALL_TABLES:
            if table == "articles_fts":
                continue  # FTS 镜像，不重复扫
            cur = conn.execute(f"SELECT name FROM pragma_table_info('{table}')")
            cols = [r[0] for r in cur.fetchall()]
            if not cols:
                continue
            quoted = ", ".join(f"CAST({c} AS TEXT)" for c in cols)
            for row in conn.execute(f"SELECT {quoted} FROM {table}"):
                blob = "\n".join("" if v is None else str(v) for v in row)
                for pat in FORBIDDEN_LITERALS:
                    m = pat.search(blob)
                    if m:
                        hits.append(f"{table}: {m.group(0)!r}")
    finally:
        conn.close()
    return hits


def backup(source: Path, target: Path) -> dict:
    """主流程：热备 → 脱敏 → 校验 → 扫描禁字面量 → 返回结果字典。"""
    if not source.exists():
        raise FileNotFoundError(f"源数据库不存在: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        scrubbed = _scrub_records(dst)
        dst.commit()
        counts_after = _row_counts(dst)
    finally:
        dst.close()
        src.close()

    sha = _sha256_of(target)
    hits = _scan_forbidden(target)
    return {
        "source": str(source),
        "target": str(target),
        "scrubbed_records_rows": scrubbed,
        "row_counts": counts_after,
        "sha256": sha,
        "size_bytes": target.stat().st_size,
        "forbidden_hits": hits,
        "backed_up_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("source", type=Path, help="源 SQLite 文件")
    parser.add_argument("target", type=Path, help="备份目标 SQLite 文件")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="可选：把 SHA/行数/时间写入 JSON manifest，给 restore 脚本比对",
    )
    args = parser.parse_args()

    try:
        result = backup(args.source, args.target)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # 输出结构化结果（脚本可被 evidence 文档直接引用）
    print(f"source:       {result['source']}")
    print(f"target:       {result['target']}")
    print(f"size_bytes:   {result['size_bytes']}")
    print(f"sha256:       {result['sha256']}")
    print(f"scrubbed_rows:{result['scrubbed_records_rows']}")
    for t, n in result["row_counts"].items():
        print(f"row_count[{t}]: {n}")
    if result["forbidden_hits"]:
        print("FORBIDDEN_HITS:")
        for h in result["forbidden_hits"]:
            print(f"  - {h}")
        return 1

    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        # manifest 只放可信元数据，不放全文/路径回写
        manifest = {
            "target_sha256": result["sha256"],
            "target_size_bytes": result["size_bytes"],
            "row_counts": result["row_counts"],
            "scrubbed_records_rows": result["scrubbed_records_rows"],
            "backed_up_at": result["backed_up_at"],
        }
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"manifest:     {args.manifest}")

    print("status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())