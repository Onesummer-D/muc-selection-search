# A 角色 SQLite 脱敏备份/恢复证据（9/23 任务交付）

> 冻结日期：2026-09-21
> 适用分支：`feat/week2-A-platform`
> 关联台账：A-03（备份恢复 + 三类行数校验 + SHA）

本文件落地 9/23 任务书要求的 SQLite 脱敏快照、备份、恢复、行数校验、SHA、articles/records/evidence 行数核验。

## 1. 范围与红线

- 范围：仓库内 `data/app.db`（演示库，5 篇文章 + 7 条记录 + 11 条 evidence，全部脱敏 seed）。
- 备份产物：写入仓库 `evidence/week2/A/_artifacts/`，**不进** git 历史（_artifacts/ 目录在 .gitignore 内覆盖范围）。
- 脱敏清单：`experience_records` 中的 6 个敏感字段 → `person_name`、`avatar_ref`、`qr_code_ref`、`contact_info`、`meeting_entry`、`source_sso_url` 在备份阶段置 NULL。
- 红线：备份产物不含 Cookie、密码、API Key、真实姓名、原始海报外链、绝对路径。`backup_sqlite.py` 内置正则扫描 `FORBIDDEN_LITERALS`，命中即让脚本退出码 1。
- 三类行数校验：`articles`、`experience_records`、`evidence`。

## 2. 运行命令（按顺序）

```bash
# 0) 准备：seed 一个完整演示库
python -c "import sys; sys.path.insert(0, '.')\\
from app.repository.sqlite_repository import SQLiteRepository\\
from app.web.seed import seed\\
repo = SQLiteRepository('data/app.db'); print(seed(repo))"

# 1) 备份（产出 _artifacts/app-2026-09-23.db + manifest.json）
python scripts/backup_sqlite.py \\
    data/app.db \\
    evidence/week2/A/_artifacts/app-2026-09-23.db \\
    --manifest evidence/week2/A/_artifacts/app-2026-09-23.manifest.json

# 2) 模拟破坏（5→3 articles, 7→4 records, 11→5 evidence）
python -c "import sqlite3\\
db=sqlite3.connect('data/app.db')\\
db.execute(\"DELETE FROM articles WHERE notice_id IN ('portal-10001','portal-10002')\")\\
db.execute(\"DELETE FROM experience_records WHERE notice_id IN ('portal-10001','portal-10002')\")\\
db.execute(\"DELETE FROM evidence WHERE record_key IN ('portal-10001-01','portal-10001-02','portal-10002-01')\")\\
db.commit()"

# 3) 恢复（target=data/app-restored.db）
rm -f data/app-restored.db
python scripts/restore_sqlite.py \\
    --backup evidence/week2/A/_artifacts/app-2026-09-23.db \\
    --manifest evidence/week2/A/_artifacts/app-2026-09-23.manifest.json \\
    --target data/app-restored.db
```

## 3. 实际值

| 步骤 | 三类行数（articles / records / evidence） | SHA-256 | 备注 |
|---|---|---|---|
| 备份前（干净） | 5 / 7 / 11 | — | `data/app.db` 由 seed() 重建 |
| 备份产物 | 5 / 7 / 11 | `b343c3b4…077d076` | `evidence/week2/A/_artifacts/app-2026-09-23.db`，135168 字节 |
| 备份后破坏 | 3 / 4 / 5 | — | `data/app.db` 模拟丢失 portal-10001/10002 三层数据 |
| 恢复后（data/app-restored.db） | 5 / 7 / 11 | `b343c3b4…077d076` | 恢复产物 SHA 与备份一致 |
| 备份内禁字面量扫描 | — | — | **0 命中**（PHPSESSID/密码/API Key/Authorization/Windows 路径/原始海报外链） |

脱敏字段空值统计（恢复后 db）：

