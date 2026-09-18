# 角色 C 目标任务书

在执行 agent 那边输入 `/goal `，粘贴下面整段并发送。

```text
你是角色C，也是集成人。这份任务书是唯一任务来源；没人能在执行中答疑，拿不准的写进progress/week1/C/BLOCKED.md并继续其他工作。换会话先读progress/week1/C/PROGRESS.md。目标是在2026-09-20 23:59前把A和B的输出整合为本机及局域网可访问的Flask API、React/Vite和SQLite检索系统，并完成验收证据及云端HTTPS部署清单。冲突时，数据安全与证据真实性 > 主链可运行 > 查询正确 > 页面细节。硬约束不可改，建议可调整但要记录。

## 我替领导拍的板
- 技术栈固定为Flask API + React + TypeScript + Vite，不得改回Jinja2或换成Vue。现有静态原型只作交互迁移参考。
- 视觉采用校园官方可信感与Answer Engine轻交互，品牌强调色使用民大红#A20000，禁用墨绿主色、蓝紫AI光、大面积渐变和玻璃拟态。桌面紧凑列表，移动端单列大卡。
- SQLite使用FTS5；中文短词保留归一化LIKE回退｜本机已验证SQLite 3.53.1支持FTS5 trigram，但队友机器必须在任务0复测。
- 最终部署路线固定为云服务器或学校服务器+HTTPS，并保留LAN灾备。本周硬门槛是本机与另一台LAN设备可访问；同时提交服务器、域名、反向代理、Let’s Encrypt证书和自动续期清单。没有公网资源不判P0。
- 第一周不启用Embedding，当前项目不做语义检索。自然语言查询走白名单QueryPlan、结构化/FTS5/LIKE检索和可选LLM带引用总结。
- 自然语言查询只生成白名单QueryPlan；模型不可用时自动转关键词，不允许生成SQL。
- 正式认证目标为CAS/SSO；开发角色开关只在显式开发环境变量下启用，生产构建不得出现。完整海报默认关闭，只有学校授权后才由服务端策略开关开放。
- 实现对比台、四Sheet Excel/CSV导出、当前结果可视化；为第二周的保存搜索/站内提醒、隐私中心和无痕模式冻结接口。搜索历史默认关闭，用户开启后保存90天。

## 界限
只允许修改app/domain/**、app/repository/**、app/search/**、app/web/**、frontend/**、schemas/**、docs/**、tests/core/**、evidence/week1/C/**、progress/week1/C/**和根配置。A、B目录只读；发现接口不合只在其PR提出，不直接修。C是docs/week1/05_本周验收台账.xlsx唯一提交者，每日至少两次把A/B角色PROGRESS或PR清单中的值回填；不得让多人同时提交该二进制文件。不得把姓名、头像、二维码、联系方式、会议入口、原始海报路径、Cookie、密钥或未脱敏数据库返回公开接口。不得新增框架、数据库或权限模型。

## 现状与任务0
先读README、ARCHITECTURE、TEAM_RULES、接口字典和两份Schema。运行git status --short、git log -1 --oneline、python --version；在内存SQLite创建FTS5 trigram表并记录结果。确认分支feat/week1-core-search。把目标、顺序、最大风险写进不超过10行的progress/week1/C/PROGRESS.md。若环境不支持trigram，保留FTS5 unicode61加归一化LIKE，记录差异，不更换数据库。

## 任务1 契约与存储
在9月17日12:00前冻结数据字典和Schema。建立articles、assets、experience_records、evidence、processing_events；notice_id与record_key唯一，一帖多人。导入重复bundle必须更新而不增行。为null、review_required、failed和证据关系写测试。故意重复导入一次，证明总数不增加。

## 任务2 查询、权限与页面
在frontend中用React、TypeScript和Vite迁移现有原型，保留首页分段搜索、筛选、结果、详情、QueryPlan、匹配原因、复核状态和证据并排视图。开发环境用Vite代理/api，生产构建与Flask同源。实现GET /api/search、POST /api/query/parse、POST /api/query/answer、GET /api/records/{record_key}和GET /api/auth/me。用服务端RolePolicy/Presenter区分guest、student/teacher、admin；处理状态与visibility分离，guest和student/teacher查询只返回人工确认且published的记录，review_required仅进入admin复核队列和管理员演示。按Guest Visibility Matrix验证全部受限字段为0；校内完整海报仍默认关闭。开发角色开关必须受环境变量保护，生产模式访问返回404或禁用。拒绝未知查询字段。空条件显示最新记录，无结果允许逐项放宽。不得只在前端隐藏受限字段。

## 任务3 Evidence-RAG整合与性能
先导入A的5篇article bundle，再导入B的extraction bundle和evidence pack。实现“自然语言需求→白名单QueryPlan→证据检索→带字段证据引用的结果或回答”闭环；无证据返回“证据不足”，模型关闭时返回明确degraded状态且传统查询仍成功。建立100行脱敏性能夹具，运行至少30次普通查询，记录最大值和P95，均须低于1秒。反向验证未知字段、越权资源和无证据回答；还原后全套测试通过。

## 任务4 演示与发布
提供GET /healthz并用host 0.0.0.0完成另一台设备的局域网验证，记录环境变量、日志、数据库备份和访问说明。提交云服务器/学校服务器、域名、反向代理、HTTPS证书、自动续期和LAN灾备部署清单；公网资源已就绪时可提前部署，但不是本周通过前提。用390×844和768×1024视口验证首页、筛选、详情、证据展开和角色切换，无横向溢出且触控可用。按总体手册流程录屏；执行敏感文件扫描。每天push，建立Draft PR；先合A，再合B，最后处理适配层。9月20日15:00功能冻结，之后只修P0/P1。提交用feat(search)、feat(web)、test(core)、docs(week1)。

## 规矩
不得skip/todo、放宽1秒阈值、用静态假结果代替数据库、删除失败状态、在前端假装脱敏、mock掉Repository做端到端验收、修改A/B证据或用|| true。测试数只增不减，main必须可运行。同一验收失败3次即停该项并记录。

## 完成条件
1. 固定5篇真实脱敏样本跑通采集结果、Evidence-RAG到页面，100行夹具30次查询均小于1秒；模型开启、模型关闭、证据缺失、来源证据、复核状态和幂等导入可现场复现。
2. 本机与LAN访问、健康检查、三角色权限、两个移动视口和云端HTTPS部署清单均有证据，guest响应敏感字段为0，所有合并均有PR和队友检查。progress/week1/C/BLOCKED.md必须提交，没问题也写“无”；必须贴实际命令输出和反向验证红到绿证据，或连续3轮仍受上游阻塞后如实交卷。
```
