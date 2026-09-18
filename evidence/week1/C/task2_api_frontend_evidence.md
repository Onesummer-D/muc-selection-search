# 任务2 查询、权限与页面 证据（角色 C）

- 日期：2026-09-18（本地）
- 分支：feat/week1-core-search
- 环境：Python 3.13.15 + Flask 3.1.3；Node v24.15.0 + npm 11.12.1 + Vite 6.4.3 + React 18.3 + TypeScript 5.6

## 交付内容

### 后端（Flask API，附录 G G1：Flask 只提供 API）

| 模块 | 职责 |
|---|---|
| `app/domain/query_plan.py` | QueryPlan 白名单模型（cohort/education/college/major/city/position_or_unit/keywords/page/page_size），`from_dict` 拒绝未知字段 |
| `app/domain/role_policy.py` | guest/student/teacher/admin 三类策略；published-only 查询；`ENABLE_DEV_ROLE_SWITCH` 环境变量保护开发角色开关；`CAMPUS_ORIGINAL_ASSET_ENABLED` 完整海报默认关闭 |
| `app/domain/presenter.py` | RecordPresenter 按角色生成 DTO；guest 删除全部 7 个私有字段与来源 URL；`assert_no_restricted_fields` 防泄漏校验 |
| `app/search/query_parser.py` | 规则解析器：自然语言 → 白名单 QueryPlan（学历/届别/地区/专业/基层意图），意图类停用词不进 keywords；也是模型不可用时的降级路径 |
| `app/search/search_service.py` | 结构化过滤（学历/届别精确、其余包含）+ FTS5 trigram 召回 + 1-2 字中文 LIKE 回退 + 地区别名组（西部/四川等展开到城市）+ 可解释排序（专业5/城市4/岗位4/学院4/学历3/届别2）+ 逐项放宽候选 |
| `app/search/answer_service.py` | 证据包（record_key/notice_id/条件/字段证据/来源/复核状态 + 程序统计）→ 模板化带引用回答；无证据返回"证据不足"；LLM 未配置 → degraded=true 且传统结果照常返回 |
| `app/web/api.py` + `app/web/app.py` | 五个接口 + /healthz + 开发角色开关（关闭时 404）+ 错误映射（ContractViolation→400，越权未发布→404，未知字段→400）；生产同源托管 frontend/dist |
| `app/web/seed.py` | 5 篇文章/7 条记录的脱敏演示数据（4 published + 2 review_required + 1 draft），经正式 BundleImporter 入库 |

### 前端（React 18 + TypeScript + Vite，frontend/）

- 首页：单搜索框 + 传统/AI 分段切换（G3），示例查询一键填入
- 结果页：学历/城市/专业筛选；紧凑列表（核心字段、匹配原因 chips、来源、复核状态徽章、详情入口）
- QueryPlan 面板：白名单条件 chips + 命中原因权重
- AI 回答面板：答案 + 引用列表 + 降级横幅 + 证据不足提示
- 详情弹窗：字段与字段级证据并排表格（值 | 证据文本 | 抽取方式/bbox）；游客显示"来源链接需校内登录"
- 开发角色开关下拉（仅 dev_switch_enabled 时出现）；无结果时逐项放宽按钮
- 民大红 #A20000 品牌色；移动端单列大卡布局（390×844 / 768×1024 媒体查询）
- Vite dev proxy `/api`→Flask:5000；`npm run build` 产物由 Flask 同源托管

## 测试

```
$ python -m unittest discover -s tests/core
Ran 60 tests in 0.170s
OK
```

新增 48 个测试（累计 60，只增不减）：
- test_search.py：白名单未知字段拒绝、解析器规则、published-only、admin 复核队列、结构化过滤+匹配原因、FTS/LIKE 关键词、地区别名、空条件最新记录、无结果放宽候选、分页、README 示例端到端
- test_permissions.py：guest DTO 受限字段为 0（键不存在）、student 完整海报默认关闭（需 CAMPUS_ORIGINAL_ASSET_ENABLED=true）、admin 全量、review_required 仅 admin、角色开关环境变量、能力矩阵
- test_api.py：五接口集成、未知 GET 参数/POST 字段 400、draft 对游客 404 对 admin 200、开发开关关闭 404/开启可切换、healthz 组件状态

## 端到端烟测（python -m app.web.seed data/app.db 后启动 Flask）

```
healthz: {'components': {'database': 'ok', ..., 'llm': 'not_configured'}, 'status': 'ok'}
answer(2026届计算机本科，想看西部基层案例):
  degraded: True | insufficient: False
  answer: 共匹配到 1 条已发布记录（条件：2026届、本科、计算机、西部、基层）。
          工作地点分布：成都 1 条[1] portal-10001-01：学历本科，专业计算机科学与技术，
          去向成都，岗位基层岗位。
  citations: [(1, 'portal-10001-01', 'city', '工作地点 成都')]
search city=西部 → total 4（成都/重庆/绵阳/昆明）
search education=本科&major=软件 → total 1
parse(四川 软件工程) → city=四川, major=软件工程
me → guest ['search', 'view_public_detail', 'view_public_stats']
GET /api/records/{draft_key} (guest) → 404
GET /api/search?salary=1 → 400
POST /api/dev/role（未设环境变量）→ 404
GET / → 200 text/html（React 构建产物由 Flask 同源托管）
```

## 修复记录

1. SQLite 连接 `check_same_thread=False` + RLock 串行化：Flask 请求线程与建连线程不同，首启烟测 500，修复后 60 测试回归通过。
2. 查询解析器停用词：首版把"想看案例"等意图词混入 keywords 造成过度过滤，README 示例查询返回 0 条；加停用词表后端到端命中 1 条。
3. 地区别名组："西部/四川"等省级/大区条件展开到具体城市，否则结构化条件永远无法命中。

## 遗留到任务3/4

- compare/export/stats 接口与对比台 UI（G7 本周主链，任务3 一起做）
- LLM 接入（degraded 路径已就绪）、100 行性能夹具
- LAN 另一台设备实测与录屏（服务已监听 0.0.0.0:5000）
