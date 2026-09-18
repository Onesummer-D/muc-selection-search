# 任务3（收尾）性能基准与 P1 接口 证据（角色 C）

- 日期：2026-09-18（本地）
- 分支：feat/week1-core-search

## 性能基准（任务书硬阈值：100 行夹具，≥30 次普通查询，max 与 P95 均须 < 1s）

夹具：20 篇文章 × 5 条记录 = 100 条 experience_records（一帖多人），全部虚构脱敏数据，
经正式 BundleImporter 入库；约 60 条 published / 30 条 draft / 10 条 review_required，
覆盖 guest 与 admin 两条查询路径。基准走 Flask test_client 完整 HTTP 链路
（参数校验 → 检索 → 角色 DTO 序列化），不含夹具导入时间。

```
$ python -m app.web.perf_fixture
=== 任务3 性能基准（100 行夹具，HTTP 全链路） ===
查询次数: 32
最大值: 2.5 ms
P95: 1.5 ms
平均: 1.2 ms
最慢查询:  (2.5 ms)
夹具规模: {'records': 100, 'articles': 20, 'visible_default': 60}
阈值: max < 1000ms 且 P95 < 1000ms -> PASS
exit=0
```

结论：max 2.5ms、P95 1.5ms，余量约 400 倍。查询集覆盖空条件、单条件、
组合条件、关键词（FTS/LIKE）、分页、大页容量。回归测试 tests/core/test_perf.py
将同一断言固化进测试套件，防止后续改动劣化性能。

## P1 接口（接口字典 6.1，本周冻结）

| 接口 | 行为 | 约束落实 |
|---|---|---|
| `GET /api/search/stats` | 当前查询+当前角色可见记录的聚合（学历/城市/届别分布、带证据数） | 只统计可见记录，不泄露隐藏分组；review_status 分布仅 admin 返回 |
| `POST /api/compare` | 按 record_keys 返回角色完整 DTO（含证据），最多 4 条 | 超过 4 条 400；不存在/越权 → 404 不暴露存在性；guest DTO 无受控字段 |
| `GET /api/export?format=csv\|xlsx` | 导出当前查询全量匹配 | CSV 扁平公开字段（游客无来源链接列）；XLSX 固定四 Sheet：搜索结果、字段证据、来源文章、导出说明；导出说明含脱敏声明与查询条件 |

依赖变更：新增 openpyxl（XLSX 生成）。理由：接口字典明确要求四工作表 XLSX，
无法在不引入依赖的前提下正确生成；openpyxl 为纯库非框架，符合 TEAM_RULES 边界，
在此 PR 说明中记录（由 C 维护根配置）。

## 前端（React/TS/Vite）

- 结果卡片增加"对比"勾选（最多 4 条，超限禁用），工具栏"对比（n）"按钮打开对比台弹窗
- 对比台：字段行 × 记录列，含证据文本、来源、证据条数；只展示当前角色可见内容
- 工具栏"导出 CSV / 导出 Excel"按钮：携带当前查询条件调用 /api/export
- 结果页"城市分布"横条（当前查询、当前角色可见）；AI 模式不显示统计（无传统结果集）

## 测试

```
$ python -m unittest discover -s tests/core
Ran 88 tests in 0.622s
OK
```

新增 13 个测试（75 → 88）：test_perf.py（性能阈值回归）+ test_p1.py
（stats 角色可见性与查询联动、compare 限额/越权/404、export CSV 列与 BOM、
XLSX 四 Sheet 与脱敏声明、非法 format 400、未知参数 400）。

## 接口烟测（服务运行中）

```
GET /api/search/stats?city=西部 → total=4, distributions{city:{成都1,昆明1,绵阳1,重庆1}}
POST /api/compare {record_keys:[portal-10001-01, portal-10001-02]} → 200 两条角色 DTO
GET /api/export?format=csv  → 200 text/csv
GET /api/export?format=xlsx → 200 application/vnd.openxmlformats-...sheet
GET /healthz → {"components":{"database":"ok","llm":"configured","search":"ok"},"status":"ok"}
```
