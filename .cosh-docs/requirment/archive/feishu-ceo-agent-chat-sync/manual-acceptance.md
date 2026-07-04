# Manual Acceptance Runbook

需求：`feishu-ceo-agent-chat-sync`

更新时间：2026-07-04T19:02:07+08:00

## 目标

用真实飞书 chat app 长连接完成端到端验收，证明：

- 飞书私聊消息可以进入 VO。
- 绑定用户才能触发代表 Agent。
- 代表 Agent 的回复能发回同一个飞书私聊。
- VO 侧强制记录 user message、assistant reply、Feishu source metadata 和实际发送文本。
- 切换代表 Agent 后，后续飞书消息使用新的 Agent。

## 前置条件

- VO 服务已启动，且使用本次实现代码。
- 已准备一个飞书企业自建应用作为 chat app。
- chat app 已配置长连接能力，并具备接收 `im.message.receive_v1` 事件的权限。
- chat app 具备发送文本消息到私聊的权限。
- 已获取 chat app 的 `appId` 和 `appSecret`。
- VO 中至少有一个可用 Agent，可作为 CEO representative Agent。
- 已知测试飞书用户的 `open_id`、`user_id` 或 `union_id`。

## 配置步骤

1. 打开 VO 设置页。
2. 找到 `Feishu Chat App` 配置区。
3. 勾选启用 chat channel。
4. 填入 chat app 的 `App ID` 和 `App Secret`。
5. 在 `Representative Agent ID` 填入一个有效 VO Agent ID，例如 `hermes-default`。
6. 保存 chat app 配置。
7. 确认 long connection 状态不是 `missing_app_credentials`。
8. 在 `Feishu User Bindings` 中添加测试用户绑定，一行一个：

```text
open_id:ou_xxx=user-1
```

也可以使用：

```text
user_id:u_xxx=user-1
union_id:on_xxx=user-1
chat_id:oc_xxx=user-1
```

9. 保存 bindings。

## 验收用例

### AC-001 已绑定用户私聊

步骤：

1. 使用已绑定的飞书用户，私聊 chat app 发送：`hello from feishu acceptance`。
2. 等待 VO Agent 回复。
3. 在飞书私聊中检查回复文本。
4. 在 VO 状态目录检查 `feishu-channel-records.jsonl`。
5. 或调用 `GET /api/feishu-chat/records?limit=20` 检查最近的 VO channel 记录。

预期：

- 飞书收到回复，格式类似：

```text
CEO (by <Agent>):
<Agent reply>
```

- `feishu-channel-records.jsonl` 至少包含：
  - `event=user_message`
  - `event=turn_completed`
- `turn_completed` 记录包含：
  - `channel=feishu`
  - `sourceApp=feishu`
  - `sourceSurface=feishu-dm`
  - `sourceMessageId`
  - `feishuChatId`
  - `voUserId`
  - `representativeAgentId`
  - `reply`
  - `feishuReply`
  - `sendResult`

### AC-002 未绑定用户拒绝

步骤：

1. 删除或不要配置测试飞书用户绑定。
2. 使用该飞书用户私聊 chat app 发送任意文本。
3. 检查飞书回复和 VO 记录。

预期：

- 飞书收到绑定提示。
- VO 不触发代表 Agent。
- `feishu-channel-records.jsonl` 记录 `event=rejected`、`reason=unbound_user`。

### AC-003 切换代表 Agent

步骤：

1. 将 `Representative Agent ID` 设置为 Agent A。
2. 用已绑定飞书用户发送第一条消息。
3. 将 `Representative Agent ID` 改为 Agent B 并保存。
4. 用同一飞书用户发送第二条消息。
5. 检查 VO 记录。

预期：

- 第一条消息的 `representativeAgentId` 是 Agent A。
- 第二条消息的 `representativeAgentId` 是 Agent B。
- 旧会话不需要归档、迁移或关闭。

### AC-004 重复投递幂等

步骤：

1. 使用 `/api/feishu-chat/inbound-test` 或测试工具重复投递同一个 `message_id`。
2. 检查 VO 记录和 Agent 调用次数。

预期：

- 只触发一次代表 Agent。
- 第二次结果为 `duplicate` 或等价幂等状态。
- 不重复写入新的 `turn_completed`。

### AC-005 非私聊和非文本消息

步骤：

1. 模拟或触发群聊消息。
2. 模拟或触发非 text 消息。

预期：

- 群聊消息记录为 `ignored_unsupported_chat_type`。
- 非 text 消息记录为 `ignored_unsupported_message_type`。
- 不触发代表 Agent。

## 可替代模拟命令

没有真实飞书事件时，可以用 inbound-test route 验证 VO 侧处理链路：

```bash
curl -sS http://127.0.0.1:<VO_PORT>/api/feishu-chat/inbound-test \
  -H 'Content-Type: application/json' \
  -d '{
    "event": {
      "sender": {"sender_id": {"open_id": "ou_xxx"}},
      "message": {
        "message_id": "om_acceptance_001",
        "chat_id": "oc_acceptance_001",
        "chat_type": "p2p",
        "message_type": "text",
        "text": "hello from feishu acceptance"
      }
    }
  }'
```

模拟命令可以验证 VO 侧 route、binding、adapter、Agent dispatch、recording，但不能替代真实飞书长连接和飞书发送权限验收。

## 通过标准

- AC-001 到 AC-005 均符合预期。
- `feishu-channel-records.jsonl` 无明文 app secret。
- 飞书 notification app 原通知/card-action 流程仍可用。
- chat app 配置没有覆盖 notification app 配置。
- 真实验收结果需要回填到 `checklist.md` 的测试执行记录。

## 失败排查

- `missing_app_credentials`：检查 chat app `appId/appSecret` 是否保存。
- `disabled`：检查 chat channel 是否启用。
- `unbound_user`：检查 `open_id/user_id/union_id/chat_id` 与 VO user 绑定。
- `missing_representative_agent`：检查 `Representative Agent ID` 是否已保存。
- `agent_not_found`：检查代表 Agent 是否存在于 VO roster。
- `sendResult.ok=false`：检查 chat app 发送消息权限、tenant token、chat_id 是否正确。
- receiver 状态为 `missing_message_event_handler`：检查当前 `lark_oapi` SDK 是否支持 `register_p2_im_message_receive_v1`。
