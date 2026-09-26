# A 部署阻塞记录（9/24 升级版）

## 状态结论
截至 2026-09-21 23:50，候选服务器 81.70.40.146 网络层已确认在线（TCP/22 开放、RTT 11.7ms、DNS 正常），但用户口述的 SSH 凭据（ubuntu / `lm@1215`）认证失败。其他 4 项外部资源（域名、有效凭据、回调白名单、真实 CAS issuer）未具备。

按任务书 §一「真实 CAS/HTTPS 条件不足时必须保留阻塞记录，不伪造上线结果」，9/24 不宣称公网 HTTPS/CAS 已上线，保留 LAN 演示与 `/api/admin/sync` 的条件式 503 证据。

## 探测事实（落 evidence/week2/A/deployment-precheck.md）
- TCP/22 通，RTT 11.7ms
- TCP/80/443 无服务（防火墙/未起服务）
- DNS 解析到 81.70.40.146
- paramiko SSH ubuntu+`lm@1215` → `AuthenticationException`
- 公网对照 OK（api.github.com 200），排除本地出口问题

## 阻塞细化（5 项外部资源）
1. 有效 SSH 凭据（重新提供用户名 + 密码，或 SSH 私钥路径）
2. 入站策略：家庭/校园网出口对 81.70.40.146:443 是否放行
3. 域名（自签可也建议有一个 host 用于回调白名单与 evidence 截图）
4. 真实 CAS 服务端：issuer URL、callback 白名单、回跳字段约定
5. TLS 证书：生产 CA / 测试 CA / 自签（自签需在 evidence 显式标注 `-k`）

## 解锁后预计动作（不在本次执行）
- `uvicorn app.web:create_app() --host 127.0.0.1 --port 5000` 起后端（不直接对外）
- `openssl req -x509 ... -keyout key.pem -out cert.pem -days 7` 自签证书（仅测试用）
- Nginx 反代 80→443→uvicorn，`server { listen 443 ssl; location / { proxy_pass http://127.0.0.1:5000; } }`
- `curl -k https://81.70.40.146/healthz` 取证（带 `-k` 标注 + `-v` 输出截图/落盘）
- 把生产开关 `MUC_PRODUCTION=1` 拉起后，再跑一遍 9/22 越权 4 场景，确认 `X-Incognito-Mode` 和 6 类伪造 header 在 HTTPS 上同样被拒
- 落 `evidence/week2/A/deployment-run.txt`，附 plan/precheck/curl 三类原文

## 阻塞对其他角色/任务的影响
- A-04 验收项：本周期内不具备关闭条件，保持阻塞
- 协作手册 9/24 行：「真实证据或阻塞记录」二选一，本次选阻塞
- 9/25 联调：仍以 LAN 演示 + localhost HTTPS（自签 + `-k`）进行，不依赖公网回调
- 9/26 P0 冻结后：如上 5 项补齐，可在冻结窗口内补 9/24 部署；若仍未补齐，按阻塞收尾
