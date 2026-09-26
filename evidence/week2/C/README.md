# C 证据目录

第二周角色 C 的现场证据。代码测试通过不等于现场证据已接收，本目录逐项登记如下。

## 已归档（2026-09-27）

| 证据 | 文件 | 说明 |
| --- | --- | --- |
| 游客 Network 脱敏 | `guest-network.json` | 真实 HTTP 抓包：published-only、无 source_url/person、review_required/draft 详情 404、个人接口 401、管理接口 403；12 项断言全绿 |
| 删除历史后退出画像 | `history-delete.json` | history_count 2 → DELETE `/api/me/history` → insights 0（U-03）；5 项断言全绿 |
| 无痕零写入 | `incognito-zero-write.json` | `X-Incognito-Mode: 1` 下搜索/对比/导出均不写历史（3 项断言全绿） |
| 跨用户隔离 | `cross-user-isolation.json` | bob 不可见/不可改/不可删 alice 的保存搜索（5 项断言全绿） |
| 移动端截图 | `mobile-390x844-home/results/detail.png` | 手机视口 390×844：首页、结果页（含 QueryPlan 与游客视图提示）、详情弹窗（匿名记录、来源不下发） |
| 平板截图 | `mobile-768x1024-home/results.png` | 768×1024 视口首页与结果页；窄屏单列布局正常，无横向溢出 |

复现命令：`python scripts/week2_c_evidence.py`（自建临时脱敏库 + 回环端口真实 HTTP，断言失败即非零退出）。

## 待人工补齐

- `demo.mp4`（H-03 完整演示录屏）：本机浏览器录制能力不可用，待人工录屏后归档；
  上述截图与 JSON 证据已可支撑 9/27 演示链路复核。
