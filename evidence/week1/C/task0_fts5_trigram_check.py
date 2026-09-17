"""任务0环境确认：在内存 SQLite 中复测 FTS5 与 trigram 分词器支持。

领导机器（SQLite 3.53.1）已验证 FTS5 trigram 可用；按角色C任务书要求，
每个执行环境必须在任务0复测。若本脚本报告 trigram 不可用，
回退方案为 FTS5 unicode61 + 归一化 LIKE（中文 1-2 字查询），不更换数据库。

用法：
    python evidence/week1/C/task0_fts5_trigram_check.py
"""

import sqlite3
import sys


def main() -> int:
    print(f"python: {sys.version.split()[0]}")
    print(f"sqlite3 module runtime: {sqlite3.sqlite_version}")

    conn = sqlite3.connect(":memory:")

    # 1. FTS5 基础可用性
    conn.execute("CREATE VIRTUAL TABLE base_fts USING fts5(content)")
    print("fts5: available")

    # 2. trigram 分词器：建表 + 中文子串召回
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE tri_fts USING fts5(content, tokenize='trigram')"
        )
    except sqlite3.OperationalError as exc:
        print(f"fts5_trigram: NOT available ({exc})")
        print("fallback: FTS5 unicode61 + normalized LIKE for 1-2 char Chinese queries")
        conn.close()
        return 1

    conn.execute("INSERT INTO tri_fts(content) VALUES ('工作地点成都基层岗位')")
    conn.execute("INSERT INTO tri_fts(content) VALUES ('四川选调经验分享')")
    hits = conn.execute(
        "SELECT content FROM tri_fts WHERE tri_fts MATCH '成都基层'"
    ).fetchall()
    print(f"fts5_trigram: available, MATCH '成都基层' -> {len(hits)} hit(s): {[r[0] for r in hits]}")

    # 3. 短查询演示：确认 2 字查询为何必须保留 LIKE 回退
    try:
        short_hits = conn.execute(
            "SELECT content FROM tri_fts WHERE tri_fts MATCH '成都'"
        ).fetchall()
        print(f"fts5_trigram MATCH '成都'(2字) -> {len(short_hits)} hit(s)（trigram 最小匹配长度为 3）")
    except sqlite3.OperationalError as exc:
        print(f"fts5_trigram MATCH '成都'(2字) -> error: {exc}")

    like_hits = conn.execute(
        "SELECT content FROM tri_fts WHERE content LIKE '%成都%'"
    ).fetchall()
    print(f"LIKE '%成都%' -> {len(like_hits)} hit(s)：短词回退有效")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
