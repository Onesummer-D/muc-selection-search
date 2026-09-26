# Week2 C 进度

- 已增加用户表、隐私设置、保存搜索、历史、通知和提醒持久化；默认历史/推荐关闭，保留期固定 90 天。
- 已实现 `/api/saved-searches`、`/api/me/privacy`、`/api/me/history`、`/api/me/insights`、`/api/notifications` 以及管理员发布/撤回审计接口。
- 已加入无痕请求服务端约束、跨用户隔离测试和个人中心/无痕模式前端控件；前端 `npm run build` 通过。

## 2026-09-27：A/B 交付接收与端到端证据

- 接收 A（`feat/week2-A-platform`，f88e52f..1c04f7b）与 B（`feat/week2-B-quality`，604170d..f2fb46e），
  双双合并进 `feat/week2-integration`（合并提交见 `git log --merges -2`），合并后全量回归
  `python -m pytest -q`：**226 passed + 19 subtests**（17 个 setup 报错为本机 Temp 目录权限，
  `--basetemp` 指向仓库内目录后全绿，非代码问题）。
- B-01 接收：导入烟测 5 文章/4 资产/7 记录/51 证据，重复导入幂等（`evidence/week1/B/import-smoke.txt`）。
- B-02/B-04 接收：同 20 样本/SHA-256/gold 复评（f2fb46e），归一化主口径 OCR 完整记录 57.89%（11/19）
  vs 多模态 10.53%（2/19）；裁决口径差 -15.79pp；两种口径均未达 +5pp 门槛，维持"不启用多模态"。
- 端到端证据已补（脚本 `scripts/week2_c_evidence.py`，真实 HTTP + 断言全绿）：
  - `evidence/week2/C/guest-network.json`：游客 published-only、无 source_url/person、
    review_required/draft 详情 404、个人接口 401、管理接口 403（12 项断言）；
  - `evidence/week2/C/history-delete.json`：U-03 删除历史后 `history_count` 2→0，旧记录退出画像（5 项断言）；
  - `evidence/week2/C/incognito-zero-write.json`：`X-Incognito-Mode: 1` 搜索/对比/导出零写入（3 项断言）；
  - `evidence/week2/C/cross-user-isolation.json`：保存搜索跨用户隔离，bob 改/删 alice 资源 404（5 项断言）。
- 移动端截图已归档：`evidence/week2/C/mobile-390x844-{home,results,detail}.png`、
  `mobile-768x1024-{home,results}.png`（窄屏单列布局正常，`scrollWidth` 375 < 390 无横向溢出）。
- 台账回填：`docs/week2/05_第二周验收台账.xlsx` A/B/C/H/U/总览/20样本复评/证据索引各 sheet 已按上述实际值与接收确认更新（C 为台账唯一提交人）。

## 遗留待办

- 完整演示录屏（H-03/E-09 的 `demo.mp4`）：本机浏览器录制能力不可用（截图表面准备超时），
  待人工录屏补齐；截图与 API 证据已可支撑 9/27 演示。
- 附件闭环：A 未交付附件 manifest（88/12 对账文档已在 README/07 号说明落地，但无附件端点与下载权限），
  按 07 号说明登记为阻塞，不伪造附件结果。
- W2-01 第一周四元组：第一周台账已回填终版（`c/ledger-backfill`，PR #9），9/27 合并 PR #9 后闭环。
