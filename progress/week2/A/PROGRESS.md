# Week2 A 进度

- 2026-09-21：已冻结 `app/auth/provider.py` 的 AuthProvider/CasProvider 契约；已加入 `scripts/backup_sqlite.py`；API 开发角色关闭时仍返回 404。
- 条件式同步接口：`/api/admin/sync`、`/api/admin/sync/status` 已存在，未配置真实 Portal/CAS 时返回 `503 sync_not_configured`，不伪造成功。
- 已收到 LAN 证据：`evidence/week2/A/lan-home.png`、`lan-search.png`、`lan-healthz.png`。三张图分别覆盖首页、传统搜索和 `/healthz`，其中健康检查返回 `status: ok`，数据库与搜索组件为 `ok`。
- 仍待人工补齐：访问时间/设备信息、详情页截图或录屏、备份恢复日志、真实 HTTPS/CAS。外部资源不足时按阻塞记录收尾。
- 2026-09-21 20:30：设备信息与访问时间已补记（ASUS Vivobook S Flip，Windows 11，2026-09-19 20:36，见 evidence/week2/A/lan-verification.md），台账 A-01 与证据索引 E-01 已同步；剩余缺口为详情页截图与 C 接收确认。
- 2026-09-21 21:00：C 确认 LAN 证据已足够接收，无需补详情页截图，A-01 验收项关闭。
- 2026-09-21 21:00：越权验证完成——pytest 30/30（tests/core/test_api.py + test_permissions.py）+ 真实 HTTP 活体验证 4 场景全 PASS（开关关闭 /api/dev/role=404；6 种伪造 header 提权失败；开发开关显式开启才可用且可复位）。证据：evidence/week2/A/role-isolation-live.txt、role-isolation-test-output.txt，复现脚本 run_role_isolation.py。
- 2026-09-22 09:45：AuthProvider/CAS 契约固化落地——`evidence/week2/A/auth-contract.md` 完成 §1-§7（角色白名单/接口/开发开关/越权响应/验证证据/部署要求/变更记录）。台账 A-02 同步指向新证据文件。
- 2026-09-21 23:20：SQLite 脱敏备份/恢复落地——`scripts/backup_sqlite.py`（在线热备 + 6 字段清空 + 禁字面量扫描 + manifest 可选）+ `scripts/restore_sqlite.py`（SHA + 三类行数校验 + `--dry-run` / `--allow-overwrite`）；端到端在 `data/app.db`（5/7/11）→ 模拟破坏（3/4/5）→ 恢复到 `data/app-restored.db`（5/7/11，SHA `b343c3b4…077d076` 与备份一致），6 个敏感字段全 NULL，非敏感字段保留；篡改检测退出码 2 + 错误路径退出码 3。证据：`evidence/week2/A/backup-recovery.md` + `_artifacts/step1-step6.txt`，A-03 验收项同步指向新文件。`.gitignore` 增加 `evidence/**/_artifacts/*.db` / `*.manifest.json` 防止原始库或备份误提交。
- 2026-09-21 23:50：9/24 HTTPS/CAS 部署探测——候选服务器 81.70.40.146 TCP/22 通（RTT 11.7ms，DNS 正常），但 `ubuntu + lm@1215` SSH 凭据被服务端拒绝（`AuthenticationException`）；TCP/80/443 无服务。按任务书 §一「真实 CAS/HTTPS 条件不足时必须保留阻塞记录，不伪造上线结果」原则，本周期不宣称公网 HTTPS/CAS 已上线。证据：`evidence/week2/A/deployment-precheck.md`（探测事实 + 5 项外部资源缺失清单 + 解锁后预计动作）。`progress/week2/A/deployment-blocker.md` 同步升级为 9/24 版本（细化 5 项外部资源 + 解锁后动作清单 + 对其他角色影响）。A-04 验收项保持阻塞状态。
