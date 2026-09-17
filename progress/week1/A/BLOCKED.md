# 角色 A 阻塞记录

## B-1 门户真实端点未登记（阻塞真实采集，不阻塞开发）

- 现象：仓库（README、ARCHITECTURE、04_接口与数据字典）只定义了逻辑接口名 `getNoticeByPage` / `getNotice`，
  未给出真实 `PORTAL_BASE_URL`、`CAS_BASE_URL`、栏目 ID、分页参数名和筛选关键词。
- 影响：A2 的 5 篇固定样本必须来自真实门户数据，无法在端点确认前产出真实样本。
- 已采取措施：客户端端点/参数全部配置化（`app/datasource/config.py` + `.env`），传输层可注入，
  全部逻辑与自动化测试不依赖真实门户。
- 需要决策：由本人（角色 A）人工确认门户端点与栏目参数后填入 `.env`（不入库），再执行 CAS 登录采集。

### 更新（9/18 00:10）：A1 匿名探测结果

- `PORTAL_BASE_URL = https://my.muc.edu.cn`（信息门户，`/page/11` 为 SPA 路由）已确认。
- 门户未登录时 302 → `/user/simpleSSOLogin` → `https://ca.muc.edu.cn/zfca/login`
  （民大统一认证为 **ZFCA**，非标准 CAS 协议名；表单字段 username/password，可能有验证码）。
  → `CAS_BASE_URL = https://ca.muc.edu.cn/zfca`。
- 匿名探测 `my.muc.edu.cn` 常见路径均 404：门户 JSON 接口**必须登录后才能确认真实路径与参数**。
- 下一步：运行 `python -m app.datasource.probe_endpoints --portal-base-url https://my.muc.edu.cn`
  人工登录并浏览「就业信息」栏目，捕获真实接口（工具已就位，待人工登录执行）。

