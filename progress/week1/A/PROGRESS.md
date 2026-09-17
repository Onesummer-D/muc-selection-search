# 角色 A 进度（采集与更新）

## 目标（≤10 行）

1. 目标：交付可复现的门户采集与增量更新模块；100 篇目标文章都有明确状态；先交 5 篇脱敏固定样本。
2. 顺序：A1 接口核查 → A2 固定样本 → A3 台账 → A4 Scheduler/SyncService+测试。
3. 最大风险：门户真实端点与登录方式未在仓库登记（A1 待人工确认），可能阻塞真实采集；先用可注入传输层完成全部逻辑与测试。
4. 界限：只改 app/datasource/**、app/sync/**、tests/datasource/**、evidence/week1/A/**、progress/week1/A/**。

## DDL（全队确认整体推迟一天，2026-09-17）

- A1 接口与素材可用性核查：9/18 12:00
- A2 5 篇 article_bundle.v1 固定样本：9/18 18:00
- A3 100 篇采集状态台账：9/19 22:00
- A4 Scheduler、SyncService、测试和证据：9/20 18:00

## 执行日志

### 2026-09-17（晚）
- [x] 从 main 新建 `feat/week1-portal-sync`，工作区干净（git log -1 = 34144fb）。
- [x] 阅读 README、ARCHITECTURE、TEAM_RULES、04_接口与数据字典、article_bundle.v1 Schema。
- [x] A1 部分核查：`.env.example` 已预留 CAS_BASE_URL/PORTAL_BASE_URL；仓库未登记真实门户端点与栏目参数 → 见 BLOCKED.md B-1。
- [x] 实现 app/datasource（配置化门户客户端、限速 0.8–1.5s、重试≤3、分页游标）。
- [x] 实现 app/sync（状态台账、断点恢复、幂等、SyncService、Scheduler 单实例锁）。
- [x] 实现 tests/datasource（分页/重复页/空列表/缺字段/429 退避/第三次失败/恢复/重复运行/调度/并发锁/Schema 校验）。
- [ ] 待人工：CAS 登录获取真实会话后跑真实采集，产出 5 篇固定样本（工具：`python -m app.sync.collect_fixed`）。

## 环境

- Python 3.13（本地 venv）；依赖新增：requests、jsonschema（登记 PR 说明，由 C 处理根配置）。
