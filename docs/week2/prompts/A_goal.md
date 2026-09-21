# A Goal：平台、认证、部署与灾备

从 `feat/week2-integration` 建立 `feat/week2-A-platform`。先阅读 `docs/week2/07_第二周数据源与海报主线补充说明.md`。只修改 `app/auth/**`、`app/datasource/**`、`app/sync/**`、`scripts/**`、`evidence/week2/A/**`、`progress/week2/A/**`，除非 C 明确接收接口变更。

在 9 月 21-23 日完成另一台设备 LAN 首页、`/healthz`、搜索、详情复测，固化 AuthProvider/CAS 契约，执行 SQLite 备份/恢复和三类行数校验。同时核对门户详情 HTML/接口是否存在 PDF、XLS、XLSX 附件链接，输出 100 条来源的 88/12 类型对账和附件 manifest；当前采集器只处理正文与图片，不能把未发现的附件写成已采集。9 月 24 日只有在服务器、域名、CAS 回调真实提供时才推进 HTTPS；否则记录外部阻塞，绝不编造 URL。9 月 25-27 日只做跨角色联调、台账、录屏与问题清单。

每次提交必须附运行命令、实际值、证据路径、Commit/PR 和 C 接收确认。不得提交 Cookie、密码、API Key、真实姓名、原始海报或绝对路径。
