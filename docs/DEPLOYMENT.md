# 部署与 HTTPS 执行清单

本项目最终路线固定为“云服务器或学校可用服务器 + HTTPS”，同时保留一台电脑上的局域网灾备。第一周的硬验收只要求本机和同一局域网另一台设备可访问 React 页面、Flask API 与 `/healthz`；公网资源就绪后再完成正式 HTTPS。

## 1. HTTPS 证书是什么

HTTPS 证书是一份由浏览器信任的证书机构签发的数字凭证。它把域名和服务器公钥绑定起来，主要解决两件事：浏览器确认自己连接的是该域名对应的服务器；浏览器和服务器之间的 Cookie、CAS 票据、查询内容及返回结果经过加密传输。

证书不是域名，也不是服务器。正式部署至少需要：一台有公网入口的服务器、一个解析到该服务器的域名、开放的 80/443 端口，以及可自动续期的证书。建议使用免费的 Let’s Encrypt 证书，并通过 Certbot 或等价工具自动续期。

CAS 回调地址必须使用最终 HTTPS 域名，并在学校 CAS 侧登记为允许的 service URL。未获得学校对接参数前，不得用爬虫、保存密码或绕过验证码来伪装认证。

## 2. 第一周 LAN 验收

- Flask 监听受控的局域网地址，开发调试信息关闭。
- React/Vite 构建产物由同一站点提供，API 使用同源 `/api`。
- 本机和另一台局域网设备访问首页、传统查询、详情和 `/healthz`。
- `/healthz` 返回应用版本、数据库和检索组件状态，不返回绝对路径、密钥或异常堆栈。
- Windows 防火墙只开放演示所需端口；演示结束后关闭临时规则。
- 截图或录屏记录两台设备、访问地址、commit、时间和测试结果。

## 3. 正式 HTTPS 部署

推荐链路如下：

```text
浏览器
  -> HTTPS 443 / Nginx
  -> React 静态构建
  -> /api 与 /healthz 反向代理到 Flask 应用
  -> SQLite 与受限素材目录
```

发布前逐项确认：

- 服务器与域名负责人明确，DNS 已指向服务器。
- Nginx 或等价反向代理只公开 80/443；80 自动跳转 443。
- Flask 不直接暴露到公网，生产环境关闭 debug 和开发角色开关。
- Let’s Encrypt 证书签发成功，浏览器无证书警告，自动续期测试通过。
- `Secure`、`HttpOnly`、`SameSite` Cookie 属性按 CAS 流程配置，密钥只放环境变量或受控密钥存储。
- `CAMPUS_ORIGINAL_ASSET_ENABLED=false`，学校书面授权前不开放完整海报。
- 数据库、受限素材和备份不位于 Web 静态目录，日志不记录 CAS ticket、Cookie、姓名或查询敏感内容。
- HTTPS 首页、CAS 登录与退出、三角色权限、传统检索、模型降级、导出和 `/healthz` 均已复测。
- 保留 LAN 灾备启动方式、最新脱敏数据库快照和回退版本。

## 4. 不具备公网条件时

没有服务器、域名或学校 CAS 配置时，第一周按 LAN 验收，不得编造公网地址或把自签名证书截图写成正式通过。把缺失资源、负责人和预计完成时间记录到 `progress/week1/C/BLOCKED.md`，演示时明确“正式 HTTPS 待资源到位”。

## 5. 命令级执行手册（服务器资源到位后照此执行）

