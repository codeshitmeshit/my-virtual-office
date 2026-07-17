# 技术方案评审

## 1. 评审结论

**结论：通过，可以进入人工技术方案确认门禁。**

方案覆盖了规格中的主投递优先级、Chat App 回退、首个有效决定唯一生效、双卡终局同步、投递失败关闭等待、独立审计及 VO 聊天历史隔离。实现路径以现有 `feishu_notifications.py` 通用框架为唯一出站卡片基础，复用其 intent、卡片 builder、应用发送、脱敏和通知审计；同时复用 Codex approval continuation、统一飞书卡片动作分发器和 `ProviderApprovalService` fence 语义，没有引入新的第三方依赖或第二套发卡协议。

实现阶段必须保持以下三项硬约束：

1. 通知应用只能定向原发起人，不能使用配置里的固定收件人替代；无法安全映射身份时回退 Chat App。
2. callback 必须先持久 claim，provider 调用结果不确定时不得自动重放受保护动作。
3. card delivery、card action、action acknowledgement 和 synthetic approval result 均不得写入 VO chat/comm history；只有原用户消息和 turn 正常终局回复沿用既有历史行为。

## 2. 阻塞问题

无。

通知应用使用 `union_id` 定向用户仍需在测试租户验证权限，但该结果不阻塞设计：权限不可用时按既定规则回退原 Chat App 会话。

## 3. 主要风险

| 风险 | 影响 | 方案控制 | 评审意见 |
| --- | --- | --- | --- |
| 通知应用与 Chat App 的用户 ID 身份域不同 | 审批误投或主路径无法投递 | `union_id` 优先、`user_id` 次之、`open_id` 仅同身份域；不可映射即回退 | 可接受，需覆盖跨应用身份测试 |
| 主投递响应丢失后又发送 fallback | 用户看到两张卡 | 共用 durable route fence，首个有效决定生效，终局更新全部引用 | 可接受，必须有冲突动作测试 |
| provider 成功、route commit 前崩溃 | 决策结果不确定 | claim 先持久化；恢复时不重试不确定 provider 调用，标记 unavailable | 安全优先，符合审批场景 |
| 飞书网络请求阻塞 provider event reader | turn 卡死或事件积压 | 有界后台 executor、短超时、总 deadline、饱和安全取消 | 可接受，需队列饱和测试 |
| 卡片更新失败，旧按钮仍可点击 | 用户误以为可再次审批 | 服务端 fence 权威拒绝 replay，更新失败独立告警 | 可接受，不能依赖前端按钮状态保证幂等 |
| 审批摘要泄露命令参数或路径中的秘密 | 信息泄漏 | allowlist、脱敏、长度限制、审计不存完整卡片 | 可接受，需秘密样本测试 |
| failure closure 与原 turn 同时终局 | 重复回复或状态竞争 | 同一 route/turn fence、只允许一次 provider continuation、正常 reply 作为唯一可见终局 | 实现时重点 CR |
| pending 状态被后续 activity 覆盖 | 界面误报 idle | approval pending 对 presence projection 具有优先级 | 与原问题一致，需回归验证 |

## 4. 关键追问

### Q1. “通知应用优先”是否意味着发给配置中的固定 `feishuReceiveId`？

否。需求同时限定收件人是原发起用户。固定收件人仅适用于普通通知；审批必须用本次来源身份定向，无法定向就回退 Chat App。

### Q2. 为什么不能直接在 Codex approval event callback 里发卡？

飞书调用是外部网络 I/O，同步执行会阻塞 Codex app-server event reader。方案采用有界后台投递，并把队列饱和也视为显式失败，避免形成新的卡死点。

### Q2.1. 之前的通用飞书通知框架是否可以直接复用？

可以，而且是本方案的默认实现。Codex 只新增 `application_form` intent builder 和审批 routing policy；通知应用与 Chat App 都调用 `send_feishu_notification`。动态收件人已经可以通过 per-call `app_config` 指定；通用框架只需补两个通用缺口：应用发送返回 `messageId`、按 `messageId` 更新卡片。Chat App worker 只补 cardAction 入站，不再新增私有发卡命令。

### Q3. 为什么除了 `ProviderApprovalService` 还需要 durable route repository？

