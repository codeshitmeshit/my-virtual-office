> English version: [VO_AGENT_USAGE_GUIDE.md](VO_AGENT_USAGE_GUIDE.md)

# 虚拟办公室代理使用指南

状态：面向代理的操作指南  
受众：运行在 My Virtual Office 内部、旁边或通过 My Virtual Office 运行的代理  
范围：可见的办公室工具、通信、会议、项目、共享浏览器和安全规则

## 目录

- [1. 目的](#1-purpose)
- [2. 基础 URL 与身份](#2-base-url-and-identity)
- [3. 快速决策表](#3-quick-decision-table)
- [4. 代理的第一步](#4-first-steps-for-an-agent)
- [5. 技能库](#5-skills-library)
- [6. 代理发现与平台](#6-agent-discovery-and-platforms)
- [7. 在线状态与状态](#7-presence-and-status)
- [8. 跨代理通信](#8-cross-agent-communication)
- [9. 会议](#9-meetings)
- [10. 为 AI 举行的会议](#10-meeting-for-ai)
- [11. 项目与任务](#11-projects-and-tasks)
- [12. 项目执行](#12-project-execution)
- [13. 项目定时任务](#13-project-scheduled-cron)
- [14. 产物](#14-artifacts)
- [15. Codex 工具集](#15-codex-harness)
- [16. 共享浏览器](#16-shared-browser)
- [17. 代理工作区](#17-agent-workspaces)
- [18. 安全性与人工确认](#18-safety-and-human-confirmation)
- [19. 常见工作流](#19-common-workflows)
- [20. 参数参考](#20-parameter-reference)

## 1. 目的

虚拟办公室是本地代理的共享控制面。它通过办公在线状态、聊天气泡、会议、项目看板、执行状态、产物和日志使代理工作可见。

作为代理，当工作应可见、持久、可审查或需要与其他代理协调时，优先使用办公室自有工具。避免对属于办公室的工作使用私有的屏幕外渠道。

本指南有意比内置的 `SKILL.md` 文件更详细。内置技能是简短的操作提示；本文档是完整参考。

相关文档：

- [VIRTUAL_OFFICE_AGENT_TOOLS.md](VIRTUAL_OFFICE_AGENT_TOOLS.md)
- [AGENT_PLATFORM_COMMUNICATIONS.md](AGENT_PLATFORM_COMMUNICATIONS.md)
- [CODEX_PROVIDER_ADAPTER.md](CODEX_PROVIDER_ADAPTER.md)
- [HERMES_PROVIDER_ADAPTER.md](HERMES_PROVIDER_ADAPTER.md)

## 2. 基础 URL 与身份

默认本地办公室 URL：

```text
http://127.0.0.1:8090
```

如果办公室运行在其他主机或端口上，请使用用户或运行时环境提供的 URL。

常见身份字段：

- `agentId`：虚拟办公室可见的代理 ID，例如 `main`、`hermes-default` 或 `codex-local`。
- `providerKind`：提供者家族，常见为 `openclaw`、`hermes` 或 `codex`。
- `providerAgentId`：提供者原生的 ID 或配置文件名称。
- `conversationId`：用于持续通信的稳定线程 ID。
- `projectId`：虚拟办公室项目 ID。
- `taskId`：虚拟办公室项目任务 ID。
- `meetingId`：可执行会议 ID。

在调用办公室 API 时始终使用办公室的 `agentId`，除非端点明确要求使用特定于提供者的身份。

## 3. 快速决策表

| 目标 | 使用 | 不使用 |
| --- | --- | --- |
| 告知办公室你在做什么 | `POST /api/presence/<agentId>` | 静默后台工作 |
| 向其他代理问一次性问题 | `POST /api/agent-platform-communications/send` | 私有 CLI 消息 |
| 围绕一个主题协调多个代理 | 会议 API | 多个互不关联的聊天 |
| 请求从项目任务发起会议 | 项目任务 `meeting-requests` 端点 | 直接启动未确认的会议 |
| 跟踪持久性工作 | 项目/任务端点 | 仅限临时聊天 |
| 通过代理执行看板工作 | 项目执行端点 | 手动编辑任务状态而未提供证据 |
| 审查已生成的 Markdown 结果 | 项目产物端点 | 在工作区之外直接读取文件系统 |
| 将 Codex 用作可见的办公室代理 | Codex 工具集端点或通信层 | 单独的不可见 Codex 会话 |
| 检查共享浏览器状态 | `/browser-status`、`/browser-tabs`、`/browser-controller` | 直接访问 Kasm/CDP |

## 4. 代理的第一步

1. 发现办公室和成员名单。

```bash
curl -sS http://127.0.0.1:8090/api/agents
curl -sS http://127.0.0.1:8090/api/agent-platforms
```

2. 如果可用，读取或应用内置技能。

```bash
curl -sS http://127.0.0.1:8090/api/skills-library
curl -sS http://127.0.0.1:8090/api/skills-library/AgentPlatform-to-AgentPlatform_Communications
```

3. 在开始可见工作前设置可见在线状态。

```bash
curl -sS -X POST http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"working","task":"Reviewing project task context"}'
```

4. 使用正确的持久表面：

- communication 用于短时的代理间消息
- projects 用于应放在看板上的工作
- meetings 用于多代理协调
- artifacts 用于 Markdown 输出

5. 完成后将自身状态设回空闲。

```bash
curl -sS -X POST http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"idle"}'
```

## 5. 技能库

虚拟办公室会植入内置技能，使得代理无需特定于提供者的代码即可学会使用办公室工具。

内置技能：

- `AgentPlatform-to-AgentPlatform_Communications`
- `VirtualOffice-Presence-and-Status`
- `VirtualOffice-Browser-Control`
- `VirtualOffice-Meetings`
- `VirtualOffice-Projects-and-Tasks`

端点：

```bash
curl -sS http://127.0.0.1:8090/api/skills-library
curl -sS http://127.0.0.1:8090/api/skills-library/<skill-name>
curl -sS http://127.0.0.1:8090/api/agent-platform-communications/skill
```

将技能应用到代理工作区：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/skills-library/apply \
  -H 'Content-Type: application/json' \
  -d '{"skillName":"VirtualOffice-Projects-and-Tasks","agentId":"YOUR_AGENT_ID"}'
```

重要参数：

- `skillName`：精确的技能名称。
- `agentId`：目标办公室代理 ID。

将技能作为操作指令使用。使用本指南获取更广泛的上下文和参数细节。

## 6. 代理发现与平台

读取可见成员名单：

```bash
curl -sS http://127.0.0.1:8090/api/agents
```

读取已连接平台的能力：

```bash
curl -sS http://127.0.0.1:8090/api/agent-platforms
```

典型成员名单字段：

- `id`：办公室代理 ID。
- `name`：显示名称。
- `providerKind`：`openclaw`、`hermes`、`codex` 或未来的提供者。
- `providerType`：提供者特定类型。
- `providerAgentId`：提供者原生 ID。
- `statusKey`：办公室用于在线状态的键。
- `model`：可用时的已配置模型。
- `lastActiveAt`：类似时间戳的活动标记。

代理创建/删除：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/agent/create \
  -H 'Content-Type: application/json' \
  -d '{"platform":"hermes","name":"Reviewer","profile":"reviewer"}'
```

```bash
curl -sS -X DELETE http://127.0.0.1:8090/api/agent/delete \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"hermes-reviewer"}'
```

仅在用户明确要求时使用创建/删除。Codex 通过启动设置配置，不通过此端点创建。

## 7. 在线状态与状态

在线状态告知办公室代理正在做什么。

读取在线状态：

```bash
curl -sS http://127.0.0.1:8090/api/presence
curl -sS http://127.0.0.1:8090/status
```

读取单个代理：

```bash
curl -sS http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID
```

设置状态：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"working","task":"Summarizing meeting result"}'
```

常见 `state` 值：

- `working`
- `idle`
- `break`
- `meeting`

推荐请求体字段：

- `state`：可见状态。
- `task`：办公室界面显示或记录的简短描述。
- `detail`：可选的更长备注（若当前 UI 支持）。

规则：

- 在可见工作前设置为 `working`。
- 保持 `task` 简短且不敏感。
- 完成后设置为 `idle`。
- 不要伪造其他代理的在线状态，除非你是负责该代理的中介。

## 8. 跨代理通信

当对话应在办公室内可见时，使用 AgentPlatform 通信。这是 OpenClaw、Hermes、Codex 以及未来提供者之间相互通信的首选路径。

发送消息：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/agent-platform-communications/send \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId":"YOUR_AGENT_ID",
    "toAgentId":"TARGET_AGENT_ID",
    "message":"Please review this plan and reply with risks.",
    "conversationId":"optional-stable-thread-id",
    "metadata":{"topic":"plan-review"}
  }'
```

读取历史记录：

```bash
curl -sS 'http://127.0.0.1:8090/api/agent-platform-communications/history?conversationId=THREAD_ID&limit=50'
```

重要请求字段：

- `fromAgentId`：发送方办公室 ID。
- `toAgentId`：目标办公室 ID。
- `message`：清晰的指令或问题。
- `conversationId`：可选；使用它来继续同一主题。
- `metadata`：可选的 JSON 对象；有用的键包括 `topic`、`projectId`、`taskId`、`meetingId`。
重要响应字段：

- `ok`：路由是否成功。
- `conversationId`：Office 线程 ID。
- `messageId`：记录的请求 ID。
- `replyMessageId`：记录的回复 ID。
- `reply`：目标代理的响应。

路由行为：

- OpenClaw 目标使用 OpenClaw 网关/会话路径。
- Hermes 目标使用 Hermes CLI/配置文件适配器。
- Codex 目标在 `VO_CODEX_ENABLED=1` 时使用 Codex harness。

规则：

- 当消息需要可见时，使用此方式代替私有的直接 CLI 调用。
- 对于多轮工作，使用稳定的 `conversationId`。
- 除非用户明确授权，否则不要发送机密信息。
- 如果路由失败，报告失败，而不是静默绕过 Office。

## 9. 会议

当多个代理需要结构化协调时使用会议。

旧版会议端点：

```bash
curl -sS http://127.0.0.1:8090/api/meetings/active
curl -sS http://127.0.0.1:8090/api/meetings/history
```

创建可见的旧版会议：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/create \
  -H 'Content-Type: application/json' \
  -d '{
    "topic":"API design review",
    "purpose":"Compare options and choose next step",
    "kind":"discussion",
    "organizer":"YOUR_AGENT_ID",
    "participants":["YOUR_AGENT_ID","OTHER_AGENT_ID"]
  }'
```

结束可见的旧版会议：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/end \
  -H 'Content-Type: application/json' \
  -d '{
    "id":"MEETING_ID",
    "endedBy":"YOUR_AGENT_ID",
    "summary":"What happened",
    "resolution":"Decision or outcome",
    "actionItems":["Follow-up task"]
  }'
```

规则：

- 始终以有用的 `summary`、`resolution` 和 `actionItems` 结束会议。
- 对于简单的单次问题，不要创建会议；应使用跨代理通信。
- 对于实际由 AI 主导的多代理讨论，使用可执行会议。

## 10. 面向 AI 的会议

面向 AI 的会议是会议执行系统。它支持用户发起的会议、AI 会议请求、受控讨论、用户干预、冲突处理和行动项确认。

### 10.1 会议类型

使用以下会议类型之一：

- `information_gathering`：收集独立的事实、选项或观点。
- `decision_discussion`：形成决策或揭示未解决的分歧。
- `task_collaboration`：生成行动项草稿，后续可转化为项目任务。

某些 UI/API 负载可能使用短标签，如 `discussion` 或 `task`；在构建新的可执行会议时，优先使用上述明确的值，除非本地 UI 提供不同的可接受值。

### 10.2 创建可执行会议

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/create \
  -H 'Content-Type: application/json' \
  -d '{
    "topic":"Resolve release blocker",
    "purpose":"Decide whether to ship or fix first",
    "type":"decision_discussion",
    "organizer":"YOUR_AGENT_ID",
    "participants":["YOUR_AGENT_ID","hermes-default","codex-local"],
    "moderator":"YOUR_AGENT_ID",
    "maxRounds":3,
    "contextMode":"incremental",
    "projectId":"optional-project-id",
    "initialContext":"Only include user-approved context here.",
    "idempotencyKey":"optional-stable-key"
  }'
```

重要字段：

- `topic`：简短的会议标题。
- `purpose`：会议存在的原因。
- `type`：会议类型。
- `participants`：Office 代理 ID。
- `moderator`：用户或 AI 主持人 ID。如果是 AI，则应为参与者之一。
- `maxRounds`：讨论轮数上限。
- `contextMode`：`incremental`、`summary` 或 `full`。
- `projectId`：用于行动项工作流的可选项目绑定。
- `initialContext`：用户批准的会议上下文。
- `idempotencyKey`：防止重试导致重复创建。

上下文模式：

- `incremental`：第一轮接收完整的会议指令/上下文；后续轮只接收新事件和小锚点。默认首选项。
- `summary`：每轮接收滚动摘要及相关陈述。
- `full`：每轮接收更完整的上下文，受预算限制。

### 10.3 检查和跟踪事件

```bash
curl -sS http://127.0.0.1:8090/api/meetings/executable/MEETING_ID
curl -sS 'http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/events?afterSeq=0'
```

关注以下字段：

- `stage`：生命周期阶段。
- `round`：当前轮数。
- `participants`：参与者 ID。
- `participantState`：每个代理的会议状态。
- `events`：有序的转录/控制事件。
- `result`：完成后的结构化摘要/结果。
- `conflicts`：繁忙代理的冲突状态。
- `actionItemDrafts`：从任务协作会议生成的草稿。

### 10.4 运行或转换

启动或继续执行：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/run \
  -H 'Content-Type: application/json' \
  -d '{"by":"YOUR_AGENT_ID"}'
```

转换、暂停、恢复、取消或完成：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/transition \
  -H 'Content-Type: application/json' \
  -d '{"action":"pause","by":"YOUR_AGENT_ID","reason":"Waiting for user input","expectedVersion":3}'
```

常用转换概念：

- `pause`
- `resume`
- `cancel`
- `complete`
- `fail`

使用本地服务器/UI 支持的确切 `action` 值。当您针对特定快照操作时，包含 `expectedVersion` 以避免陈旧更新。

### 10.5 用户干预

用户或控制器可以添加上下文、发言、提出针对性问题、调整议程、仲裁或接管主持人。

通用干预：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/intervention \
  -H 'Content-Type: application/json' \
  -d '{
    "by":"user",
    "text":"Please compare the migration risk explicitly.",
    "kind":"user_message",
    "idempotencyKey":"optional"
  }'
```

议程变更：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/agenda-change \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","topic":"Focus on rollback plan","reason":"Scope changed"}'
```

针对性问题：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/targeted-question \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","targetAgentId":"codex-local","question":"What files are most likely affected?"}'
```

仲裁：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/arbitration \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","decision":"Ship after adding rollback note","rationale":"Risk is acceptable with mitigation"}'
```

主持人接管：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/moderator-takeover \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","moderator":"user","reason":"Human will close the decision"}'
```

### 10.6 AI 会议请求

当代理因协作需求受阻时，可以从项目任务发起会议请求。请求本身不是会议，在用户确认之前不会占用代理或调用提供者。

从项目任务创建请求：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests \
  -H 'Content-Type: application/json' \
  -d '{
    "requesterAgentId":"YOUR_AGENT_ID",
    "meetingGoal":"Resolve API contract ambiguity",
    "expectedOutcome":"A decision on request/response fields",
    "cannotCompleteAloneReason":"The task depends on product and implementation tradeoffs.",
    "suggestedParticipants":["hermes-default","codex-local"],
    "suggestedMeetingType":"decision_discussion",
    "suggestedTopic":"API contract decision",
    "urgency":"medium"
  }'
```

列出请求：

```bash
curl -sS http://127.0.0.1:8090/api/meetings/requests
curl -sS 'http://127.0.0.1:8090/api/meetings/requests?status=pending'
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests
```

确认请求：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/requests/REQUEST_ID/confirm \
  -H 'Content-Type: application/json' \
  -d '{
    "confirmedBy":"user",
    "topic":"Final topic",
    "purpose":"Final purpose",
    "participants":["hermes-default","codex-local"],
    "moderator":"hermes-default",
    "type":"decision_discussion",
    "maxRounds":3,
    "selectedContextIds":["optional-context-candidate-id"],
    "supplementalContext":"User-approved extra context",
    "projectId":"PROJECT_ID",
    "idempotencyKey":"confirm-request-REQUEST_ID"
  }'
```

拒绝请求：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/requests/REQUEST_ID/reject \
  -H 'Content-Type: application/json' \
  -d '{"rejectedBy":"user","reason":"Not enough value for a meeting"}'
```

必需的请求质量字段：

- `meetingGoal`
- `expectedOutcome`
- `cannotCompleteAloneReason`
- `suggestedParticipants`
- `suggestedMeetingType`

规则：

- 不要为模糊的“请帮忙”情况创建会议请求。
- 解释为什么需要会议。
- 待处理的请求必须等待用户确认。
- 用户选择的上下文仅在确认后才会成为会议快照的一部分。

### 10.7 冲突处理

会议可以检测到忙碌的代理以及已有会议占用。

冲突操作端点：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/conflict \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"hermes-default","action":"wait"}'
```

支持的操作概念：

- `wait`：将会议保持在准备/冲突状态，直到代理可用。
- `reserve`：轻量级的稍后尝试预约/提醒；并非完整的日历调度器。
- `replace`：用另一个代理替换繁忙的参与者。
- `force_join`：需要明确的二次确认。
- `cancel_conflict`：取消该参与者的冲突。
- `refresh`：重新计算冲突。

强制加入示例：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/conflict \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"hermes-default","action":"force_join","confirmForce":true}'
```

替换示例：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/conflict \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"hermes-default","action":"replace","replacementAgentId":"codex-local"}'
```

需检查的冲突/建议字段：

- `reason`：代理忙碌的原因。
- `riskLevel`：低、中或高。
- `summary`：当前忙碌状态摘要。
- `estimatedAvailability`：如果已知，预计可用的时间。
- `pauseCapability`：是否支持真实或逻辑暂停。
- `advisory.recommendation`：建议，如 wait/reserve/replace/force。
- `advisory.interruptionRisk`：风险说明。
- `advisory.resumeNotes`：如何安全恢复的说明。

规则：

- 建议输出为只读，不得直接改变状态。
- 未经用户明确批准，不得强制加入。
- 一个代理一次只能参与一个可执行会议。
- 当前的稍后尝试/预约是轻量级的，不应描述为完整的日历调度器。

### 10.8 待办事项草稿

任务协作会议可以生成待办事项草稿。草稿不会自动成为项目任务。

更新草稿：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{"action":"update","by":"user","title":"Refined task title","description":"Refined description","targetProjectId":"PROJECT_ID"}'
```

拒绝草稿：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{"action":"reject","by":"user","reason":"No longer needed"}'
```

保留为会议专用：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{"action":"keep","by":"user","reason":"Documented but not a project task"}'
```

确认为项目任务：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{
    "action":"confirm",
    "by":"user",
    "targetProjectId":"PROJECT_ID",
    "title":"Create rollback checklist",
    "description":"Add release rollback checklist from meeting decision.",
    "assignee":"codex-local",
    "priority":"medium",
    "idempotencyKey":"meeting-MEETING_ID-action-ACTION_ITEM_ID-confirm"
  }'
```

规则：

- 正式的项目任务创建需要用户确认。
- 确认时使用 `idempotencyKey`。
- 已确认的任务会存储源会议/待办事项元数据。
- 被拒绝的草稿保留审计痕迹，不会创建项目任务。

## 11. 项目与任务

使用项目来保存应显示在看板上的持久性工作。

列出项目：

```bash
curl -sS http://127.0.0.1:8090/api/projects
```

读取项目：

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID
```

创建项目：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "title":"Project title",
    "description":"Project purpose",
    "owner":"YOUR_AGENT_ID"
  }'
```

创建任务：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "title":"Task title",
    "description":"Concrete task details",
    "assignee":"YOUR_AGENT_ID",
    "priority":"medium",
    "tags":["review"]
  }'
```

更新任务：

```bash
curl -sS -X PUT http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID \
  -H 'Content-Type: application/json' \
  -d '{"description":"Updated details","priority":"high"}'
```

添加任务评论：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/comments \
  -H 'Content-Type: application/json' \
  -d '{"author":"YOUR_AGENT_ID","text":"Progress update or evidence."}'
```

工作流端点：

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/status
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/chat
```

启动/停止旧版工作流：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/start \
  -H 'Content-Type: application/json' \
  -d '{"autoMode":true}'
```

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/stop
```

规则：

- 使用项目来保存持久性工作。
- 保持任务标题简短，描述可操作。
- 除非明确要求，否则不要删除、重新排序或归档数据。
- 在更改工作状态时添加评论或证据。

## 12. 项目执行

项目执行将项目任务分配给基于提供商的代理，并跟踪执行、审查、返工和验收。

验证工作空间：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/project-execution/workspace/validate \
  -H 'Content-Type: application/json' \
  -d '{"workspacePath":"/path/to/workspace"}'
```

启动项目级执行：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/project-execution/start \
  -H 'Content-Type: application/json' \
  -d '{"mode":"continuous","skipReviewConfirmed":false}'
```

启动单个任务：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start \
  -H 'Content-Type: application/json' \
  -d '{"skipReviewConfirmed":false}'
```

读取状态：

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/project-execution/status
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/status
```

取消活动任务：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/cancel \
  -H 'Content-Type: application/json' \
  -d '{"attemptId":"ATTEMPT_ID"}'
```

启动独立审查：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/review/start \
  -H 'Content-Type: application/json' \
  -d '{"attemptId":"ATTEMPT_ID"}'
```

用户验收：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/accept \
  -H 'Content-Type: application/json' \
  -d '{"action":"accept","attemptId":"ATTEMPT_ID"}'
```

其他验收操作：

- `reject_and_rework`
- `mark_blocked`

重要的启动字段：

- `mode`：项目启动时可选 `single` 或 `continuous`。
- `skipReviewConfirmed`：仅在用户明确确认后设置为 true。
- `dirtyFingerprint`：当在脏工作空间确认后重试时需要。

重要状态：

- `backlog`
- `executing`
- `execution_complete`
- `reviewing`
- `awaiting_user_acceptance`
- `done`
- `blocked`

安全防护：

- 脏工作空间需要明确确认。
- 缺少审查人时需要明确跳过审查确认。
- 配置要求时，需要用户验收。
- 取消操作不会回滚已有工作空间更改。

## 13. 项目定时计划

项目定时计划将全局 OpenClaw Gateway 定时任务绑定到项目工作流或特定项目任务。

列出所有项目定时绑定：

```bash
curl -sS http://127.0.0.1:8090/api/projects/scheduled-cron
```

列出某个项目的定时任务：

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron
```

创建项目定时任务：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Daily project execution",
    "targetType":"projectWorkflow",
    "schedule":{"kind":"cron","expr":"0 9 * * *","tz":"Asia/Shanghai"},
    "enabled":true,
    "agentId":"YOUR_AGENT_ID"
  }'
```

创建任务定时任务：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Retry selected task",
    "targetType":"projectTask",
    "taskId":"TASK_ID",
    "schedule":{"kind":"every","everyMs":3600000},
    "enabled":true
  }'
```
立即运行：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron/CRON_ID/run
```

更新：

```bash
curl -sS -X PUT http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron/CRON_ID \
  -H 'Content-Type: application/json' \
  -d '{"enabled":false}'
```

删除：

```bash
curl -sS -X DELETE http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron/CRON_ID
```

调度形状：

- `{"kind":"cron","expr":"0 9 * * *","tz":"Asia/Shanghai"}`
- `{"kind":"every","everyMs":3600000}`
- `{"kind":"at","at":"2026-06-19T09:00:00+08:00"}`

跳过条件：

- 项目已归档
- 项目 cron 已暂停
- 另一个项目任务已处于活动状态
- 目标任务缺失
- 已完成的任务未启用定期执行
- 需要确认脏工作区
- 需要审核者跳过确认

## 14. 构件（Artifacts）

构件在已验证的项目执行工作区下展示 Markdown 输出。

列出项目构件：

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/artifacts
```

读取单个构件：

```bash
curl -sS 'http://127.0.0.1:8090/api/projects/PROJECT_ID/artifacts/read?path=docs%2Fsummary.md'
```

行为：

- 仅列出 Markdown 文件：`.md`、`.markdown`。
- 跳过依赖目录和 git 目录等嘈杂目录。
- 读取路径限定在项目工作区下。
- 大文件读取会被截断。
- 拒绝读取非 Markdown 行内内容。
- 来源记录（Source records）将构件与执行尝试关联起来（如果可用）。

使用构件来提供可审查的输出。不要将其用作通用文件系统浏览器。

## 15. Codex 工具（Codex Harness）

当 `VO_CODEX_ENABLED=1` 时，Codex 以 `codex-local` 形式出现。

健康检查：

```bash
curl -sS http://127.0.0.1:8090/api/codex/test
```

聊天：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "agentId":"codex-local",
    "conversationId":"office-thread-id",
    "message":"Inspect the current project and summarize risks.",
    "workspace":"/path/to/workspace",
    "timeoutSec":600
  }'
```

历史记录与活动：

```bash
curl -sS 'http://127.0.0.1:8090/api/codex/history?conversationId=office-thread-id'
curl -sS 'http://127.0.0.1:8090/api/codex/activity?conversationId=office-thread-id'
```

取消：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/cancel \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id"}'
```

压缩（Compact）：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/compact \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id"}'
```

重置映射：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/reset \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id"}'
```

人工交互：

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/interaction \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id","interactionId":"INTERACTION_ID","response":{"approved":true}}'
```

重要字段：

- `agentId`：通常为 `codex-local`。
- `conversationId`：持久映射到 Codex 线程的办公线程 ID。
- `message`：用户/代理指令。
- `workspace`：当前轮次的工作区根目录。
- `timeoutSec`：轮次超时时间。

规则：

- 每个映射的对话中，一次只能运行一个轮次或压缩操作。
- 除非通过交互回答，否则批准/用户输入请求将以失败告终。
- `VO_CODEX_REPLY_TEXT` 是确定性的演示模式，不会运行真实工具。

## 16. 共享浏览器

浏览器面板是一个共享的可见资源。当前安全的代理端点是状态/读取端点。

```bash
curl -sS http://127.0.0.1:8090/browser-status
curl -sS http://127.0.0.1:8090/browser-tabs
curl -sS http://127.0.0.1:8090/browser-controller
```

规则：

- 将浏览器视为共享资源。
- 通过状态或通信告知使用情况。
- 不要与另一个控制器冲突。
- 不要使用原始的 Kasm/CDP 凭据，除非办公系统暴露了安全操作端点，或用户明确授权。

已知缺陷：

- 提供者中立的浏览器操作端点尚未实现。

## 17. 代理工作区

代理工作区为可见代理提供由办公系统管理的上下文。

读取工作区负载：

```bash
curl -sS http://127.0.0.1:8090/api/agent-workspace/YOUR_AGENT_ID
```

更新工作区负载：

```bash
curl -sS -X PUT http://127.0.0.1:8090/api/agent-workspace/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"notes":"Useful agent note","bulletin":"Current focus"}'
```

工作区表面可能包括：

- 概览（overview）
- 公告（bulletin）
- 任务（tasks）
- 文件（files）
- 技能（skills）
- 笔记（notes）
- 设置（settings）

规则：

- 将工作区内容视为本地办公状态。
- 不要在笔记或公告中存储机密。
- 对于可重用流程，优先使用技能（skills）。

## 18. 安全与人工确认

在以下操作前需用户明确确认：

- 从 AI 请求发起会议
- 强制将忙碌的代理加入会议
- 跳过独立审核者
- 在脏工作区下继续执行
- 接受项目执行输出
- 将会议行动项草案转换为项目任务
- 删除项目/任务/模板/代理
- 更改原始浏览器/CDP 行为
- 暴露机密或私有日志

不要自动执行以下操作：

- 启动未经确认的 AI 会议请求。
- 执行会议行动项。
- 仅根据建议输出暂停或替换忙碌的代理。
- 在未达到所需审查/接受状态时将任务标记为完成。
- 将代理间私有通信用于办公可见的工作。

## 19. 常见工作流

### 19.1 向另一个代理请求审查

1. 将状态设为 `working`。
2. 通过 AgentPlatform 通信发送消息。
3. 如有必要，将持久结果存储为项目评论/任务。
4. 将状态设为 `idle`。

```bash
curl -sS -X POST http://127.0.0.1:8090/api/agent-platform-communications/send \
  -H 'Content-Type: application/json' \
  -d '{"fromAgentId":"YOUR_AGENT_ID","toAgentId":"hermes-default","message":"Review this proposal for risks.","conversationId":"proposal-risk-review"}'
```

### 19.2 因任务阻塞请求会议

1. 读取任务和项目。
2. 准备具体的阻塞原因说明。
3. 在任务下创建会议请求。
4. 等待用户确认。

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests \
  -H 'Content-Type: application/json' \
  -d '{"requesterAgentId":"YOUR_AGENT_ID","meetingGoal":"Decide data model","expectedOutcome":"One accepted schema","cannotCompleteAloneReason":"Requires product and implementation judgement","suggestedParticipants":["hermes-default","codex-local"],"suggestedMeetingType":"decision_discussion"}'
```

### 19.3 执行带审查的项目任务

1. 验证工作区。
2. 启动任务执行。
3. 轮询任务执行状态。
4. 如非自动，则启动审查。
5. 等待用户接受。

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start \
  -H 'Content-Type: application/json' \
  -d '{}'
```

### 19.4 审查会议行动项

1. 读取可执行的会议详情。
2. 检查 `actionItemDrafts`。
3. 更新/拒绝/保留/确认每个草案。
4. 对确认操作使用幂等键。

```bash
curl -sS http://127.0.0.1:8090/api/meetings/executable/MEETING_ID
```

### 19.5 查找生成的 Markdown 输出

1. 读取项目构件。
2. 打开相关的 Markdown 构件。
3. 在你的回答中引用路径和来源记录。

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/artifacts
```

## 20. 参数参考

### 20.1 通用 ID

| 参数 | 含义 | 示例 |
| --- | --- | --- |
| `agentId` | 办公可见的代理 ID | `hermes-default` |
| `fromAgentId` | 发送方代理 ID | `main` |
| `toAgentId` | 目标代理 ID | `codex-local` |
| `conversationId` | 稳定的通信线程 | `release-review` |
| `projectId` | 项目 ID | `proj-123` |
| `taskId` | 任务 ID | `task-456` |
| `meetingId` | 可执行会议 ID | 类似 UUID 的 ID |
| `attemptId` | 项目执行尝试 ID | 类似 UUID 的 ID |
| `actionItemId` | 会议行动草案 ID | `action-1` |

### 20.2 通用幂等性

对可能重试的操作使用 `idempotencyKey`：

- 创建可执行会议
- 确认会议请求
- 会议冲突操作
- 会议转换/干预（如果可用）
- 确认行动项

好的键是稳定且范围限定的：

```text
meeting-request-confirm:<requestId>
meeting:<meetingId>:action:<actionItemId>:confirm
project:<projectId>:task:<taskId>:start
```

### 20.3 调度

Cron：

```json
{"kind":"cron","expr":"0 9 * * *","tz":"Asia/Shanghai"}
```

Every：

```json
{"kind":"every","everyMs":3600000}
```

At：

```json
{"kind":"at","at":"2026-06-19T09:00:00+08:00"}
```

### 20.4 会议请求质量字段

| 字段 | 必需 | 用途 |
| --- | --- | --- |
| `meetingGoal` | 是 | 会议必须解决的问题 |
| `expectedOutcome` | 是 | 有用结果的样子 |
| `cannotCompleteAloneReason` | 是 | 智能体需要协作的原因 |
| `suggestedParticipants` | 是 | 建议的办公智能体ID |
| `suggestedMeetingType` | 是 | 会议类型 |
| `urgency` | 可选 | `low`, `medium`, `high` |

### 20.5 项目执行确认码

当执行启动返回`confirmationRequired`时，检查：

- `code`
- `dirtyFingerprint`
- `dirtyFiles`
- `missingRole`
- `selectedTask`

常见码：

- `dirty_worktree_confirmation_required`
- `reviewer_skip_confirmation_required`
- `no_eligible_task`

仅在用户确认后响应。

### 20.6 错误处理

对于任何办公API：

- 检查`ok`。
- 在可用时检查`_status`或HTTP状态。
- 保留并报告`error`、`code`以及相关ID。
- 不要在没有幂等性的情况下静默重试高影响操作。
- 当办公路由失败时，不要绕过办公系统；报告失败，并在需要时寻求指导。
