# AuthProvider / CAS 契约固化（9/22 任务交付）

> 冻结日期：2026-09-22
> 适用分支：`feat/week2-A-platform`
> 关联台账：A-02（开发角色开关关闭时 `/api/dev/role=404`）+ A-02 关联证据

本文件是第二周 A 角色的**身份与权限契约**的冻结版，所有 B/C 角色集成时以本文件为准，**接口签名/语义后续变更须重新走契约评审**。

## 1. 角色（Role）白名单

| Role | 说明 | 适用场景 |
|---|---|---|
| `guest` | 未登录访问者 | 公开已发布数据浏览 |
| `student` | 校内登录本科生/研究生 | 私有搜索/对比/导出/CAS 原作下载（受隐私开关控制） |
| `reviewer` | 内容审核 | 可看 review_required 记录、不能发布/撤回 |
| `admin` | 管理员 | 发布/撤回/管理审计日志 |

`role_policy.ROLES` 为上述 4 个；其他值（含 `superadmin`/`root`/`user` 等）一律 `normalize_role(...)` 归一到 `guest`，**不抛错**——前端/客户端不能伪造提权。

## 2. AuthProvider / CasProvider 接口

```python
@dataclass(frozen=True)
class AuthIdentity:
    subject: str           # CAS/SSO 唯一下发身份（不可伪造）
    role: str               # 上表 4 选 1
    authenticated: bool    # True 表示已通过 CAS/SSO 验证

class AuthProvider(Protocol):
    def current_identity(self) -> AuthIdentity | None: ...
    def login_url(self, next_url: str = "/") -> str: ...

class CasProvider:           # 生产适配器占位
    def __init__(self, login_endpoint: str | None = None): ...
    def current_identity(self) -> AuthIdentity | None: ...
    def login_url(self, next_url: str = "/") -> str: ...
```

**约束（不可变条款）**：

1. 应用层只依赖 `subject / role / authenticated` 三个字段；**不读取客户端 header 充当认证凭据**。
2. `login_url(...)` 必须由服务端生成，**不接受任何客户端拼接**（如 `?ticket=` / `Authorization:` 等）。
3. `CasProvider` 缺端点时 `login_url(...)` 必须显式抛 `RuntimeError("CAS_PROVIDER_NOT_CONFIGURED")`，**不返回 200 + 假登录地址**。
4. 生产模式下 `CasProvider.current_identity()` 永远返回 `None`，由前端跳 `login_url` 走真正的 CAS 流程。

## 3. 开发角色开关（Dev Role Switch）

仅当环境变量 `ENABLE_DEV_ROLE_SWITCH=true` 时启用，**生产必须关闭**：

| 行为 | 开关关闭（生产） | 开关开启（开发） |
|---|---|---|
| `POST /api/dev/role` | **404**（不暴露接口存在性） | 200，校验 `role ∈ ROLES`，写 session |
| `DELETE /api/dev/role` | **404** | 200，session 清空 |
| `X-Demo-User` header | 被忽略（伪造 header 无效） | 作为 subject（80 字符截断，空则降级 `demo-{role}`） |
| `X-Role` / `X-Forwarded-User` / `X-Remote-User` / `Authorization` | 全部被忽略 | 全部被忽略（不充当认证凭据） |
| `GET /api/auth/me.dev_switch_enabled` | `false` | `true` |

`role_policy.dev_role_switch_enabled()` 是单一闸门，所有相关 API 在路由入口处调用此函数。

## 4. 越权不可暴露存在性

| 场景 | 响应 | 说明 |
|---|---|---|
| 非管理员访问未发布记录详情 | **404 `not_found`** | 不区分“未找到”与“无权访问”，避免枚举攻击 |
| 未配置 CAS 直接访问受保护接口 | 401 `unauthorized` | `detail: "需要校内登录"` |
| 客户端伪造任何身份 header | **按 session 中真实身份返回** | 越权即 4xx，不静默降级为 guest |

## 5. 验证证据（4 个场景全 PASS + pytest 30/30）

| 场景 | 验证手段 | 证据路径 |
|---|---|---|
| A. 开关关闭 → `POST /api/dev/role` = 404 | 真实 HTTP 活体验证 | `evidence/week2/A/role-isolation-live.txt` |
| B. 6 种伪造 header（X-Role/X-Forwarded-User/X-Remote-User/Authorization/Role）提权失败 | 真实 HTTP 活体验证 | `evidence/week2/A/role-isolation-live.txt` |
| C. 未发布记录 + 伪造 admin → 详情 404 | 真实 HTTP 活体验证 | `evidence/week2/A/role-isolation-live.txt` |
| D. 开关显式开启 → 功能可用、可 DELETE 复位 | 真实 HTTP 活体验证 | `evidence/week2/A/role-isolation-live.txt` |
| 单元/接口测试（30 项） | pytest | `evidence/week2/A/role-isolation-test-output.txt` |

复现：`python scripts/run_role_isolation.py`（本仓库根目录）。

## 6. 部署要求（9/24 真实部署的依赖）

- HTTPS 证书（域名 + 受信 CA，自签证书会被 CAS 拒绝 callback）
- CAS 端点：`{CAS_LOGIN_URL}/login?service={本服务回调}`（生产值由部署环境注入）
- 环境变量：`ENABLE_DEV_ROLE_SWITCH` 必须为 `false` 或未设
- 未满足时 `app/auth/provider.py` 中 `CasProvider` 必须显式抛 `CAS_PROVIDER_NOT_CONFIGURED`，**前端 401 引导到阻塞记录页**，不返回 200。

## 7. 变更记录

| 日期 | 变更 | 影响面 |
|---|---|---|
| 2026-09-21 | 冻结 `app/auth/provider.py`（40 行）：`AuthIdentity` / `AuthProvider` / `CasProvider` | 所有依赖 subject 的路由 |
| 2026-09-22 | 本契约文档落地；越权 4 场景 + pytest 30/30 全 PASS | A-02 验收项关闭 |

---

**契约评审触发条件**：本文件 §1 角色清单、§2 接口签名、§3 开关语义、§4 越权响应任何一项变更，须在 PR 中 @ B/C 角色 + reviewer 重审。