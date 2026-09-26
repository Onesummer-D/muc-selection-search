# 9/24 HTTPS/CAS 部署探测（事实记录）

**记录时间**：2026-09-21 23:50 (UTC+8)
**采集人**：角色A
**目标地址**：81.70.40.146:22（从用户口述 + 之前对话历史记录）
**结论**：
- ✅ 网络层：TCP/22 可达，RTT 11.7 ms
- ✅ DNS：解析到 81.70.40.146
- ❌ 80 / 443 端口拒绝连接（说明 9/24 之前没有任何服务对外）
- ❌ SSH 认证失败（ubuntu + 用户口头提供的密码 `lm@1215`）
- 🔒 状态：阻塞（凭据无效，无法继续部署）

## 一、可达性探测

```python
import socket, time
# TCP/22 (SSH): ok, rtt_ms=11.7, peer=81.70.40.146:22
# TCP/80:    [WinError 10061] 目标主动拒绝
# TCP/443:   timed out（5s 超时）
# DNS:       解析到 81.70.40.146
# 公网对照：api.github.com 200（本地网络出口正常）
```

## 二、SSH 登录尝试

```python
import paramiko
paramiko.SSHClient().connect(
    host="81.70.40.146", port=22,
    username="ubuntu", password="lm@1215",
    timeout=10, auth_timeout=10,
)
# → paramiko.ssh_exception.AuthenticationException: Authentication failed.
```

任意已尝试密码组合：

| 用户名 | 密码 | 结果 |
|--------|------|------|
| ubuntu | lm@1215 | AuthenticationException |

无密钥可用（`look_for_keys=False`；本机 ~/.ssh 无密钥对目标）。

## 三、推论（不构成本文事实，仅作判断）

1. 服务器在线、SSH 端口开放，说明这台机器具备"被登录部署"的基本条件。
2. 用户口头提供的凭据与实际不符——可能记错、可能已改密、可能是另一台机器复用同一公网 IP。
3. 在拿到新凭据/或密钥文件之前，继续部署会进入猜密码盲测，违反任务书 §一「真实 CAS/HTTPS 条件不足时必须保留阻塞记录，不伪造上线结果」。
4. 80/443 端口无服务响应——即便拿到凭据，仍需补：(a) `uvicorn` 起后端、(b) `openssl req -x509` 自签证书、(c) Nginx 反代 80→443→uvicorn、(d) `curl -k https://...` 取证。

## 四、阻塞项细化（供外部提供后继续）

- [ ] 有效 SSH 凭据（用户+密码 或 私钥文件 path）
- [ ] 校园网/家庭网出口对 81.70.40.146:443 的入站策略（防火墙/SG）
- [ ] 域名（即使自签也建议绑一个临时 host，便于回调白名单）
- [ ] CAS 服务端 issuer URL + callback URL（生产 HTTPS 才能真登一次）
- [ ] TLS 证书颁发机构或允许自签（自签场景下 `curl -k` 留证）

## 五、与 blocker.md 的关系

`progress/week2/A/deployment-blocker.md` 当前文本：

> 截至 2026-09-21，仓库没有可核验的公网服务器、域名、TLS 证书或 CAS 回调配置。

升级为：

> 截至 2026-09-21 23:50，仓库已确认一台候选服务器 81.70.40.146 网络可达、SSH 端口开放但凭据无效；缺 §四 列出的 5 项外部资源，仍按阻塞收尾。

## 六、可复现命令

```bash
# 网络可达性
python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('81.70.40.146', 22)); print('tcp/22 ok')"

# SSH 认证
python -c "
import paramiko
s = paramiko.SSHClient()
s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
s.connect('81.70.40.146', 22, 'ubuntu', '<password>')
"
```

未做任何写入、未触动服务器任何文件。
