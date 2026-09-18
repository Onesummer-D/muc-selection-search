# 角色 C 进度（PROGRESS）

- 目标：2026-09-20 23:59 前将 A/B 输出整合为本机及局域网可访问的 Flask API、React/Vite 和 SQLite 检索系统，并留齐验收证据与云端 HTTPS 部署清单。
- 顺序：任务0 环境确认 → 任务1 契约与存储 → 任务2 查询/权限/页面 → 任务3 Evidence-RAG 与性能 → 任务4 演示与发布。
- 最大风险：A/B 的 bundle 交付延迟会阻塞任务3；React/Vite迁移与现有静态交互的功能对齐需要尽早做页面级回归。
- 2026-09-18 决策变更：前端固定为 React+TypeScript+Vite；视觉使用民大红 #A20000；第一周不启用 Embedding；本周 LAN 为部署硬门槛，云端 HTTPS 为最终路线。
- 任务0（2026-09-17 完成）：分支 feat/week1-core-search，基线 34144fb；Python 3.13.15；SQLite 3.50.4，FTS5 trigram 复测通过，1-2 字中文短词确认保留归一化 LIKE 回退。
- 证据：evidence/week1/C/task0_fts5_trigram_output.md（含检查脚本与实际命令输出）。
- 阻塞：见 BLOCKED.md（当前无阻塞，两项上游依赖待观察）。
