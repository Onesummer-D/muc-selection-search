# 角色 A 阻塞记录

## B-1 门户真实端点未登记（✅ 已解除，2026-09-18 00:30）

- 现象：仓库（README、ARCHITECTURE、04_接口与数据字典）只定义了逻辑接口名 `getNoticeByPage` / `getNotice`，
  未给出真实 `PORTAL_BASE_URL`、`CAS_BASE_URL`、栏目 ID、分页参数名和筛选关键词。
- **解除过程**：
  1. 匿名探测：门户未登录 302 → `/user/simpleSSOLogin` → `https://ca.muc.edu.cn/zfca/login`
     （民大统一认证为 ZFCA，表单字段 username/password）。
  2. 登录探测（人工登录 + `probe_endpoints` 捕获，证据 `evidence/week1/A/endpoint-probe.json`）：
     - 列表接口：`POST https://my.muc.edu.cn/comsys-portal-notice-web/getNoticeByPage`
       表单参数 `currentPage / pageSize / type / searchValue / comsys_random_t` 等；
       响应 `{"datas": {"tables": [...]}}`，行字段 `notice_id / notice_title / notice_content /
       notice_link / notice_first_time / notice_type_name / organization_name`。
     - **就业信息栏目 type=10**（实测返回"就业信息"类通知）。
     - 详情：门户无独立详情 JSON 接口（`readNotice` 仅为"标记已读"），正文在列表行
       `notice_content`（HTML）或外链 `notice_link`（就业信息多为微信公众号推文）。
- **落地**：`from_env` 默认值已适配真实接口（POST/分页参数/栏目 type=10/list 详情模式），
  本地 `.env`（不入库）已配置；`tests/datasource/test_real_portal.py` 按真实响应结构覆盖。
- 遗留观察项（不阻塞 A2/A3）：就业信息栏目部分文章 `notice_content` 为空、正文在
  微信外链中；样本如需正文，采集时按 `notice_link` 抓取外链或在交接说明标注。