`ProviderApprovalService` 当前是进程内状态。飞书可能重试或延迟 callback，服务也可能重启；仅靠内存无法在恢复后判断 replay。持久 route 保存最小状态和 claim fence，原生 Codex pending registry 仍由现有 bridge 管理。

### Q4. Chat App cardAction 为什么不能走普通 inbound message spool？

普通 inbound path 会形成消息 delivery record 和 VO 历史投影，违反审批卡片隔离。专用 approval-action spool 只保证 callback 可靠投递，不参与聊天历史同步。

### Q5. 两路卡片都无法送达时，失败消息为什么允许进入历史？

卡片和动作是控制面，不进入历史；“审批无法送达，操作已取消”是原 Codex turn 的正常终局业务结果，规格明确要求用户可见并保留既有最终回复行为。

### Q6. crash 后能否自动重新调用 approve？

不能。在 provider 调用是否成功不确定时自动重放可能重复执行受保护命令。恢复策略选择 at-most-once：无法证明仍 pending 就将 route 标为 unavailable，并拒绝迟到动作。

## 5. 测试与上线建议

### 必须的自动化测试

- 路由单测：eligible kind、来源冻结、通知应用优先、未配置/不可路由/明确失败/ambiguous 的 fallback。
- 身份与安全单测：原用户通过、不同用户拒绝、跨 Agent/conversation/thread/turn/approval 拒绝、未知字段和超限 payload 拒绝。
- 幂等单测：重复、并发、冲突、busy、late callback；只有一个 provider continuation。
- 故障单测：executor queue full、两路 timeout、provider failure、audit failure、card update failure、callback spool replay、进程恢复中的 unresolved claim。
- 历史隔离测试：发送卡、更新卡、接受/拒绝/replay callback、飞书来源 respond 都不会新增可见 comm/chat message；最终 Agent reply 仍正常记录。
- presence 回归：approval pending 后出现其他 activity 仍显示等待审批，resolved/failed 后才清除。
- 通知框架 contract tests：动态原用户收件人、`messageId` 返回、card update、`skipped_*` 在审批 policy 中触发 fallback，同时保证普通通知兼容行为不变。
- worker contract tests：`cardAction` schema、token、worker instance、payload size、spool replay、timeout 和错误归类；确认没有另建 Codex 私有发送协议。
- transport contract tests：Channel SDK 与 legacy adapter 对同一业务输入产出一致的规范化结果。

### 测试租户验收

1. 通知应用通过 `union_id` 给原用户发卡并成功回调。
2. 通知应用未配置时，Chat App 在原 DM/群会话发卡并回调。
3. 通知应用明确失败及响应丢失场景触发 fallback；两张卡只生效一次。
4. approve-once 后原 Codex turn 继续；cancel 后受保护动作不执行。
5. 两路投递失败后 Agent 不再 pending，原会话收到普通失败回复。
6. VO 聊天历史中看不到审批卡片及动作，但能看到最终回复。

### 上线与回滚

- 先以 `VO_CODEX_FEISHU_APPROVAL_CARDS_ENABLED=false` 部署代码和观测指标，再在测试租户、小范围用户、全量三个阶段开启。
- 灰度重点观察 pending duration、primary/fallback success、callback replay/reject、queue saturation、failure closure 和 card update failure。
- 回滚前停止创建新 route，对 live approvals 安全取消或等待终局，并尽力将已发卡片更新为 unavailable；随后关闭开关。不得通过直接丢弃 route 的方式回滚。

## 规格追踪

| 规格要求 | 设计覆盖 | 主要验收证据 |
| --- | --- | --- |
| 原发起用户收到 eligible approval | Decisions 1、2、4、6 | 来源冻结与收件人路由测试 |
| 通知应用优先、Chat App fallback | Decisions 4、5 | 主/备投递矩阵与 ambiguous 双卡测试 |
| 原 Codex turn exactly-once continuation | Decisions 3、7 | 并发/重复/冲突 callback 测试 |
| 所有卡片反映终局 | Decision 6 | primary/fallback fan-out update 测试 |
| 无法投递时可见失败且不再等待 | Decision 8 | queue full、双失败、终局状态测试 |
| 审批控制面不进入聊天历史 | Decisions 3、5、7、8 | comm/chat history isolation 测试 |
