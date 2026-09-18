# 角色 C 进度（PROGRESS）

- 目标：2026-09-20 23:59 前将 A/B 输出整合为本机及局域网可访问的 Flask API、React/Vite 和 SQLite 检索系统，并留齐验收证据与云端 HTTPS 部署清单。
- 顺序：任务0 环境确认 → 任务1 契约与存储 → 任务2 查询/权限/页面 → 任务3 Evidence-RAG 与性能 → 任务4 演示与发布。
- 最大风险：A/B 的 bundle 交付延迟会阻塞任务3；React/Vite迁移与现有静态交互的功能对齐需要尽早做页面级回归。
- 2026-09-18 决策变更：前端固定为 React+TypeScript+Vite；视觉使用民大红 #A20000；第一周不启用 Embedding；本周 LAN 为部署硬门槛，云端 HTTPS 为最终路线。
- 任务0（2026-09-17 完成）：分支 feat/week1-core-search，基线 34144fb；Python 3.13.15；SQLite 3.50.4，FTS5 trigram 复测通过，1-2 字中文短词确认保留归一化 LIKE 回退。
- 任务1（2026-09-18 完成，含附录 G 私有字段扩展）：app/domain + app/repository 落地五表（articles/assets/experience_records/evidence/processing_events，notice_id 与 record_key 唯一，一帖多人）；BundleImporter 幂等导入，重复导入只更新不增行，visibility 与 7 个私有字段不被导入覆盖；12 个契约测试（含 19 个非法 bundle 子用例）全部通过。
- 任务2（2026-09-18 完成）：Flask 五接口（search/parse/answer/records/auth-me）+ /healthz + 开发角色开关（环境变量保护，关闭 404）；QueryPlan 白名单拒绝未知字段；RolePolicy/Presenter 服务端脱敏，guest DTO 受限字段为 0；FTS5+LIKE 回退+地区别名检索与可解释排序；无结果逐项放宽候选；React/TS/Vite 前端（首页分段搜索/筛选/结果/QueryPlan/匹配原因/复核状态/证据并排详情），生产构建由 Flask 同源托管。
- 任务3（2026-09-18 完成）：DeepSeek LLM 接入（LLMProvider 可插拔 + 引用校验器 + 失败/越界引用自动降级回模板，LLM 只消费证据包）；100 行脱敏性能夹具 32 次查询 max 2.5ms / P95 1.5ms（阈值 1s，余量约 400 倍，回归测试固化）；P1 三接口冻结：stats（角色可见聚合）/compare（≤4 条过 RolePolicy）/export（CSV + XLSX 四 Sheet）；前端对比台、导出按钮、城市分布条。累计 88 测试通过。
- 任务4（2026-09-18 主体完成）：双移动视口 390×844 / 768×1024 实测无横向溢出（程序化断言+截图）；本机 /healthz 与页面验收通过，LAN 灾备步骤就绪（待另一台设备实测截图）；docs/DEPLOYMENT.md 新增命令级执行手册（systemd/Nginx/certbot 自动续期/备份/上线核对单）；敏感文件扫描通过；录屏待 LAN 截图后录制。
- A→C 交接（2026-09-18）：PR #4 已完成验收审查并 APPROVED（5/5 样本双校验器交叉验证、100 篇真实台账、68 测试复跑全绿、敏感扫描干净）；requirements.txt 已固化双方依赖；A 的 5 篇真实 bundle 经 C 导入通道验证通过且幂等，等合并后正式入库。
- 证据：evidence/week1/C/task0_fts5_trigram_output.md；task1_storage_tests_output.md；task2_api_frontend_evidence.md；task3_llm_evidence.md；task3_perf_p1_evidence.md；task3_a_handover_verification.md；task4_release_evidence.md（含视口截图 3 张与待办清单）。
- 阻塞：见 BLOCKED.md（当前无阻塞，两项上游依赖待观察）。
