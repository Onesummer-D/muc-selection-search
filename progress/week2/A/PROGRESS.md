# Week2 A 进度

- 2026-09-21：已冻结 `app/auth/provider.py` 的 AuthProvider/CasProvider 契约；已加入 `scripts/backup_sqlite.py`；API 开发角色关闭时仍返回 404。
- 条件式同步接口：`/api/admin/sync`、`/api/admin/sync/status` 已存在，未配置真实 Portal/CAS 时返回 `503 sync_not_configured`，不伪造成功。
- 已收到 LAN 证据：`evidence/week2/A/lan-home.png`、`lan-search.png`、`lan-healthz.png`。三张图分别覆盖首页、传统搜索和 `/healthz`，其中健康检查返回 `status: ok`，数据库与搜索组件为 `ok`。
- 仍待人工补齐：访问时间/设备信息、详情页截图或录屏、备份恢复日志、真实 HTTPS/CAS。外部资源不足时按阻塞记录收尾。
- 2026-09-21 20:30：设备信息与访问时间已补记（ASUS Vivobook S Flip，Windows 11，2026-09-19 20:36，见 evidence/week2/A/lan-verification.md），台账 A-01 与证据索引 E-01 已同步；剩余缺口为详情页截图与 C 接收确认。
- 2026-09-21 21:00：C 确认 LAN 证据已足够接收，无需补详情页截图，A-01 验收项关闭。
- 2026-09-21 21:00：越权验证完成——pytest 30/30（tests/core/test_api.py + test_permissions.py）+ 真实 HTTP 活体验证 4 场景全 PASS（开关关闭 /api/dev/role=404；6 种伪造 header 提权失败；开发开关显式开启才可用且可复位）。证据：evidence/week2/A/role-isolation-live.txt、role-isolation-test-output.txt，复现脚本 run_role_isolation.py。
- 2026-09-22 09:45：AuthProvider/CAS 契约固化落地——`evidence/week2/A/auth-contract.md` 完成 §1-§7（角色白名单/接口/开发开关/越权响应/验证证据/部署要求/变更记录）。台账 A-02 同步指向新证据文件。
