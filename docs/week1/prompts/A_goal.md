# 角色 A 目标任务书

在执行 agent 那边输入 `/goal `，粘贴下面整段并发送。

```text
你是角色A。这份任务书是唯一任务来源；没人能在执行中答疑，拿不准的写进 progress/week1/A/BLOCKED.md 后继续不受影响的工作。换会话先读 progress/week1/A/PROGRESS.md，每完成一项立即更新。目标是在2026-09-20 15:00前交付可复现的门户采集与增量更新模块，让100篇目标文章都有明确状态，并在9月17日18:00前先交付5篇脱敏固定样本。发生冲突时，账号安全与数据真实性 > 契约兼容 > 完整度 > 速度。文中“只允许”“不得”是硬约束；“建议”可调整，但要在角色PROGRESS.md说明。

## 我替领导拍的板
- 现有材料只有部分素材，没有可直接依赖的完整代码｜按从零复现规划；旧代码通过检查后才复用。
- CAS登录由本人在有界面浏览器完成｜程序只接收登录后的会话，不读取或保存密码。
- 100篇目标以现有筛选清单为起点｜清单不足时记录真实数量和缺口，不伪造条目。
- 固定5篇优先选2篇文本、2篇海报、1篇多人或混合内容｜不满足时记录实际构成。

## 界限
只允许修改 app/datasource/**、app/sync/**、tests/datasource/**、evidence/week1/A/** 和 progress/week1/A/**。README、Schema、requirements、Excel验收台账及其他角色目录只读；新增依赖写进PR说明，由C处理。A把实际值、证据路径和交接信息写入角色PROGRESS.md或PR清单，由C回填主验收台账。不得提交Cookie、账号、原始含个人信息海报、绝对本地路径、真实姓名、未脱敏响应或数据库。不得绕过CAS、随机切换UA、提高请求频率或改验收阈值。

## 现状与任务0
仓库基线以README、docs/ARCHITECTURE.md、docs/TEAM_RULES.md、docs/week1/04_接口与数据字典.md为准。技术方案记录326条候选、100篇目标、约95篇海报、22条初步记录，这些是历史基线，不是本周实绩。先运行 git status --short、git log -1 --oneline、python --version，核对分支为 feat/week1-portal-sync；确认Schema可读。把目标、顺序、最大风险写入不超过10行的progress/week1/A/PROGRESS.md。环境或接口不符时把原始输出写入progress/week1/A/BLOCKED.md顶部。

## 任务1 固定样本
实现CAS人工登录后把Cookie仅放入内存requests会话；实现getNoticeByPage和getNotice配置化客户端。相邻门户请求的开始时间差随机落在0.8至1.5秒，超时、429和5xx在初次尝试后最多额外重试3次并退避。按article_bundle.v1输出5篇脱敏固定样本及SHA-256。用Schema校验全部通过；失败样本必须有notice_id和failure_reason。

## 任务2 批量、调度与恢复
建立100篇采集台账，逐篇保存状态。以notice_id幂等插入或更新；中断后只继续未完成项。实现SyncService稳定入口和本地可运行Scheduler，支持周期配置、单实例锁、任务状态、最多3次重试和从上次游标继续；Scheduler不得复制采集逻辑，CAS会话失效时暂停并提示人工重新登录。写自动化测试覆盖分页、调度触发、并发锁、重试上限、429退避、断点恢复、重复运行和失败落账。反向验证一次：故意让模拟接口返回429，贴出失败/重试证据；还原后贴通过结果。

## 任务3 交接
每天至少push一次并建立Draft PR。提交信息使用 feat(sync) 或 test(sync)。9月17日18:00前把5篇样本的commit交给B和C，18:00至22:00留给接收方完成Schema、哈希和导入校验；9月18日22:00前交付100篇台账；9月19日18:00前完成PR与脱敏证据。交接后等待接收方4小时内确认，只修契约或P0问题。

## 规矩
不得skip/todo测试、放宽断言、mock掉被测重试/幂等逻辑、删除失败样本、修改Schema或用|| true制造假绿。测试数只增不减。同一验收连续失败3次即停该项，记录已试方法和下一步。不得直接合并main。

## 完成条件
1. 真实目标清单中每篇都有processed、review_required或failed及原因，5篇固定样本全部通过article_bundle.v1校验；Scheduler能触发SyncService，单实例锁、断点恢复和重复运行均可复现且无重复记录。
2. git diff不越界，敏感文件为0，PR含命令输出、429红到绿证据和交接commit。progress/week1/A/BLOCKED.md必须提交，没问题也写“无”。只有每条都贴实际命令输出才算完成；或连续3轮仍受外部接口阻塞时停止并如实交卷。
```
