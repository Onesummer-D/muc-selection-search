# Week2 A 进度

- 2026-09-21：已冻结 `app/auth/provider.py` 的 AuthProvider/CasProvider 契约；已加入 `scripts/backup_sqlite.py`；API 开发角色关闭时仍返回 404。
- 条件式同步接口：`/api/admin/sync`、`/api/admin/sync/status` 已存在，未配置真实 Portal/CAS 时返回 `503 sync_not_configured`，不伪造成功。
- 待人工证据：另一台 LAN 设备截图/录屏、备份恢复日志、真实 HTTPS/CAS。外部资源不足时按阻塞记录收尾。
