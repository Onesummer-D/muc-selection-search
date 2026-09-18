# 角色 C 阻塞记录（BLOCKED）

- 2026-09-17 23:05：无阻塞。
  - 待观察（上游依赖，尚未构成阻塞）：A 的 5 篇 article_bundle.v1 与 B 的 extraction_bundle.v1 尚未交付，任务3需要它们做端到端导入。
- 2026-09-18：公网服务器和域名不再是第一周P0。最终路线已确定为云服务器或学校服务器+HTTPS；本周提交部署清单并完成LAN验收。
- 2026-09-18（任务4 收尾状态）：无阻塞项；两项待人工完成——
  - LAN 另一台设备实测（服务已监听 0.0.0.0:5000，操作步骤见 evidence/week1/C/task4_release_evidence.md 第 4 节），需要一名队友配合截图。
  - 录屏（按总体手册流程），待 LAN 截图后统一录制。
  - 依赖记录：A 分支 feat/week1-portal-sync 已含 A1/A2（5 篇样本 5/5 通过校验）但未开 Draft PR；B 分支 feat/week1-extraction-eval 未出现。C 侧任务3 演示数据当前使用脱敏虚构 seed，A 的真实样本 bundle 合入后需重导并复跑性能夹具（预估半小时）。
