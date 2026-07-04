> English version: [AGENT_PLATFORM_COMMUNICATIONS.md](AGENT_PLATFORM_COMMUNICATIONS.md)

# AgentPlatform 到 AgentPlatform 通信

状态：首个可工作实现

## 目标

为“我的虚拟办公室”提供内建的通信层，使 Agent 平台能够通过办公室相互对话，而不是通过屏幕外的私有 CLI 调用。

这是 OpenClaw、Hermes、Codex 及未来提供者适配器之间实现可见跨平台对话的基础。

## 内建技能

技能名称：

`AgentPlatform-to-AgentPlatform_Communications`

该技能被植入虚拟办公室技能库，同时通过以下地址暴露：

`GET /api/agent-platform-communications/skill`

Agent 可以读取/应用该技能，无需自定义代码即可了解端点。

## 发送端点

`POST /api/agent-platform-communications/send`

请求体：

```json
{
  "fromAgentId": "main",
  "toAgentId": "hermes-default",
  "message": "Hi Hermes, can you review this?",
  "conversationId": "optional-thread-id",
  "metadata": {"topic": "optional"}
}
```

响应：

```json
{
  "ok": true,
  "conversationId": "main__hermes-default",
  "messageId": "...",
  "replyMessageId": "...",
  "reply": "..."
}
```

## 历史记录端点

`GET /api/agent-platform-communications/history?conversationId=<id>`

可选筛选条件：

- `conversationId`
- `agentId`
- `limit`

事件存储于：

`VO_STATUS_DIR/agent-platform-communications.jsonl`

每个事件具有标准化结构，包含：

- schema
- id
- timestamp
- conversationId
- direction：`request` 或 `reply`
- from agent ref
- to agent ref
- text
- metadata
- visibleInOffice 标记

## 当前路由

通信层通过服务端 agent-call 抽象进行路由：

- OpenClaw 目标使用现有的 OpenClaw 工作流/网关/CLI 路径。
- Hermes 目标使用 Hermes 提供者适配器。
- Codex 目标在 `VO_CODEX_ENABLED=1` 时使用可选的 Codex harness 适配器。
- 未来提供者应实现提供者适配器接口，然后可通过同一层调用。

## 可见性

该实现将对话记录在办公室拥有的通信日志中。`/agent-chat` 将这些通信事件合并到每个相关 Agent 的聊天气泡负载中，从而使跨平台 Agent 对话可见，而非在屏幕外发生。

## 已验证

产品实例测试已通过：

- skill 端点返回有效的 SKILL.md 内容
- skill 出现在技能库中
- `main` → `hermes-default` 消息成功路由
- Hermes 回复被记录为回复事件
- history 端点返回请求和回复
- Hermes 状态在调用期间切换为工作中，调用结束后恢复为空闲
- `/agent-chat` 在两个参与 Agent 下显示请求/回复事件

Codex 实时桥接：

- `VO_CODEX_ENABLED=1` 发现 `codex-local`，无需 OpenClaw/Hermes
- `VO_CODEX_REPLY_TEXT=<text>` 为通信测试提供确定性的演示回复
- 未设置 `VO_CODEX_BRIDGE_URL` 时，虚拟办公室使用本地 `codex app-server` 桥接
- Codex 事件持久化保存线程、轮次、终端状态、修改文件及干预元数据
- 办公室对话在刷新和服务重启后恢复映射的 Codex 线程
- 可通过专用端点压缩或重置 Codex 上下文
