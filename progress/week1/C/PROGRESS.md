# 角色 C 进度（PROGRESS）

- 目标：2026-09-20 23:59 前将 A/B 输出整合为本机及局域网可访问的 Flask API、React/Vite 和 SQLite 检索系统，并留齐验收证据与云端 HTTPS 部署清单。
- 顺序：任务0 环境确认 → 任务1 契约与存储 → 任务2 查询/权限/页面 → 任务3 Evidence-RAG 与性能 → 任务4 演示与发布。
- 最大风险：A/B 的 bundle 交付延迟会阻塞任务3；React/Vite迁移与现有静态交互的功能对齐需要尽早做页面级回归。
- 2026-09-18 决策变更：前端固定为 React+TypeScript+Vite；视觉使用民大红 #A20000；第一周不启用 Embedding；本周 LAN 为部署硬门槛，云端 HTTPS 为最终路线。
- 任务0（2026-09-17 完成）：分支 feat/week1-core-search，基线 34144fb；Python 3.13.15；SQLite 3.50.4，FTS5 trigram 复测通过，1-2 字中文短词确认保留归一化 LIKE 回退。
- 任务1（2026-09-18 完成，含附录 G 私有字段扩展）：app/domain + app/repository 落地五表（articles/assets/experience_records/evidence/processing_events，notice_id 与 record_key 唯一，一帖多人）；BundleImporter 幂等导入，重复导入只更新不增行，visibility 与 7 个私有字段不被导入覆盖；12 个契约测试（含 19 个非法 bundle 子用例）全部通过。
- 任务2（2026-09-18 完成）：Flask 五接口（search/parse/answer/records/auth-me）+ /healthz + 开发角色开关（环境变量保护，关闭 404）；QueryPlan 白名单拒绝未知字段；RolePolicy/Presenter 服务端脱敏，guest DTO 受限字段为 0；FTS5+LIKE 回退+地区别名检索与可解释排序；无结果逐项放宽候选；React/TS/Vite 前端（首页分段搜索/筛选/结果/QueryPlan/匹配原因/复核状态/证据并排详情），生产构建由 Flask 同源托管。累计 60 测试通过，端到端烟测见证据。
- 证据：evidence/week1/C/task0_fts5_trigram_output.md（含检查脚本与实际命令输出）；evidence/week1/C/task1_storage_tests_output.md（存储层交付说明、测试输出与任务书要求对照）；evidence/week1/C/task2_api_frontend_evidence.md（任务2 交付清单、烟测输出与修复记录）。
- 阻塞：见 BLOCKED.md（当前无阻塞，两项上游依赖待观察）。
