# Codex 飞书审批卡片运维指南

本文说明飞书来源的 Codex command、file-change 和 permission approval 如何投递、回调、审计、灰度与回滚。Web Chat 审批行为不受此能力影响。

## 路由规则

1. 只有 `sourceApp=feishu` 且来源为 `feishu-dm` 或 `feishu-group` 的安全审批会生成卡片。
2. 配置完整的通知应用时，优先使用通知应用，并按原消息用户的 `union_id`、`user_id` 顺序选择收件身份。只有通知应用与 Chat App 使用同一个 App ID 时才允许复用 `open_id`。
3. 通知应用未配置、身份不可迁移、发送失败或结果不确定时，使用 Chat App 凭据向原始 `feishuChatId` 回退。
4. 通知配置中的固定 `VO_FEISHU_RECEIVE_ID` 不用于 Codex 交互审批；`VO_FEISHU_NOTIFICATION_WEBHOOK` 也不用于交互审批。固定收件人和 webhook 无法同时满足“原发起人”和可信动作回调要求。
5. 主卡片和回退卡片共享同一个 durable route。首个有效的 approve-once 或 cancel 决定生效，重复、冲突和迟到动作不会再次调用 Codex。

卡片、卡片更新、动作和动作确认不会写入 VO chat history、provider conversation history 或 agent-platform communication history。原用户消息和 Codex 的正常最终回复/终局失败仍沿用原历史链路。

## 配置

通知应用：

- `VO_FEISHU_NOTIFICATION_ENABLED=true`
- `VO_FEISHU_APP_ID`
- `VO_FEISHU_APP_SECRET`
- 通知应用必须启用卡片动作长连接能力。

Chat App fallback：

- `VO_FEISHU_CHAT_ENABLED=true`
- `VO_FEISHU_CHAT_APP_ID`
- `VO_FEISHU_CHAT_APP_SECRET`
- `channel-sdk-node` transport 会将 `cardAction` 写入独立的有界 spool，并通过带进程 token 的 loopback `/api/feishu-chat/card-action-worker` 交给 VO；普通聊天入站 endpoint 不处理审批动作。
- `legacy-python` transport 通过现有长连接进入同一个统一卡片分发器。

审批执行参数：

| 环境变量 | 默认值 | 约束与用途 |
| --- | ---: | --- |
| `VO_CODEX_FEISHU_APPROVAL_CARDS_ENABLED` | `true` | 总开关；关闭后不创建新 route，Web Chat 审批保持可用 |
| `VO_CODEX_FEISHU_APPROVAL_WORKERS` | `2` | 后台投递并发，范围 1–16 |
| `VO_CODEX_FEISHU_APPROVAL_QUEUE` | `16` | 等待队列容量，范围 0–256 |
| `VO_CODEX_FEISHU_APPROVAL_DEADLINE_SEC` | `12` | 单个投递任务总 deadline，范围 0.05–60 秒 |
| `VO_FEISHU_AUDIT_MAX_BYTES` | `5242880` | notification/card-action 单个 JSONL 文件轮转阈值 |
| `VO_FEISHU_AUDIT_BACKUPS` | `3` | 审计备份数量，范围 1–10 |

队列饱和、超过 deadline 或主备两路都失败时，服务会 durable claim 该 route，以 cancel 方式只关闭一次原 Codex approval。原 turn 优先返回 provider 的终局回复；没有回复时生成“审批卡片无法送达，操作已取消。”。受保护动作不会执行。

## 审计、状态与指标

- `VO_STATUS_DIR/codex-feishu-approval-routes.json`：route、冻结的来源关联、delivery references、claim fence 和权威终态；原子写入、0600、有容量与 TTL 上限。
- `VO_STATUS_DIR/feishu-notification-records.jsonl[.N]`：脱敏的发送/更新结果，包含 route、attempt、application、operation 和 message ID。
- `VO_STATUS_DIR/feishu-card-actions.jsonl[.N]`：脱敏的 callback、actor ID、route 和业务结果；与普通聊天 ledger 分离。
- `GET /api/codex/feishu-approvals/status`：返回总开关、route 状态计数和进程内指标，不返回 App Secret、token、完整卡片或消息正文。

关键指标包括 eligible、notification/chat attempts 与 success/failure/ambiguous、callback accepted/replay/rejected/busy、provider resolution、card update failure、delivery closure、queue saturation、recovery expired 和 stale-card update。

## 灰度与验收

1. 部署前可显式设置 `VO_CODEX_FEISHU_APPROVAL_CARDS_ENABLED=false`，确认原 Web Chat 审批与 Chat App 普通消息正常。
2. 在测试租户打开开关，依次验证通知应用 primary、Chat-App-only、primary failure fallback、重复/冲突 callback、双路失败 closure。
3. 特别确认通知应用具备向原用户 `union_id` 发消息的权限。权限不足的预期行为是回退 Chat App，不得改用固定收件人。
4. 检查 status endpoint 中 queue saturation、delivery closure、callback rejected 和 pending duration，并核对两类审计文件没有秘密或完整命令内容。
5. 验证处理后的所有已知卡片无有效按钮；单卡更新失败时 route 仍保持唯一终态。

## 排障

- 通知应用没有收到卡片：检查 App ID/Secret、通知开关、长连接状态、`union_id` 权限及 notification failure 指标；随后检查 Chat App fallback 记录。
- Chat App 卡片能显示但按钮一直“处理中”：检查 Node worker 的 approval-action spool、worker token callback、loopback endpoint 和 `callback_*` 指标。不要把该事件重新投递到普通聊天 endpoint。
- VO 显示 idle 但 Codex 在等待：检查 active operation 的 `pending`/`resolving` 和 route 状态。pending approval 对 presence 具有高优先级。
- 出现两张卡：通常是 primary 结果不确定后发生 fallback。核对两张卡的 route ID；这是允许的，首个有效决定仍然唯一。
- 卡片仍可点击：检查 card update failure/stale-card update 指标。服务端 durable route 是权威 fence，旧按钮不会重复执行动作。
- route 在重启后变为 `resolved_unknown`/expired：表示 provider 调用与 durable commit 之间发生了不确定中断。系统选择 at-most-once，不会自动重放受保护动作。

## 回滚

1. 先关闭 `VO_CODEX_FEISHU_APPROVAL_CARDS_ENABLED`，停止创建新 route。
2. 等待 live route 终局；无法等待的 route 必须安全 cancel，并尽力把已知卡片更新为 `no_longer_actionable`。不要静默遗弃 pending approval。
3. 回滚应用版本并保留 route 与审计文件用于对账。无需迁移或清理既有 VO 聊天历史。
4. 验证 Web Chat 审批、Chat App 普通消息和最终回复历史仍正常。
5. 如果回滚版本不认识新 route 文件，保留文件但不要手工重放其中的 resolving decision。
