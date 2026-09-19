# 任务3（阶段一）LLM 接入 证据（角色 C）

- 日期：2026-09-18（本地）
- 分支：feat/week1-core-search

## 交付内容

| 模块 | 职责 |
|---|---|
| `app/search/llm_provider.py` | LLMProvider 抽象接口 + DeepSeekProvider（OpenAI 兼容 /chat/completions，标准库 urllib 实现，零新依赖）+ NullProvider + get_llm_provider() 环境变量工厂（未知供应商不猜测，按未配置处理） |
| `app/search/answer_service.py` 改造 | LLM 只消费 UserQuery + QueryPlan + EvidencePack；system prompt 内置附录 G G9 约束（100-200 汉字、只做相关性/共同点/差异总结、不生成去向建议/概率/价值排序、必须带引用、无证据不写）；CitationValidator 校验引用（[数字] 序号与 [record_key] 两种形式归一化，越界/无引用 → 降级）；调用失败/校验失败 → 回退规则模板，degraded=true，传统结果照常返回 |
| `app/web/app.py` | 极简 .env 加载器（KEY=VALUE，已存在环境变量优先；不引入 python-dotenv）；create_app 支持 llm_provider 注入（测试隔离用） |
| `.env`（本机，gitignored） | LLM_PROVIDER=deepseek、LLM_API_KEY（不进入仓库，`git check-ignore` 已验证） |

## 密钥安全

- API Key 只存于本机 `.env`（.gitignore 第 20 行排除），代码与提交内容不含密钥。
- 建议定期轮换密钥；如密钥曾在聊天中明文出现，建议尽快在供应商后台重置。

## 余额核验

```
$ curl https://api.deepseek.com/user/balance -H "Authorization: Bearer ***"
{"is_available":true,"balance_infos":[{"currency":"CNY","total_balance":"8.69",
 "granted_balance":"0.00","topped_up_balance":"8.69"}]}
```

## 测试

```
$ python -m unittest discover -s tests/core
Ran 75 tests in 0.177s
OK
```

新增 15 个测试（60 → 75，只增不减）：test_llm.py 覆盖
- 正常引用回答 degraded=false；prompt 不含 SQL/仓库细节（LLM 输入只有证据包）
- 越界数字引用、未知 record_key 引用、无引用 → 全部降级回退
- record_key 引用归一化为序号，不降级
- 模型网络异常 → 回退且传统结果照常返回
- 证据不足时不调用模型（stub.calls == []）
- guest 引用 DTO 不含任何私有字段
- 工厂：未配置/未知供应商 → None；deepseek 配置 → 正确实例
- API 集成测试注入 NullProvider，与本机 .env 解耦（发现并修复了跨测试环境污染）

## 真实端到端烟测（真实调用 DeepSeek）

```
HTTP 200 | degraded: False | reason: None
answer: 证据包中仅匹配到1条记录，面向2026届、本科、计算机类专业、西部城市、基层岗位的查询条件[1]。
该记录显示：届别为2026届[1]，学历为本科[1]，专业为计算机科学与技术[1]，工作地点为成都[1]，
岗位为基层岗位[1]。成都属于西部城市，与查询城市方向一致[1]。专业名称与查询的计算机方向相近[1]。
整体来看，该记录在届别、学历、专业方向、城市区域和岗位类型上与查询条件基本对应[1]。
证据包未提供其他记录，无法进行更多共同点或差异比较[1]。
citations: [(1, 'portal-10001-01', 'city', '工作地点 成都')]
```

## 调试过程中发现并修复

1. `complete()` 返回 LLMResult 对象，主流程误当字符串用（单测捕获）。
2. 首版 prompt 用"编号"导致模型输出 [record_key] 引用 → 引用校验拦截降级；prompt 改为明确的"引用序号 [1]"格式，校验器同时兼容两种形式归一化，降低无谓降级率。
3. create_app 加载 .env 污染测试进程环境（测试真的调了外部 API）→ create_app 支持注入 llm_provider，API 测试注入 NullProvider 隔离；NullProvider 语义修正为"明确未配置"，走模板路径而非"调用失败"路径。

## 任务3 剩余

- 100 行脱敏性能夹具、30 次查询 P95 统计
- 对比台 / Excel·CSV 导出 / 结果统计接口（G7 P1）
- 反向验证（未知字段、越权资源、无证据回答）已有部分测试覆盖，任务3 收尾统一归档
