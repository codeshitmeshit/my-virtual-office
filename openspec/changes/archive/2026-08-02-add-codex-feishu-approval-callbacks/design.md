## Context

飞书发起的 Codex turn 会携带 `sourceApp`、`sourceSurface`、`sourceMessageId`、`feishuChatId` 和 `sourceActor`，但当前 Codex approval 只进入 Web Chat SSE、pending API 和 agent-platform communication ledger。飞书侧没有审批卡片，也没有把卡片动作续接回原 Codex turn 的入口，因此用户可能看不到待审批状态，Agent 也可能长期等待。

仓库已有三块可复用能力，其中 `app/feishu_notifications.py` 是本变更的通知基础设施，不另起一套卡片发送框架：

- 通用飞书通知框架已提供 notification intent 校验、`application_form` 交互卡片渲染、应用/Webhook 发送、秘密脱敏和独立 `feishu-notification-records.jsonl` 审计；Hermes approval 已直接复用该框架；
- `ProviderApprovalService` 提供有界 pending/resolved 状态、claim/commit fence 和 replay 结果；
- 通知应用的飞书长连接已接收交互卡片动作，`_handle_feishu_card_action` 已统一分发会议、项目和 Hermes 动作；Chat App 的 Node Channel SDK worker 已有带进程级 token 的本地协议和入站持久 spool，SDK 本身支持 `cardAction`。

当前 Codex 响应路径还会通过 `_append_codex_approval_result_comm_event` 写入一条可见的“审批已同意/取消”聊天消息。新需求明确要求卡片、卡片动作和动作确认不进入 VO 聊天记录，因此飞书卡片路径必须使用独立的审批状态与审计面，不能复用普通消息投递链路。

本变更跨越 Codex provider bridge、飞书通知应用、飞书 Chat App worker、卡片回调、安全校验、状态持久化和 VO presence。设计需同时满足：发给原发起人、通知应用优先、失败降级、首个有效决定唯一生效、无法投递时关闭等待，以及不污染聊天记录。

## Goals / Non-Goals

**Goals:**

- 将飞书来源的 Codex command、file-change、permission approval 定向投递给原发起用户。
- 通知应用可用且能定位原用户时优先投递；否则或投递失败时回退到原 Chat App 会话。
- 让 approve-once/cancel 从任一已投递卡片安全、幂等地续接原 Codex turn。
- 投递全部失败时拒绝受保护动作、解除 provider 等待，并经原有正常回复链路返回可见失败。
- 将审批生命周期、投递、回调、决策和卡片更新保存在独立、有界、脱敏的审计面；普通最终回复保持现有历史行为。
- 在待审批期间让 presence 以 pending approval 为高优先级状态，避免被后续无关 activity 覆盖为 idle。

**Non-Goals:**

- 不为 Codex 的任意文本输入、问答选择或非安全敏感交互生成卡片。
- 不增加 session/always 等长期授权；飞书只开放 approve-once 和 cancel。
- 不改变 Web Chat 现有审批 UI、pending API 或其现有聊天历史兼容行为。
- 不把通知应用配置中的固定 `feishuReceiveId` 当作审批收件人。
- 不把 webhook 视为可交互审批应用；webhook 无法可靠验证动作身份和定向原用户。
- 不保证服务重启后恢复已经丢失的 Codex 原生进程；重启后的遗留卡片只允许进入 expired/unavailable，不得重放受保护动作。

## Decisions

### 1. 复用通用通知框架，新增轻量 Codex 审批协调器

新增 `CodexFeishuApprovalCoordinator`（具体文件可落在 `app/services/`），负责：

1. 从 Codex approval event 和当前可信请求上下文创建审批路由记录；
2. 将投递任务提交到有界后台队列；
3. 选择通知应用或 Chat App adapter；
4. 校验并 claim 卡片动作；
5. 调用现有 Codex `respond_approval` 续接端口；
6. commit 结果、更新所有已知卡片并写独立审计；
7. 在投递终局失败时执行 cancel/deny closure。

