# 任务0 环境确认证据（角色 C）

- 日期：2026-09-17 23:05 +08:00（本地）
- 分支：feat/week1-core-search（基于 origin/main）
- 基线 commit：34144fb (Merge pull request #2 from Onesummer-D/docs/week1-execution-pack)
- 环境：Windows，Python 3.13.15，SQLite runtime 3.50.4

## 命令与实际输出

```
$ python evidence/week1/C/task0_fts5_trigram_check.py
python: 3.13.15
sqlite3 module runtime: 3.50.4
fts5: available
fts5_trigram: available, MATCH '成都基层' -> 1 hit(s): ['工作地点成都基层岗位']
fts5_trigram MATCH '成都'(2字) -> 0 hit(s)（trigram 最小匹配长度为 3）
LIKE '%成都%' -> 1 hit(s)：短词回退有效
exit_code=0
```

## 结论

- 本机 SQLite 3.50.4 支持 FTS5 与 trigram 分词器，与领导机器（SQLite 3.53.1）结论一致，任务0复测通过。
- 中文 4 字子串可通过 trigram MATCH 召回；1-2 字短词 MATCH 召回为 0，确认必须保留归一化 LIKE 回退（与 ARCHITECTURE.md 6.2 节方案一致）。
- 无需回退到 unicode61；trigram 方案在本环境可用。

## 其他环境自检（2026-09-17 23:00 +08:00）

```
$ git status --short
 M "docs/week1/00_本周总体目标与协作执行手册.docx"   # 本地未提交改动（他人文档，未纳入本次提交）
 M "docs/week1/01_角色A_采集与更新任务书.docx"       # 本地未提交改动（他人文档，未纳入本次提交）
$ git log -1 --oneline
34144fb Merge pull request #2 from Onesummer-D/docs/week1-execution-pack
$ python --version
Python 3.13.15
```
