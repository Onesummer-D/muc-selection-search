# 团队开发规则

## 1. 禁止提交的内容

任何情况下不得提交：

- 密码
- API Key
- CAS Cookie / Session
- .env
- 原始含个人信息的海报
- 未脱敏真实数据库
- 用户搜索历史
- 私有测试账号
- 本地虚拟环境
- node_modules

如果误提交，立即通知全组，不能只做普通 delete 后继续。

---

## 2. AI 使用规则

可以使用 AI 辅助编码，但 AI 不拥有架构决策权。

AI 不得自行：

- 更换技术栈
- 新增框架
- 新增数据库
- 修改公共接口
- 修改 Schema
- 新增产品功能
- 改变权限模型
- 绕过 CAS 或访问控制
- 将敏感数据写入代码
- 将密钥写入仓库
- 大规模重构其他成员模块

出现以上需求时，必须先停止实现并提交讨论。

---

## 3. 开发原则

main 分支必须保持可运行。

所有新功能：

feature branch
→ 自测
→ Pull Request
→ 至少一名队友检查
→ merge main

禁止为了“方便”直接覆盖其他成员代码。

---

## 4. 公共接口优先

模块之间只能通过约定接口交互。

例如：

DataSourceAdapter
Extractor
Repository
Retriever
LLMProvider

不得绕过接口直接依赖其他模块内部实现。

本期不实现语义检索，不创建 `VectorStore` 或 `EmbeddingProvider` 空壳；以后只有重新拍板并有评测收益时再补充。

---

## 5. 修改前先阅读

AI 开始编码前必须阅读：

1. README.md
2. docs/ARCHITECTURE.md
3. docs/TEAM_RULES.md
4. 当前模块 README
5. 对应接口定义

如文档与任务冲突，先询问，不自行推断。