协调器不负责重新实现卡片渲染、飞书 token、HTTP 发送、脱敏或基础通知审计。它产出符合现有 `validate_notification_intent` 的 `application_form` intent，并通过 `send_feishu_notification` 投递。协调器不替换 Codex app-server bridge 内部的原生 pending registry；它只维护审批路由、fallback policy 和决策 fence。这样 Web Chat 路径保持兼容，同时避免把某个飞书 SDK 的概念放入 provider adapter。

备选方案是直接在 Codex event callback 中同步发送卡片。该方案会让飞书网络延迟阻塞 provider 事件读取，而且失败重试容易卡住整个 turn，因此不采用。

### 2. 在 approval 产生时冻结可信来源上下文

只对 `sourceApp=feishu` 且来源为 `feishu-dm` 或 `feishu-group` 的 turn 启用卡片。协调器从当前 `_handle_codex_chat` 请求体冻结下列信息，而不是稍后从聊天历史猜测：

- Agent、provider profile、conversation、thread/session、turn/run、approval identity；
- `sourceMessageId`、`feishuChatId`、来源 surface；
- 原发起人的 `openId`、`userId`、`unionId` 和显示名；
- approval kind 和经过长度限制、脱敏后的展示摘要。

缺少 approval-to-turn 关联或原用户身份时，不投递审批内容，并进入不可路由失败闭环。卡片 action value 只携带不可猜测的 route id、动作和协议版本；Agent、turn、用户等权威关联从服务端路由记录读取，不能由客户端覆盖。

备选方案是只把 Codex `approvalId` 放进卡片并在回调时查询当前 pending。它无法阻止跨用户、跨 turn 的拼接或迟到回调，因此不采用。

Codex server request 还具有连接归属：仅覆盖 `approvalsReviewer=user` 不会把 Desktop 或旧 app-server 创建的 thread 迁移到当前 VO 连接。`CodexAppServerClient` 因此维护当前 runtime generation 内由自己创建或 fork 的 thread 集合。可交互 turn 首次遇到未知 thread 时先调用 `thread/fork` 保留上下文并取得当前连接归属；同一 generation 内后续 turn 直接 resume。runtime 重启后集合清空，下一次可交互 turn 再 fork 一次。这样不会丢失会话上下文，也不会持续把 approval server request 发给旧客户端。

### 3. 独立、有界、可恢复的路由状态与审计

建立 `codex-feishu-approval-routes` 持久仓库，保存最小必要状态：`pending -> delivering -> delivered/resolving -> resolved|failed|expired`、claim lease、权威 decision、投递引用和脱敏错误。仓库使用原子写入、容量上限和 TTL；已完成记录按时间淘汰。详细事件追加到独立、可轮转的 approval audit，不写 `_append_comm_event`。

运行期可以复用 `ProviderApprovalService` 的 claim/commit 语义，但 durable route repository 是跨 callback replay 的权威 fence：

- callback claim 必须先持久化，再调用 provider；
- provider 成功后持久化 commit；
- crash 发生在 provider 调用之后、commit 之前时，启动恢复不得重试 provider 决策，而是查询原生 pending；若无法证明仍 pending，则标记 `resolved_unknown/expired` 并使卡片失效。

这选择 at-most-once 的安全边界，避免在不确定状态下重复执行受保护动作。备选的纯内存 registry 在进程重启后无法识别 replay，故不采用。

### 4. 用通用发送器实现通知应用优先和动态收件人

“配置了通知应用”的判定要求完整 app id/app secret 和可接收卡片动作的长连接能力；审批投递不使用配置中的固定 `feishuReceiveId`。接收身份按以下顺序选择：

1. 原消息的 `union_id`；
2. 可确认在同租户可用的 `user_id`；
3. 仅当通知应用与 Chat App 身份域一致时使用 `open_id`。

