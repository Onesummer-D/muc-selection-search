# B Goal：抽取质量与评测闭环

从 C 集成基线重新建 `feat/week2-B-quality`，先阅读 `docs/week2/07_第二周数据源与海报主线补充说明.md`。只提交 extraction、tests/extraction、data/gold、reports/extraction、progress/week1/B、evidence/week1/B。禁止整体合并旧 B 分支，禁止覆盖 C 的根配置、领域层、仓储层、搜索层、前端和文档。

固定 5 篇 bundle/evidence pack 先做 C SQLite 导入烟测；随后覆盖 88 张经验分享海报的批处理状态，其中 20 张 Gold 只用于固定评测，剩余 68 张用于扩展处理和岗位字段复核。对门户附件按格式分流：PDF 优先读取文本层、无文本层再走页面 OCR，XLS/XLSX 按工作表与行列证据读取，12 个非经验材料不得强行生成五字段人物记录。再用同一 20 样本、同一 SHA-256、同一 gold 重跑评测。本周验收主口径采用归一化准确率，逐字段记录分子、分母、归一化准确率、低于 90% 的样本、review_required 队列和成本/模型/授权/保留策略。原始逐样本结果与严格口径保留为附件，不能删除或替换。多模态不足门槛时保持“不启用”，不得换样本或调整启用阈值。
