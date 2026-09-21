# B Goal：抽取质量与评测闭环

从 C 集成基线重新建 `feat/week2-B-quality`，只提交 extraction、tests/extraction、data/gold、reports/extraction、progress/week1/B、evidence/week1/B。禁止整体合并旧 B 分支，禁止覆盖 C 的根配置、领域层、仓储层、搜索层、前端和文档。

固定 5 篇 bundle/evidence pack 先做 C SQLite 导入烟测，再用同一 20 样本、同一 SHA-256、同一 gold 重跑评测。本周验收主口径采用归一化准确率，逐字段记录分子、分母、归一化准确率、低于 90% 的样本、review_required 队列和成本/模型/授权/保留策略。原始逐样本结果与严格口径保留为附件，不能删除或替换。多模态不足门槛时保持“不启用”，不得换样本或调整启用阈值。