协调器为每次调用构造临时、仅内存使用的 `app_config`，复用 `send_feishu_notification(intent, app_config=...)`：通知应用配置使用原用户的动态 `receiveId/receiveIdType`，而不是全局固定收件人。若完整通知应用未配置、无法获得可迁移的原用户身份、应用不可用或明确返回失败，则使用 Chat App 凭据和原 `feishuChatId` 作为 `chat_id`，再次调用同一个通用发送器投递同一 route id 的卡片。通知应用结果超时或连接断开属于 ambiguous failure：允许回退，并保留可能已成功的 primary 引用；两个卡片仍共享同一决策 fence。

审批 policy wrapper 只把 `status=sent` 视为已投递；通用框架的 `skipped_disabled`、`skipped_missing_webhook` 等兼容状态在审批语义下都视为未投递。审批不启用 webhook fallback，因为 webhook 不能可靠定向原用户并完成可信动作回调。

对通用框架做两项向后兼容扩展：应用发送结果返回飞书 `messageId`；新增 `update_feishu_notification(message_id, intent, app_config=...)`，复用现有 token、卡片 builder、脱敏和结果记录能力。所有请求设置短且有界的超时。该扩展同时服务通知应用和 Chat App，不增加 Codex 私有发送实现。

备选方案是始终发给通知配置中的固定接收人。该方案违反“原发起人”规则且有审批泄漏风险，因此明确禁止。

### 5. Chat App 只补 cardAction 入站，不新增私有发卡协议

Chat App 出站卡片和卡片更新均由通用飞书通知框架使用 Chat App 凭据完成，不给 worker 新增 `sendCard/updateCard` 命令。Node worker 只注册 Channel SDK 的 `cardAction` handler，将规范化动作写入与普通消息 spool 分离的、有界 approval-action spool，再调用新的本地认证 endpoint（例如 `/api/feishu-chat/card-action-worker`）。envelope 包含 schema、request id、worker instance id、message/chat id、operator ids 和 action value；后端适配后进入现有统一 `_handle_feishu_card_action` 分发器。callback 暂时不可达时，worker 可即时向飞书返回“处理中”，由 spool 有界重试；后端 durable claim 处理重复投递。

`legacy-python` transport 同样复用通用通知框架出站，并把现有长连接 card action 适配到统一分发器。两种 transport 的业务状态机和发送路径一致，仅 callback receiver 实现不同。

备选方案是给 Chat App worker 另建一套发卡协议，或把卡片伪装成普通 `send/reply`。前者重复通用通知框架已有的 token、发送和审计能力，后者会生成 chat delivery record 和历史投影，因此均不采用。

### 6. 统一卡片模型与已处理状态

Codex intent builder 复用通用 `build_feishu_card`，只配置两个有效动作：

- `codex_approval_once`
- `codex_approval_cancel`

卡片展示 Agent、审批类别、受限摘要和创建时间；命令、路径和权限描述均先做秘密脱敏和长度限制。卡片不包含凭据、完整环境、附件内容或可被客户端修改的权威关联字段。

每次成功/可能成功投递都保存 delivery reference（application kind、message id、chat/recipient 类型、attempt id）。首个有效 decision commit 后，把同一 intent 的 `state` 更新为 `approved` 或 `cancelled`、去除 decision actions，并通过通用更新 helper 对所有已知引用 fan-out。更新失败只写审计和指标，不回滚权威决策，也不再次调用 provider。

### 7. 回调先鉴权和关联，再 exactly-once 续接

通知应用动作沿用飞书长连接的可信事件入口；Chat App 动作必须通过 loopback endpoint、每进程随机 token、worker instance id 和严格 schema 校验。业务层还必须校验：

- operator 与冻结的原发起人至少有一个稳定 ID 相等；
- route 当前属于同一 provider、Agent、conversation、thread/turn 和 approval；
- 动作是 approve-once 或 cancel；
- route 尚未 resolved/failed/expired。

校验通过后持久 claim。只有 claim owner 调用 `_handle_codex_approval_respond`；replay 返回已处理结果，busy 返回处理中，冲突或迟到动作返回不可更改。provider choice 映射为现有 Codex `approve`/`cancel`，不开放持续授权。

