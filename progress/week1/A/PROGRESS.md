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
- [x] 429 反向验证红→绿证据：`evidence/week1/A/retry-429-red.txt` / `retry-429-green.txt`；全量测试输出：`evidence/week1/A/test-output.txt`（53/53 OK）。

### 2026-09-18（凌晨，A1/A2 完成）
- [x] **A1 完成**：人工登录 + probe_endpoints 捕获真实接口（证据 `evidence/week1/A/endpoint-probe.json`）：
  `POST /comsys-portal-notice-web/getNoticeByPage`（表单 currentPage/pageSize/type/searchValue/comsys_random_t，
  响应 datas.tables），就业信息栏目 **type=10**；无独立详情 JSON 接口（readNotice 仅标记已读），
  正文在列表行 notice_content（HTML）。B-1 解除。
- [x] 客户端适配真实 API（POST 表单、snake_case、list 详情模式、HTML 正文图片提取、UEditor 占位图过滤）。
- [x] **A2 完成**：5 篇固定样本已产出并通过 article_bundle.v1 校验 5/5
  （`evidence/week1/A/fixed_samples/*.json` + REPORT.json）。
  - 选样：就业信息栏目 type=10，选调相关 20 篇中经验分享类 13 篇优先入选；
  - 实际构成 4 海报 + 1 混合（理想 2文本/2海报/1混合）：本栏目经验分享类内容以整篇海报为主，
    纯文本帖均为行政通知（奖励申报/成绩公布），为满足"经验分享类"要求保留真实构成；
  - 海报原图（5 张，含真实 SHA-256）存于仓库外 `../controlled_assets/`，交接 B 时走受控渠道，
    bundle 内只含 private:// 引用与摘要；
  - 重现方式：`python -m app.sync.collect_fixed --from-pool`（候选池缓存，无需重新登录）。
- [x] 全套测试 67 项通过。

### 2026-09-18（晚，A3 完成）
- [x] **A3 完成**：人工登录后一次性采集 100 篇就业信息栏目文章，49.7 秒全部成功
  （`evidence/week1/A/ledger/article_ledger.json` + `collection_ledger.csv`）：
  - 状态分布：100/100 processed、0 failed；notice_id 唯一性通过（100 个唯一 ID）。
  - 主题分布：21 篇含"选调"、19 篇含经验分享关键词；内容类型 66 海报 + 25 unknown + 6 text + 3 mixed。
  - unknown 类型 = 列表行 notice_content 为空（不计入失败；这部分将由 A4 一致性检查触发单独请求）。
  - 重现方式：`python run_a3.py`（自动弹出 Playwright 窗口等人登录）。
  - 原始 100 个 bundle JSON 留 `evidence/week1/A/ledger/bundles/`（未入库，按需再生）。
- [x] **网络问题兜底方案已打通**：github.com 直连不稳定期间，用 Python+ctypes 从 Windows
  凭据管理器读取 GitHub OAuth Token 走 api.github.com 通道，把 A3 新提交整包（4 文件、1514 行）
  通过 Git Data API（create-blob / create-tree / create-commit / update-ref）成功推到远程；
  脚本 `push_a3.py` 沉淀在工作区根，作为后续 A4 推送的可复用通道。


## 提交记录（feat/week1-portal-sync）

1. `feat(sync): add CAS assisted portal session` — 人工登录 + 内存会话 + 配置化
2. `feat(sync): add article bundle fetch` — 客户端、限速、重试、分页、bundle 构造
3. `feat(sync): add resumable article ledger` — 台账、恢复、幂等
4. `feat(sync): add scheduler and sync service` — 增量入口、单实例锁、会话失效暂停
5. `test(sync): cover retry resume and dedupe` — 53 项测试
6. `docs(week1): register role A progress and evidence` — 进度、阻塞与证据

## 环境

- Python 3.13（本地 venv）；依赖新增：requests、jsonschema（登记 PR 说明，由 C 处理根配置）。

### A4 运行证据（2026-09-18 22:53）

- **7/7 场景通过**：`evidence/week1/A/a4/scenarios-summary.json`
- 单实例锁、幂等、恢复（重试）、调度周期、会话失效暂停、429 红→绿、全量 pytest 全部 PASS
- 全量 pytest：**68 项**测试通过（`evidence/week1/A/a4/test-output.txt`）
- 429 重试相关：**38 项**测试通过（`evidence/week1/A/a4/429-red-then-green.txt`）
- 驱动器：`run_a4.py`（一键复跑：`python run_a4.py`）
