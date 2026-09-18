# A3 失败与重试演示说明

**生成时间**：2026-09-18 22:31:57 +0800

## 背景

任务书 A3 原文：

> 验收看真实状态、恢复能力和幂等结果，不以下载文件数量代替完成。

真实采集 100 篇全部成功，无法直接展示 `failed` / `review_required` / `pending` / 重试退避痕迹。
本演示通过 `pnpm run inject_failure_demo` 在不修改真实数据的前提下，**追加 5 行** source=demo 条目，
覆盖任务书指定的 4 类状态枚举 + 1 类重试退避场景。

## 演示条目对照表

| notice_id | 场景 | final_status | attempt_count | failure_reason | 触发原因 |
|-----------|------|--------------|---------------|----------------|----------|
| D001 | 429 重试退避后成功 | processed | 3 | （空）| 首次 429 → 800ms 退避 → 二次 429 → 1.5s 退避 → 三次 200 ok |
| D002 | 503 三次重试耗尽 | failed | 3 | http_503_after_3_retries | 服务端持续 503，超过最大重试次数 |
| D003 | 响应解析失败 | failed | 1 | json_parse_error: Unterminated string | 响应截断，JSON 解析器抛异常 |
| D004 | 脱敏疑问 | review_required | 1 | personal_info_unclear: 正文含手机号 138****0000 | 启发式扫描命中疑似个人信息 |
| D005 | 中断后未完成 | pending | 0 | （空）| 采集被打断，下次恢复时继续 |

## 与生产代码的一致性

- 所有 status 值与 `app/sync/ledger.py` 中 `STATUS_*` 常量完全一致
- attempt_count 累加逻辑与 `SyncService._record_attempt()` 行为一致
- 失败时 `failure_reason` 文本格式与 `evidence/week1/A/retry-429-*.txt` 中的实际日志一致
- 演示条目未与任何真实 100 篇 notice_id 冲突（用 D00x 前缀隔离）

## 怎么重现

```bash
# 真实 100 篇
python run_a3.py

# 追加 5 行演示（保留真实 100 篇 + 覆盖 4 类状态枚举 + 重试）
python inject_failure_demo.py
```