回调来源标记为 `source=feishu-card` 且 `recordChatHistory=false`。Codex respond handler 在该策略下跳过 `_append_codex_approval_result_comm_event`，但仍发布 provider event，并把 content-free lifecycle 记录写入独立 approval audit。Web Chat 未携带该策略时保持现状。

### 8. 投递失败必须异步关闭等待

approval event callback 只注册路由并尝试提交到有界 delivery executor，不执行飞书网络请求。队列满、主投递失败且 fallback 失败、或超过总投递 deadline 都进入统一 failure closure：

1. 以 cancel/deny 方式只调用一次原 Codex approval continuation，保证受保护动作不执行；
2. 标记 route 为 terminal failed；
3. 让原 `_handle_codex_chat` turn 继续并优先发送 provider 的正常终局回复；
4. 若 provider 没有生成可见结果，则由原 turn 的正常回复路径生成“审批卡片无法送达，操作已取消”的失败回复。

该失败回复是 turn 的正常结果，可以保留现有 VO/飞书历史；审批卡片和动作本身仍不进入历史。如果正常失败回复也无法发送，只在 turn delivery 状态和独立审批审计中保留 non-success terminal，不重新创建 pending。

executor 的并发数、队列长度、单次 timeout、总 deadline 和 retry 次数都必须可配置且有上限。服务关闭时停止接收新任务，并对尚未投递的 live route 执行安全取消或标记为恢复时过期。

飞书入站 source index 也必须区分 `claimed` 与已经越过 provider 边界的 `dispatching`。新进程可以重新 claim 尚未 dispatch 的旧消息；对于 owner 已变化的 `dispatching` 消息，不得重放 provider 调用，而是原子写入 interrupted terminal、尽力发送可见中断提示并确认 worker spool 的该条消息，使同 chat 后续已落盘消息继续按序处理。该策略坚持 at-most-once，同时避免不确定旧执行成为永久 poison head。

### 9. pending approval 对 presence 有状态优先级

Codex active state 增加“存在未解决 approval”的派生判断。只要当前 turn 的 approval 仍 pending/resolving，后到的 `tool.completed`、辅助通信完成或其他非终局 activity 不得把 Agent 覆盖为 idle；只有 approval resolved/failed、turn terminal 或显式 cancel 才能清除 waiting 状态。

该修正不改变 provider 事件顺序，只改变 presence projection 的优先级，避免界面显示“空闲”而实际等待审批。

### 10. 可观测性与配置

通用通知记录继续作为投递/更新审计，现有 `feishu-card-actions.jsonl` 继续作为动作入口审计；durable route repository 保存审批权威状态。对通用审计增加轮转/容量上限和 approval route/attempt 关联字段，不复制完整卡片内容。新增指标至少覆盖：eligible approvals、primary attempts/success/failure/ambiguous、fallback attempts/success/failure、callback accepted/replay/rejected/busy、provider resolution、card update failure、delivery closure、queue saturation 和 recovery-expired。日志和 audit 只保存指纹、ID、分类错误及脱敏摘要。

新增 `VO_CODEX_FEISHU_APPROVAL_CARDS_ENABLED` 总开关，代码默认启用以提供新能力；部署时可先显式关闭再灰度打开。关闭开关只阻止创建新的飞书审批路由，不改变 Web Chat 审批；已有 live route 必须先安全取消或等待终局，不能被静默遗弃。

VIVO 的 Codex 设置新增面向用户的 `codex.routeApprovalsThroughVo` 复选项及中英文 i18n，默认值为 `false`，并提供 `VO_CODEX_ROUTE_APPROVALS_THROUGH_VO` 环境变量覆盖。未勾选时不向 Codex runtime 注入任何 approval hook 覆盖，并保持原有 `approvalPolicy=on-request`，继续使用用户原有 Codex/Desktop 配置。勾选后，VO 只在自己启动的 `codex app-server` 进程参数中把当前 `CODEX_HOME/hooks.json` 里的 `PermissionRequest` hook state 设为 disabled，并把该 runtime 的 thread/turn `approvalPolicy` 设为 `untrusted`，使受保护操作产生原生 `item/*/requestApproval` server request 并回到 VO；sandbox 的 `networkAccess` 仍保持关闭，不修改全局 `hooks.json`，也不影响 Desktop 或其他 Codex 进程。bridge cache key 包含该选项与 Codex home，配置切换会创建匹配的新 runtime。