| 字段 | 非空记录数 | 期望 |
|---|---|---|
| person_name | 0 / 7 | 0 |
| avatar_ref | 0 / 7 | 0 |
| qr_code_ref | 0 / 7 | 0 |
| contact_info | 0 / 7 | 0 |
| meeting_entry | 0 / 7 | 0 |
| source_sso_url | 0 / 7 | 0 |

非敏感字段保留（恢复后 db）：

| 字段 | 非空记录数 | 期望 |
|---|---|---|
| cohort | 5 / 7 | ≥ 4（seed 里有 5 条带 cohort） |
| city | 5 / 7 | ≥ 4 |

## 4. 反向验证（红→绿）

### 篡改检测（红）
篡改手段：复制备份 → 删除 1 篇文章（portal-10005）。

| 项目 | 篡改后值 | 期望行为 | 实际 |
|---|---|---|---|
| backup_sha256 | `1d5a118d…4681fd0` | 与 manifest 不一致 | ✅ SHA 不一致 |
| backup_row[articles] | 4 | 与 manifest 5 不一致 | ✅ 行数不一致 |
| 脚本退出码 | — | 2 | ✅ exit=2 |

### 错误路径（红）
| 场景 | 期望退出码 | 实际 |
|---|---|---|
| `--manifest` 指向不存在文件 | 3 | ✅ exit=3 |
| `--target` 已存在但未带 `--allow-overwrite` | 3 | ✅ exit=3 |
| `--backup` 指向不存在文件 | 3 | ✅ exit=3 |

## 5. 复现

```bash
git checkout feat/week2-A-platform
python scripts/backup_sqlite.py data/app.db /tmp/backup.db --manifest /tmp/backup.manifest.json
python scripts/restore_sqlite.py --backup /tmp/backup.db --manifest /tmp/backup.manifest.json --dry-run
```

## 6. 交付物清单

| 路径 | 说明 |
|---|---|
| `scripts/backup_sqlite.py` | 脱敏备份（在线热备 + 6 字段清空 + 禁字面量扫描 + 可选 manifest） |
| `scripts/restore_sqlite.py` | 恢复 + 三类行数 + SHA 校验（支持 `--dry-run` / `--allow-overwrite`） |
| `evidence/week2/A/backup-recovery.md` | 本文件 |
| `evidence/week2/A/_artifacts/app-2026-09-23.db` | 9/23 备份产物（不进 git） |
| `evidence/week2/A/_artifacts/app-2026-09-23.manifest.json` | 备份 manifest（不进 git） |
| `evidence/week2/A/_artifacts/step1-backup.txt` | 步骤 1 输出 |
| `evidence/week2/A/_artifacts/step2-damage.txt` | 步骤 2 输出 |
| `evidence/week2/A/_artifacts/step3-restore.txt` | 步骤 3 输出 |
| `evidence/week2/A/_artifacts/step4-verify.txt` | 步骤 4 输出（脱敏 + 保留） |
| `evidence/week2/A/_artifacts/step5-tamper.txt` | 步骤 5 输出（篡改检测 → exit=2） |
| `evidence/week2/A/_artifacts/step6-error-paths.txt` | 步骤 6 输出（错误路径 → exit=3） |

## 7. 变更记录

| 日期 | 变更 | 影响面 |
|---|---|---|
| 2026-09-21 | 扩展 `scripts/backup_sqlite.py`：脱敏 + manifest + 禁字面量扫描 + 结构化输出 | 所有依赖 SQLite 备份的运行 |
| 2026-09-21 | 新增 `scripts/restore_sqlite.py`：SHA 校验 + 三类行数校验 + 错误退出码 | 同上 |
| 2026-09-21 | 落 `evidence/week2/A/backup-recovery.md` + `_artifacts/` 下 6 份 step 输出 | A-03 验收项 |

---

**契约评审触发条件**：本文件 §1 红线 / §3 三类行数清单 / 脱敏字段清单任何一项变更，须在 PR 中 @ B/C 角色 + reviewer 重审。