### 5.1 服务器准备（Ubuntu 22.04/24.04）

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
sudo ufw allow 80,443/tcp && sudo ufw enable
# 创建运行账号与目录（数据库和受限素材不放 Web 静态目录）
sudo useradd -r -s /usr/sbin/nologin xuandiaoyan
sudo mkdir -p /opt/xuandiaoyan /var/lib/xuandiaoyan /etc/xuandiaoyan
```

### 5.2 应用发布

```bash
# 服务器上拉取 main（合并后），构建前端
git clone https://github.com/Onesummer-D/muc-selection-search.git /opt/xuandiaoyan/app
cd /opt/xuandiaoyan/app/frontend && npm ci && npm run build
python3 -m venv /opt/xuandiaoyan/venv
/opt/xuandiaoyan/venv/bin/pip install flask openpyxl gunicorn
# 数据库与密钥
python3 -m app.web.seed /var/lib/xuandiaoyan/app.db
```

生产环境变量只放 `/etc/xuandiaoyan/env`（root:root 600），至少包含：

```text
APP_ENV=production
SECRET_KEY=<openssl rand -hex 32 生成>
ENABLE_DEV_ROLE_SWITCH=false          # 生产必须 false
CAMPUS_ORIGINAL_ASSET_ENABLED=false   # 学校书面授权前必须 false
DATABASE_URL=/var/lib/xuandiaoyan/app.db
LLM_PROVIDER=deepseek
LLM_API_KEY=<由负责人从受控存储注入，不入库>
```

### 5.3 systemd 常驻（Gunicorn，Flask 只监听本机回环）

```ini
# /etc/systemd/system/xuandiaoyan.service
[Unit]
Description=xuandiaoyan Flask API
After=network.target

[Service]
User=xuandiaoyan
EnvironmentFile=/etc/xuandiaoyan/env
WorkingDirectory=/opt/xuandiaoyan/app
ExecStart=/opt/xuandiaoyan/venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 \
  "app.web.app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now xuandiaoyan
curl -s http://127.0.0.1:8000/healthz   # 本机自检
```

### 5.4 Nginx 反向代理 + 静态资源

```nginx
# /etc/nginx/sites-available/xuandiaoyan
server {
  listen 80;
  server_name <你的域名>;
  return 301 https://$host$request_uri;
}
server {
  listen 443 ssl;
  server_name <你的域名>;
  root /opt/xuandiaoyan/app/frontend/dist;
  index index.html;

  location /api/     { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
  location /healthz  { proxy_pass http://127.0.0.1:8000; }
  location / { try_files $uri /index.html; }   # SPA 回落
}
```

### 5.5 证书签发与自动续期

```bash
sudo certbot --nginx -d <你的域名>          # 签发并自动写 443 配置
sudo certbot renew --dry-run               # 续期演练必须通过
systemctl list-timers | grep certbot       # 确认自动续期定时器存在
```

### 5.6 数据库备份

```bash
# /etc/cron.daily/xuandiaoyan-backup —— SQLite 在线备份，保留 14 天
sqlite3 /var/lib/xuandiaoyan/app.db ".backup /var/backups/xuandiaoyan/app-$(date +\%F).db"
find /var/backups/xuandiaoyan -name 'app-*.db' -mtime +14 -delete
```

### 5.7 LAN 灾备（任一成员电脑即可启动）

```bash
python -m app.web.seed data/app.db        # 刷新演示库（可选）
python -c "from app.web.app import create_app; create_app().run(host='0.0.0.0', port=5000)"
# Windows 防火墙放行 5000（演示后删除规则）：
# netsh advfirewall firewall add rule name="xuandiaoyan-demo" dir=in action=allow protocol=TCP localport=5000
# 同一局域网设备访问 http://<本机内网IP>:5000 与 http://<本机内网IP>:5000/healthz
```

LAN 灾备只服务演示兜底：数据用最近一次脱敏快照，不承担公网流量，不开启开发角色开关以外的任何生产配置。

### 5.8 上线前最后一遍核对

- `curl -I https://<域名>` 无证书警告，HTTP 全部 301 到 HTTPS
- 三角色 + 传统检索 + AI 回答 + 导出 + `/healthz` 全链路复测
- `ENABLE_DEV_ROLE_SWITCH=false` 时 `POST /api/dev/role` 返回 404
- 敏感文件扫描通过（任务4 统一执行），备份可恢复
