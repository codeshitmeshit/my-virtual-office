# Acceptance Audit

需求：`feishu-ceo-agent-chat-sync`

更新时间：2026-07-04T19:18:02+08:00

## 结论

当前实现已经完成主要开发和模拟/自动化验收。真实飞书 chat app 长连接端到端仍未执行，因此本需求不能标记为最终 `tested` 或 `done`。

自动化已覆盖：

- 双飞书应用配置分离。
- chat app 长连接消息回调。
- Feishu sender 绑定配置、读取和 route。
- inbound-test route 进入 Feishu channel adapter。
- 代表 Agent dispatch、切换、缺失和不可用路径。
- 强制 VO 记录、幂等、连续消息顺序。
- 私聊 text 范围约束。
- 飞书文本发送 helper 的 chat app credential flow。
- 旧 Feishu notification/card-action 聚焦回归。

仍需真实环境证明：

- 飞书平台真实长连接事件能抵达 VO 进程。
- chat app 的真实事件权限和发送消息权限配置正确。
- 真实飞书私聊中能收到 `CEO (by <Agent>)` 回复。

## Checklist Audit

| ID | 状态 | 当前证据 | 剩余动作 |
| --- | --- | --- | --- |
| CHK-001 | 自动化通过 | `test_feishu_chat_config_is_separate_from_notification_app`、`test_feishu_chat_config_rejects_unknown_representative_agent` 覆盖代表 Agent 配置和校验。 | 真实设置页可再人工确认保存体验。 |
| CHK-002 | 自动化通过 | notification app 与 chat app 配置分离测试；配置读写保留旧通知配置。 | 无。 |
| CHK-003 | 自动化通过 | Feishu output adapter 包装 `CEO (by <Agent>)`，测试验证发送文本和 `feishuReply`。 | 真实飞书客户端中人工确认展示。 |
| CHK-004 | 自动化通过 | bindings 函数级和 route 级测试；inbound-test route 触发绑定用户链路。 | 真实飞书 sender ID 需人工绑定验证。 |
| CHK-005 | 自动化通过 | 未绑定用户不 dispatch，发送绑定提示并记录 `unbound_user`。 | 真实飞书未绑定账号可再跑 AC-002。 |
| CHK-006 | 自动化通过 | long connection receiver message handler 测试；缺凭证拒绝；仅配置 `receiveMode=long_connection`。 | 真实飞书长连接启动和事件抵达仍需 AC-001。 |
| CHK-007 | 自动化通过 | Feishu adapter dispatch 到现有 Hermes/Codex/Claude/OpenClaw path；metadata 写入 provider history/comm event。 | 无。 |
| CHK-008 | 自动化通过 | assistant reply 写 VO channel record，Feishu text sender helper 测试覆盖 `/im/v1/messages`。 | 真实飞书发送权限需 AC-001。 |
| CHK-009 | 部分自动化通过 | Hermes history metadata 测试证明现有 provider history 可审计来源字段。 | 可在真实 UI 中人工查看历史展示。 |
| CHK-010 | 自动化通过 | 未新增独立 CEO 私聊面板；复用原设置区和 provider pipeline。 | 无。 |
| CHK-011 | 自动化通过 | 代表 Agent 切换测试证明未来消息使用新 `representativeAgentId`。 | 无。 |
| CHK-012 | 自动化通过 | 切换测试保留旧记录，不要求迁移旧会话。 | 无。 |
| CHK-013 | 自动化通过 | sourceMessageId 幂等测试，重复投递不重复触发 Agent。 | 无。 |
| CHK-014 | 自动化通过 | 连续消息顺序测试证明同 conversationId 且记录顺序稳定。 | 并发线程级压力可后续增强，不阻塞本需求。 |
| CHK-015 | 自动化通过 | 未配置代表 Agent 入站提示、不 dispatch、记录 `missing_representative_agent`。 | 无。 |
| CHK-016 | 自动化通过 | 不存在代表 Agent 记录 `agent_failed`，发失败提示，无无限重试。 | 真实 provider 临时不可用可后续扩展集成测试。 |
| CHK-017 | 自动化通过 | 群聊和非 text 消息 ignored，不 dispatch、不回复。 | 无。 |
| CHK-018 | 自动化通过 | channel record 和 provider history/comm event 保留 Feishu source metadata。 | 无。 |
| CHK-019 | 自动化通过 | `recordMessages=false` 类配置不能阻止 `user_message/turn_completed` 记录。 | 无。 |
| CHK-020 | 聚焦回归通过 | `tests/test_feishu_notifications.py`、`tests/test_feishu_sync.py`、meeting request、Project Execution Feishu 聚焦回归通过。 | 全量 pytest 基线仍有非本需求失败，不能声称全仓库绿。 |
| CHK-021 | 聚焦回归通过 | `node --check app/game.js`、provider history metadata、Project Execution Feishu 聚焦回归通过。 | 普通聊天真实 UI 回归可人工抽查。 |
| CHK-022 | 待真实验收 | `manual-acceptance.md` 已给出 AC-001 到 AC-005。 | 必须用真实飞书 chat app 长连接执行。 |

## 当前不能 Done 的原因

`CHK-022` 需要真实飞书平台事件和真实 chat app 权限证明。当前仓库没有可用的真实飞书 app 凭证、飞书测试用户事件和飞书客户端回执证据，因此只能证明 VO 侧实现和模拟链路，不能证明真实平台端到端。

## Done 前必须补充的证据

- `manual-acceptance.md` 中 AC-001 到 AC-005 的执行结果。
- 至少一条真实 `feishu-channel-records.jsonl` 中 `turn_completed` 记录，包含真实 `sourceMessageId` 和 `feishuChatId`。
- 飞书客户端收到 `CEO (by <Agent>)` 回复的截图或文字记录。
- 真实测试后在 `checklist.md` 追加人工测试执行记录，并更新 `status.json.confirmations.tested`。
