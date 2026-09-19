# A→C 交接验证 证据（角色 C）

- 日期：2026-09-18（本地）
- 背景：PR #4（feat/week1-portal-sync，角色 A）已由 C 完成验收审查并 APPROVED，
  等待按"先合 A"顺序合并。本验证在合并前完成，确保合并后可立即导入。

## 验证内容与实际输出

1. **契约交叉验证**：A 的 5 篇固定样本通过 A 侧 jsonschema 后，再经 C 侧独立实现的
   领域校验器（app/domain/validation.py）全部 PASS（3 poster + 1 mixed + 1 text）。
2. **入库验证**：A 的 5 篇真实脱敏 bundle（直接读取 PR 分支文件）经 C 的
   BundleImporter 导入内存 SQLite：articles=5、assets=4（文本帖无海报，素材数正确）。
3. **幂等验证**：5 篇各重复导入一次，行数保持 (5, 4) 不变。
4. **extraction 通道联通**：A 的 notice_id 作为主键被 extraction bundle 正常关联
   （records=1），B 的 bundle 一到即可入库。

```
5 篇 + 各重复导入一次 -> articles=5 assets=4（幂等成立）
A 的文章 + extraction 通道联通: records = 1
=== 跨集成验证 PASS ===
```

## 依赖固化

requirements.txt 已建立（flask、openpyxl + A 声明的 requests、jsonschema；
playwright 注释说明仅人工 CAS 登录使用，不作为服务端运行依赖）。

## PR #4 审查结论（已发布 APPROVED review）

- 通过项：5/5 样本双校验器交叉验证、100 篇真实台账（4 类失败状态演示齐全）、
  68 项测试本地复跑全绿、敏感扫描三遍干净（0 绝对路径/无联系方式/Cookie 不落盘）。
- 合并前请 A 处理（不阻塞）：根目录 3 个脚本挪位、PR 描述更新 A3/标题、依赖已由 C 固化。

## 合并后 C 的后续动作（待 PR #4 merge）

1. main 同步后把 A 的 5 篇真实 bundle 导入正式演示库，替换部分虚构 seed。
2. 吸收 A 的 .gitignore 改动（evidence/week1/A/ledger/ 与 a4/_*）进根配置。
3. 复跑全部测试与性能夹具（88 + 68 项）。
4. B 的 extraction bundle 到货后走同一导入通道（已验证联通）。
