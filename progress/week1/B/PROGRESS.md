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
- [ ] 任务0：安装 Python 3.11+，venv，验证 PaddleOCR 可导入并记录版本，多模态 API 脱敏烟测。
- [ ] 补做 B1/B2（已过期，如实补做并在日志记录实际完成时间，不伪造时间点）。

## 环境

- 待记录：Python 版本、PaddleOCR/PaddlePaddle 版本、模型版本、多模态服务商与型号（Key 只放本地 .env）。
