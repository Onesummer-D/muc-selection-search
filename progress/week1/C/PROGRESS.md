# 角色 C 进度（PROGRESS）

- 目标：2026-09-20 23:59 前将 A/B 输出整合为公共 HTTPS 可访问、局域网可灾备的 Flask/SQLite 检索系统，并留齐验收证据。
- 顺序：任务0 环境确认 → 任务1 契约与存储 → 任务2 查询/权限/页面 → 任务3 Evidence-RAG 与性能 → 任务4 演示与发布。
- 最大风险：A/B 的 bundle 交付延迟会阻塞任务3；公网 HTTPS 部署环境未落实会阻塞任务4。
- 任务0（2026-09-17 完成）：分支 feat/week1-core-search，基线 34144fb；Python 3.13.15；SQLite 3.50.4，FTS5 trigram 复测通过，1-2 字中文短词确认保留归一化 LIKE 回退。
- 证据：evidence/week1/C/task0_fts5_trigram_output.md（含检查脚本与实际命令输出）。
- 阻塞：见 BLOCKED.md（当前无阻塞，两项上游依赖待观察）。
