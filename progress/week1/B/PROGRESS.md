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

## 待办（原图/Key 到达后）

1. 装 paddlepaddle+paddleocr，登记版本，跑 3 张固定海报 OCR 烟测（补 B2 OCR 路径）。
2. 选 20 张评测集、冻结哈希、人工标注 gold_20.json（B3，今晚 22:00）。
3. OCR vs 多模态对照评测与报告（B4，明天 18:00）。
