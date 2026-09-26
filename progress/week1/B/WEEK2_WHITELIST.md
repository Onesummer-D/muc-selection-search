# 第二周 B 白名单清单（9/21 交付）

分支：`feat/week2-B-quality`（基于 C 集成基线 `5c1cabc`）
依据：`docs/week2/02_角色B_抽取质量与评测任务书.docx` 第一节目录白名单、`docs/week2/prompts/B_goal.md`

## 允许提交的目录（白名单）

| 目录 | 内容 | 与 C 基线差异 |
|---|---|---|
| `app/extraction/**` | 抽取管线 18 个模块（规则/OCR/多模态/评测/台账导出/选样/金标准构建/等价预标） | **零差异**（C 已在 `5c1cabc` 原样集成 week1 终版） |
| `tests/extraction/**` | 7 个测试文件，55 项测试 | **零差异**；在 C 基线实测 55/55 全绿 |
| `data/gold/**` | 冻结金标准 v2.1、裁决日志、等价裁决表、选样 v2（v1 存档）、校验器 | **零差异** |
| `reports/extraction/**` | 5 篇 bundle + 7 条 evidence pack、评测报告（三口径双 gate）、tracker_import.csv、eval_inputs ×20、eval_raw、成本边界 | **零差异** |
| `progress/week1/B/**` | PROGRESS / BLOCKED / WEEK2_WHITELIST（本文件） | 仅追加本文件 |
| `evidence/week1/B/**` | 测试输出、引擎初始化、烟测证据、环境版本 | **零差异** |

## 禁止触碰（本分支零改动，已核验）

`app/domain/**`、`app/repository/**`、`app/search/**`、`app/web/**`、`app/auth/**`、
`app/sync/**`、`app/datasource/**`、根配置（requirements/.gitignore/.env.example）、
`docs/**`、`schemas/**`、验收台账。核验命令与结果：

```
git diff --name-only HEAD feat/week1-extraction-eval | grep -vE "^(app/extraction|tests/extraction|data/gold|reports/extraction|progress/week1/B|evidence/week1/B)"
→ 全部为 C 集成提交引入的文件（B 分支不含这些改动）
```

说明：禁止整体合并旧 B 分支——本分支从 C 基线建立，extraction 白名单内容经
`git diff` 核验与 week1 终版逐字节一致，无需任何迁移提交。

## 迁移验证记录（2026-09-21）

- `pytest tests/extraction -q`：55 passed（C 基线 + 本分支同结果）
- 金标准冻结状态未动：20 样本集合、SHA-256、gold v2.1、多模态启用门槛均保持 week1 终版
- week1 交付已随 PR #5 合并入 main（ad63eed），C 集成基线包含全部 B 交付

## 本周日程与对应交付

| 日期 | 工作 | 状态 |
|---|---|---|
| 9/21 | 定向迁移核验 + 白名单清单 + 本 PR | ✅ 本文件 |
| 9/22 | 5 篇 bundle/evidence pack 导入 C SQLite 烟测 | 待做 |
| 9/23 | 专业/城市/岗位通用规则修正 | 待做 |
| 9/24 | 同 20 样本/SHA-256/gold 重评 → evaluation_report_v2.json/CSV | 待做 |
| 9/25-26 | 复核队列、授权、保留策略与游客素材检查 | 待做 |
| 9/27 | 归一化口径与"不启用多模态"结论演示讲稿 | 待做 |
