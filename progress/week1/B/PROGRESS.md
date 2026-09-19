# 角色 B 进度（识别抽取与评测）

## 目标（≤10 行）

1. 目标：交付可批处理的 OCR + 规则抽取模块；20 张海报人工金标准；OCR 与多模态同批对照评测；每条记录有可检索 evidence pack 和复核队列。
2. 顺序：任务0 环境与接收确认 → 5 篇固定样本抽取烟测（补 B2）→ 20 张金标准 + 批处理入口（B3）→ 对照评测 + 报告 + 交接（B4）→ Draft PR。
3. 最大风险：海报原图未到达本机（A 存于仓库外 `../controlled_assets/`，需受控渠道交接）；本机此前无 Python 环境。
4. 界限：只改 `app/extraction/**`、`tests/extraction/**`、`data/gold/**`、`reports/extraction/**`、`evidence/week1/B/**`、`progress/week1/B/**`。

## DDL（全队确认整体推迟一天，2026-09-17，见 A 的 PROGRESS）

- B1 OCR 环境与 20 样本格式：9/18 12:00
- B2 5 篇固定样本抽取烟测：9/18 22:00
- B3 20 张金标准和批处理入口：9/19 22:00
- B4 OCR/多模态对照和 evidence pack：9/20 18:00

## 执行日志

### 2026-09-19 13:30
- [x] 分支 `feat/week1-extraction-eval` 快进同步至 main（`b0d73e6`），工作区干净。
- [x] 阅读 README、ARCHITECTURE、TEAM_RULES、`04_接口与数据字典.md`、两份 JSON Schema、B 任务书（DOCX + prompt）、第一周总体手册、独立审查报告（含 P1-07/P1-08/P1-02 对 B 的约束）。
- [x] 接收确认：A 的固定样本 commit `03ec381`（5/5 通过 article_bundle.v1：352508=text、348879=mixed、247919/247746/247586=poster），素材引用为 `private://` + SHA-256，原图待受控交接。
- [x] 建立 progress/week1/B/PROGRESS.md 与 BLOCKED.md。

### 2026-09-19 14:00–15:00（代码切片，逐片验证逐片提交）
- [x] `a4e61a6` feat(extraction): html_rule 文本抽取 + extraction_bundle.v1 组装 + jsonschema 校验（9 项测试）。
- [x] `efcce71` feat(extraction): PaddleOcrAdapter（懒加载、每框 text/confidence/bbox/耗时/错误状态）+ 海报版面规则（间距+人物锚点分块、一帖多人、歧义单块进 review）+ 混合帖双证据（17 项测试）。
- [x] `c54c7e4` test(extraction): 模糊OCR/unknown/证据缺失红绿（Schema 反向验证）/evidence pack（22 项测试）。
- [x] `1bcd9d9` feat(extraction): 批处理 CLI `python -m app.extraction.cli` + 20 样本金标准模板与校验器（P01–P20、SHA-256、学历枚举、空值约束）（95 项全绿）。
- [x] 测试证据：`evidence/week1/B/test-output-extraction.txt`、`test-output-full.txt`。
- [x] B2 烟测（文本路径）：对 A 的 5 篇固定样本跑 CLI——352508(text) 产出记录并过 Schema；348879(mixed) 正文路径产出 evidence pack；3 张海报帖在 OCR 环境/原图到达前如实 failed（见 BLK-1），不伪造结果。

## 环境

- Python 3.11.9（`C:\Users\LEGION\AppData\Local\Programs\Python\Python311`，venv `.venv/`）。
- 已装：pytest、jsonschema。PaddleOCR/PaddlePaddle 待装（安装较重，原图到达后按需安装并在此登记版本）。
- 多模态 API：待用户提供 Key（只放本地 .env），烟测未做。

### 2026-09-19 15:00–16:00（切片 6–8：多模态、评测、OCR 引擎）

