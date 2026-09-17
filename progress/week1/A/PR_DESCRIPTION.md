# Draft PR：feat/week1-portal-sync（角色A 采集与更新）

## 概要

门户采集与增量更新模块：CAS 人工辅助登录、配置化门户客户端、
100 篇采集状态台账、SyncService 增量入口与 Scheduler 单实例调度。
53 项自动化测试全绿，含 429 反向验证红→绿证据。

## 交付对应

| 交付 | 状态 | 证据 |
|---|---|---|
| A1 接口与素材可用性核查 | 待补充真实端点核查记录 | progress/week1/A/PROGRESS.md |
| A2 5篇固定样本 | 待真实采集（工具已就绪） | evidence/week1/A/fixed_samples/ |
| A3 100篇状态台账 | 待真实采集（工具已就绪） | evidence/week1/A/ledger/ |
| A4 Scheduler/SyncService+测试 | ✅ 完成 | evidence/week1/A/test-output.txt |

## 新增依赖（请 C 处理根配置）

- `requests`（HTTP 会话）
- `jsonschema`（Schema 校验，测试与运行均需要）
- `playwright`（仅人工 CAS 登录使用，需 `playwright install chromium`）

## 提交清单

1. `feat(sync): add CAS assisted portal session`
2. `feat(sync): add article bundle fetch`
3. `feat(sync): add resumable article ledger`
4. `feat(sync): add scheduler and sync service`
5. `test(sync): cover retry resume and dedupe`
6. `docs(week1): register role A progress and evidence`

## 验收复现命令

```bash
python -m unittest discover -s tests        # 53/53 OK
# 429 反向验证：
#   evidence/week1/A/retry-429-red.txt / retry-429-green.txt
# 真实采集（人工CAS登录后）：
python -m app.sync.collect_fixed --cas-base-url <CAS> --portal-base-url <门户>
python -m app.sync.run_sync --cas-base-url <CAS> --portal-base-url <门户> --target 100
```

## 界限声明

- 只改动 `app/datasource/**`、`app/sync/**`、`tests/datasource/**`、
  `evidence/week1/A/**`、`progress/week1/A/**`。
- 未提交 Cookie、账号、原始海报、绝对路径或未脱敏响应（已做敏感扫描）。
- BLOCKED.md B-1：门户真实端点待人工确认，真实样本待 CAS 登录后采集。

## 交接

- B：5 篇固定样本 commit 待补（真实采集后回填）。
- C：notice_id 唯一性检查与两次运行前后数量待台账生成后回填。