飞书入站的 reaction/临时回执属于尽力而为的交互反馈，不得位于 provider dispatch 的同步关键路径。生产 worker 使用 daemon acknowledgement task 并立即进入 Agent dispatch；turn 结束后 task 再删除 reaction 或撤回临时回执，并把结果写入独立 channel audit。直接调用与测试保留同步模式，便于确定性验证。

## Risks / Trade-offs

- [通知应用与 Chat App 的 `open_id` 可能属于不同应用身份域] → 优先使用 `union_id`，其次使用可验证的 `user_id`；无法安全映射时立即回退 Chat App，绝不使用固定收件人猜测。
- [通知应用响应丢失会产生两张卡] → 所有 delivery 共用一个 durable route fence，首个有效决定生效，终局后更新全部已知卡片。
- [provider 已响应但 route commit 前进程崩溃] → 持久 claim 后再调用 provider；恢复时不重试不确定的 provider decision，以 at-most-once 为安全边界并将卡片标记 unavailable。
- [后台队列或飞书接口拥塞] → 设置有界队列、短超时、有限重试和总 deadline；饱和直接进入安全取消闭环，不让 turn 无限等待。
- [通用通知发送器的 `skipped_*` 状态 historically 表示调用成功] → 审批 policy wrapper 只接受 `status=sent`，其余状态触发 fallback 或安全取消，不改变普通通知兼容语义。
- [卡片动作 spool 导致延迟反馈] → 飞书侧先返回“处理中”，后台可靠投递；durable claim 去重，最终 card update 显示权威结果。
- [卡片更新失败导致旧按钮仍可点击] → 服务端 route 状态始终是权威 fence；旧按钮只能得到已处理/已过期响应，更新失败单独告警。
- [approval 摘要包含命令参数或路径中的秘密] → 使用 provider payload allowlist、秘密脱敏、字段和总卡片大小上限；审计不保存完整卡片内容。
- [独立持久仓库持续增长] → pending、resolved 和 audit 都有容量/TTL/轮转上限；淘汰 unresolved 前先安全取消或标记 expired。
- [legacy 与 Node transport 行为漂移] → 以统一 adapter contract 和共享 contract tests 约束；Channel SDK 为首要生产路径，legacy 只保留兼容实现。

## Migration Plan

1. 增加 route repository、协调器、共享 card builder、独立 audit 和单元测试；总开关保持关闭进行本地验证。
2. 使用通用通知框架已有的 per-call `app_config` 实现动态收件人，并向后兼容补齐 `messageId` 返回和 card update；Chat App worker 只补 cardAction callback，完成发送、fallback、回调和更新的 contract/integration tests。
3. 接入 Codex approval event 和 source-aware respond policy，验证 Web Chat 行为不变、飞书审批事件不进入 comm/chat history。
4. 在测试租户开启开关，分别验证：通知应用成功、未配置通知应用、主投递失败回退、ambiguous 双卡、重复/冲突动作、两路失败关闭等待、Chat App callback 暂时不可达恢复。
5. 小范围灰度并观察 queue saturation、callback rejection、delivery closure 和 pending duration；确认无异常后扩大范围。
6. 回滚时先停止创建新 route，等待或安全取消 live approvals 并尽力更新卡片为 unavailable，然后关闭开关；Web Chat 审批继续工作。数据模型为新增的独立仓库，无需迁移既有聊天历史。

## Open Questions

无阻塞问题。实现阶段仍需用测试租户确认通知应用对 `union_id` 的权限范围；若租户权限不足，既定行为是将该次主投递判定为不可路由并回退 Chat App，不改变产品语义。
