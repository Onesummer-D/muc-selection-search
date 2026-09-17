# Draft PR：feat/week1-portal-sync（角色A 采集与更新）

## 概要

门户采集与增量更新模块：CAS 人工辅助登录、配置化门户客户端（已适配真实接口）、
100 篇采集状态台账、SyncService 增量入口与 Scheduler 单实例调度。
67 项自动化测试全绿，含 429 反向验证红→绿证据。

## 交付对应

| 交付 | 状态 | 证据 |
|---|---|---|
| A1 接口与素材可用性核查 | ✅ 完成（真实接口已确认并适配） | evidence/week1/A/endpoint-probe.json、progress/week1/A/PROGRESS.md |
| A2 5篇固定样本 | ✅ 完成（5/5 通过校验，经验分享类） | evidence/week1/A/fixed_samples/*.json + REPORT.json |
| A3 100篇状态台账 | 待真实采集（工具已就绪） | evidence/week1/A/ledger/ |
| A4 Scheduler/SyncService+测试 | ✅ 完成 | evidence/week1/A/test-output.txt |

## 真实接口结论（A1）

- 列表：`POST https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage`
  表单 `currentPage/pageSize/type/searchValue/comsys_random_t`，响应 `datas.tables`；
- 就业信息栏目 `type=10`；无独立详情 JSON 接口（`readNotice` 仅标记已读），
  正文在列表行 `notice_content`（HTML）；登录走 ZFCA（`ca.muc.edu.cn/zfca`）。

## A2 固定样本构成说明

- 就业信息栏目选调相关 20 篇中经验分享类 13 篇优先入选；
- 实际构成 **4 海报 + 1 混合**（理想 2文本/2海报/1混合）：本栏目经验分享类内容
  以整篇海报为主，纯文本帖均为行政通知，为满足"经验分享类"要求保留真实构成；
- 海报原图（含真实 SHA-256）在仓库外受控目录，交接 B 走受控渠道，bundle 内只含
  `private://` 引用与摘要。

## 新增依赖（请 C 处理根配置）

- `requests`（HTTP 会话）
- `jsonschema`（Schema 校验，测试与运行均需要）
- `playwright`（仅人工 CAS 登录使用，需 `playwright install chromium`）

## 验收复现命令

```bash
python -m unittest discover -s tests        # 67/67 OK
# 429 反向验证：
#   evidence/week1/A/retry-429-red.txt / retry-429-green.txt
# 固定样本（候选池缓存，无需登录）：
python -m app.sync.collect_fixed --from-pool
# 真实采集（人工CAS登录后）：
python -m app.sync.collect_fixed --cas-base-url https://ca.muc.edu.cn/zfca --portal-base-url https://my.muc.edu.cn
python -m app.sync.run_sync --cas-base-url https://ca.muc.edu.cn/zfca --portal-base-url https://my.muc.edu.cn --target 100
```

## 界限声明

- 只改动 `app/datasource/**`、`app/sync/**`、`tests/datasource/**`、
  `evidence/week1/A/**`、`progress/week1/A/**`。
- 未提交 Cookie、账号、原始海报、绝对路径或未脱敏响应（已做敏感扫描）；
  `.env` 已被 .gitignore 忽略。

## 交接

- B：5 篇固定样本见 `evidence/week1/A/fixed_samples/`（commit `03ec381`）；
  原图 + SHA-256 走受控渠道，联系角色 A 获取。
- C：notice_id 唯一性检查与两次运行前后数量待 A3 台账生成后回填。
