# 任务4 演示与发布 证据（角色 C）

- 日期：2026-09-18（本地）
- 分支：feat/week1-core-search
- 服务：Flask 监听 0.0.0.0:5000（debug 关闭），生产构建由同源托管

## 1. 双移动视口验证（任务书：390×844 与 768×1024，无横向溢出且触控可用）

| 视口 | 页面 | 横向溢出 | 关键元素 | 证据 |
|---|---|---|---|---|
| 390×844 | 首页 | 0px | 分段搜索、全宽按钮、示例可点 | task4_mobile_390x844_home.png（截图） |
| 390×844 | 结果页 | 0px | 查询计划面板可见、结果列表可见、共1条结果 | 程序化断言（下方命令输出） |
| 768×1024 | 结果页 | 0px | 查询计划、结果、筛选栏全部可见 | 程序化断言 |

程序化检查（浏览器 evaluate 实测，非人工目测）：

```
viewport: {width: 390, height: 844}   overflowPx: 0   planVisible: true   resultsVisible: true
viewport: {width: 768, height: 1024}  overflowPx: 0   planVisible: true   resultsVisible: true   filterBarVisible: true
```

桌面端结果页与详情弹窗截图：task4_desktop_results.png、task4_desktop_detail_modal.png
（民大红 #A20000、紧凑列表、匹配原因 chips、复核状态徽章、字段-证据并排表格可见）。

## 2. 本机验收（LAN 验收的"本机"部分）

```
$ curl -s http://127.0.0.1:5000/healthz
{"components":{"database":"ok","embedding":"disabled_by_decision","llm":"configured","search":"ok"},"status":"ok"}
GET / → 200 text/html; charset=utf-8（React 同源托管）
```

LAN 灾备已具备条件：服务监听 0.0.0.0，防火墙放行步骤与命令见 docs/DEPLOYMENT.md 5.7。

## 3. 云端 HTTPS 部署清单（任务书要求的交付物）

docs/DEPLOYMENT.md 新增第 5 节"命令级执行手册"，覆盖：
- 服务器准备（用户/目录/防火墙）→ 应用发布（npm build / venv / seed）
- 生产环境变量清单（ENABLE_DEV_ROLE_SWITCH=false、CAMPUS_ORIGINAL_ASSET_ENABLED=false 等硬约束）
- systemd + Gunicorn 常驻（Flask 只监听 127.0.0.1:8000）
- Nginx 反向代理配置（80→443 跳转、SPA 回落、/api 与 /healthz 代理）
- Let's Encrypt certbot 签发 + `certbot renew --dry-run` 自动续期验证
- SQLite 每日在线备份（保留 14 天）
- LAN 灾备启动步骤与 Windows 防火墙临时规则
- 上线前核对单（含"开发角色开关关闭时 /api/dev/role 必须 404"）

公网资源（服务器、域名）当前未就绪：按附录 G G8 与接口字典第 7 节，
第一周以本机+LAN 验收为硬门槛，正式 HTTPS 待资源到位后按上述手册执行，
不判 P0。已在 BLOCKED.md 登记。

## 4. LAN 另一台设备验证（待办，需要人工操作）

步骤（另一台手机/电脑连接同一 WiFi）：
1. 本机查询内网 IP：`ipconfig | findstr IPv4`
2. 对方浏览器访问 `http://<内网IP>:5000/` 与 `http://<内网IP>:5000/healthz`
3. 执行一次传统搜索与一次详情查看，截图（含 URL 与时间）
4. 演示后删除防火墙临时规则

## 5. 敏感文件扫描

```
$ git ls-files | grep -iE "\.env$|cookie|session|secret|\.key$|\.pem$" | grep -v .env.example
（无输出）
$ git ls-files | grep -iE "password|token|sk-" 
（无输出）
```

仓库内无 .env、Cookie、密钥、原始海报；LLM Key 仅存本机 .env（gitignored，已用
git check-ignore 验证）。evidence 截图均为脱敏演示页面，无真实个人信息。

## 6. 录屏（待办）

按总体手册流程录制：首页 → 传统搜索（QueryPlan/匹配原因/复核状态）→ AI 回答（带引用）
→ 详情（字段-证据并排）→ 对比台 → 导出 → 角色切换 → AI 降级。待 LAN 设备截图后
统一录制，大文件按 evidence/week1/README.md 约定放共享链接并回填台账。