- [x] `21f6790` feat(extraction): 多模态适配器——固定提示词要求输出 bundle 兼容 JSON + 逐字段证据；输出先过 JSON 解析（含 ``` 围栏剥离）再过字段词典；超时/坏 JSON/引擎异常如实 failed；关键字段缺失或无证据 → review_required。补齐任务书场景 5 的「模型超时」缺口（8 项测试）。
- [x] `d19c6f1` feat(extraction): 20 样本评测模块——逐样本 0/1 判定汇总，分子/分母可重算；金标准 null 不计分但报告分母并告警（gold_null_but_extracted）；成功率失败样本不从分母删除；平均/P95 耗时、成本（总成本/成功数）；5pp 启用门槛由数据判定（完整记录优先，不可判定时回退字段宏平均并标注 gate_basis）。低于 90% 字段自动列入 below_90_fields（8 项测试）。
- [x] `a1143aa` feat(extraction): PaddleOCR 3.x 兼容（3.7.0 的 predict() 字典结构 rec_texts/rec_scores/rec_polys，保留 2.x 回退）+ 台账桥接导出 `tracker_export.py`（对齐 20样本评测!A14:AB14 列布局，0/1 判定、耗时、成本、标注人、路线 ID 直接粘贴，C 回填 Excel）（3 项测试）。
- [x] `f87c847` fix(extraction): 适配器异常转 failed 不中断批处理；完整记录 0/1 仅在五字段全部可判定时输出（与台账分母语义一致）。
- [x] **B1 环境验证完成**：Python 3.11.9；paddlepaddle 3.3.1 + paddleocr 3.7.0（paddlex 3.7.2）；
  引擎实跑初始化成功（PP-OCRv6_medium_det/rec 模型缓存），证据 `evidence/week1/B/paddle-engine-init.txt`、`env-versions.txt`。
- [x] 台账核对发现（重要，交接 C 时说明）：`20样本评测!AA15` 金标准校验要求 C–G 五字段全部非空，
  与任务书「原文未出现填 null」存在张力——**选 20 样本时应优先选五字段齐全的海报**；
  确有缺失的样本会在 AA 列显示"缺金标准"，如实保留并在评测报告说明。
- 测试全量 114 项通过。

### 2026-09-19 16:30（切片 9：20 样本选样冻结 + 复核队列）

- [x] `d564d26` feat(extraction): 20 样本选样冻结（`data/gold/sample_selection_20.json`）——
  固定 5 篇海报素材必选（P16-P18，3 张已有真实 SHA-256）；其余 17 张从台账 67 张海报
  按「关键词得分降序 + notice_id 升序」确定性选取，无人工挑选空间，模型运行前冻结 ID 集合。
  含 14 张经验分享类 + 6 张公告/活动类（is_announcement 标记，属稀疏金标准难例，如实保留）。
- [x] 评测报告新增 review_queue：低于 90% 的字段列出 wrong_samples 与 invalid_samples
  具体样本 ID（任务 3 硬要求），测试覆盖（115 项全绿）。
- [ ] 待原图：P01-P20 的 image_sha256 回填（受控交接后逐一核对）、20 张人工金标准标注。

## 风险登记（B3 前必须知晓）

- 台账 AA 校验要求金标准五行（C-G）全非空才计"通过"，与任务书「原文未出现填 null」有张力；
  选样已尽量偏向信息齐全的分享类海报，公告类难例若五行不全，将在评测报告中如实说明并交 C 处置。

## 待办（原图/Key 到达后，更新于 16:00）

1. ~~装 paddlepaddle+paddleocr~~ ✅ 已完成（3.3.1 / 3.7.0，引擎初始化验证通过）。
2. 原图到达 → 3 张固定海报 OCR 烟测（补 B2 OCR 路径）+ 选 20 张评测集、冻结哈希、
   **人工标注** gold_20.json（B3，今晚 22:00；标注只能由 B 本人做）。
3. 多模态 Key 放 .env → 脱敏烟测 → `run_evaluation` + `tracker_export` 产出对照报告与台账导入 CSV（B4，明天 18:00）。
