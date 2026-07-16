---
name: vo-agent-communication
description: 任意 CLI 或 agent 需要通过 Virtual Office 联系 OpenClaw、Hermes、Claude Code 或其他非 Codex 办公室 Agent 时使用；查询实际 Agent ID，通过统一通信 API 提问、委派任务、转交信息或复用 conversationId 延续跨平台会话，并返回可在 history 中追踪的真实响应。目标为 codex-local 或 providerKind=codex 时改用 vo-codex-communication。
---

# Virtual Office Agent 通信

## 目标

通过 Virtual Office 与非 Codex 办公室 Agent 通信，包括 OpenClaw、Hermes、Claude Code 等 provider，确保请求、回复和状态均可在 Virtual Office history 中追踪。

目标为 `codex-local` 或 `providerKind=codex` 时，不使用本技能，改用 本地 `/skills/vo-codex-communication/SKILL.md`。

如果任务是在判断是否处于 VO、选择哪个 VO skill、或决定普通沟通是否应升级为正式 AI 会议，先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。本技能只处理已确定要进行的普通非 Codex agent 通信。

## 核心规则

与办公室 Agent 通信时，必须调用：

```text
POST /api/agent-platform-communications/send
```

不要：

- 直接调用 OpenClaw 私有 session。
- 使用 `sessions_list`、`sessions_send`、`openclaw agents` 或等价的 provider-private 发现/消息路径完成办公室 Agent 通信。
- 直接执行 Hermes、Claude Code CLI 或其他目标平台的私人 CLI。
- 绕过 Virtual Office 建立不可见通信。
- 把目标 Agent 当成本地 Codex subagent。
- 猜测、补全或复用未确认的 Agent ID。
- 传输凭据、密钥或敏感配置。

## 通信工作流

### 1. 确定 Virtual Office 地址

优先使用当前运行环境或 `start.sh` 启动配置中的端口。`start.sh` 会加载 `.env` 并导出 `VO_PORT`，服务端按这个端口启动；不要只探测 `8090`。

```bash
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f /home/wo/code/my-virtual-office/.env ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' /home/wo/code/my-virtual-office/.env)"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
```

如果调用方位于容器或远程环境，使用其能够访问的 Virtual Office 地址，不要假设 `127.0.0.1` 指向宿主机。

### 2. 查询并确认 Agent

发送消息前查询 Agent 列表：

```bash
curl -sS "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agents"
```

常见 ID 包括：

- `main`：OpenClaw 默认 Agent。
- `hermes-default`：Hermes 默认 Agent。
- `claude-code-local`：Claude Code 本地 Agent。
- `codex-local`：Codex；遇到此目标必须改用 本地 `/skills/vo-codex-communication/SKILL.md`。

始终以 `/api/agents` 当前返回的实际 ID 和 provider 信息为准，不要把常见 ID 当作存在性证明。

同时确认 `fromAgentId` 是调用方在 Virtual Office 中的实际身份。不要冒用其他 Agent 的 ID。

按以下规则处理目标：

- 唯一匹配：使用返回的实际 ID。
- 多个可能目标：停止发送，列出候选项并要求用户明确选择。
- 目标不存在：报告不可用并停止，不自动转交给 `main` 或其他替代 Agent。
- 目标为 `codex-local` 或 `providerKind=codex`：停止本流程并改用 本地 `/skills/vo-codex-communication/SKILL.md`。
- 无法确认发送方身份：报告缺失信息并停止。

### 3. 选择 Conversation ID

需要延续上下文时，复用相同的 `conversationId`：

```text
codex__main__project-alpha
```

需要隔离任务时，创建新的稳定 ID：

```text
codex__main__bug-123
codex__main__release-review
```

ID 应表达发送方、接收方和业务主题。不要在同一任务或业务会话中频繁更换 ID。

### 4. 发送消息

向 OpenClaw `main` 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "codex-local",
    "toAgentId": "main",
    "conversationId": "codex__main__general",
    "message": "请检查当前 OpenClaw 服务状态，并简要返回结果。",
    "metadata": {
      "topic": "service-status"
    }
  }'
```

向 Hermes 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "codex-local",
    "toAgentId": "hermes-default",
    "conversationId": "codex__hermes__review",
    "message": "请从产品角度评审这个方案，并指出两个主要风险。"
  }'
```

向 Claude Code 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "codex-local",
    "toAgentId": "claude-code-local",
    "conversationId": "codex__claude-code__review",
    "message": "请从实现角度评审这个改动，并只返回高风险问题。"
  }'
```

示例中的 `fromAgentId` 仅适用于实际发送方为 `codex-local` 的场景。其他调用方必须替换为其经确认的 Virtual Office Agent ID。

消息应包含明确目标、必要上下文、任务边界和期望输出。默认委派短任务；复杂任务可以发送，但应提示超时和协调风险，不要将本技能用于长期项目编排。

### 5. 处理响应

成功响应通常包含：

```json
{
  "ok": true,
  "conversationId": "codex__main__general",
  "reply": "服务当前运行正常。",
  "status": "completed",
  "modifiedFiles": [],
  "needsHumanIntervention": false
}
```

按以下规则处理：

- `ok=false`：明确报告通信失败和实际错误，不宣称任务成功。
- `status=completed` 且 `reply` 非空：返回目标 Agent 的真实回复。
- `status=busy`：报告忙碌并停止，不自动重试或并发发送。
- `status=timeout`：报告结果未知，不推定成功或失败，不自动重发。
- `reply` 为空：报告未获得有效回复，不把空回复解释为成功。
- `needsHumanIntervention=true`：停止自动执行并通知用户介入。
- 未识别状态：原样报告关键响应字段，不伪造目标 Agent 的回复。

### 6. 按需查询历史

需要确认既有通信或结果时，按 `conversationId` 查询：

```bash
curl -sS \
  "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/history?conversationId=codex__main__general"
```

不要使用 history 中的旧 Agent ID 替代当前 `/api/agents` 检查。

## 任务边界

适合：

- 提问和获取意见。
- 短任务委派。
- 代码或产品评审请求。
- 状态查询和信息转交。
- 单轮协作或复用稳定会话的少量后续沟通。

不适合：

- 高频并发对话。
- 无限自主 Agent 循环。
- 长期项目编排。
- 正式 AI 会议申请、多方同步决策或需要用户确认会议上下文的场景；这类场景先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。
- 绕过人工授权的操作。
- 传输凭据或敏感配置。

## 质量检查

发送前确认：

- 已使用当前可访问的 Virtual Office 地址。
- 已查询 `/api/agents` 并确认发送方和唯一目标的实际 ID。
- 目标不是 `codex-local`，provider 也不是 `codex`。
- 没有使用目标平台的私有 session、CLI 或本地 subagent 绕过 Virtual Office。
- 延续任务复用了原 `conversationId`，隔离任务使用了新的稳定 ID。
- 消息范围清晰，且不包含凭据或敏感配置。

收到响应后确认：

- 已检查 `ok`、`status`、`reply` 和 `needsHumanIntervention`。
- 返回的是目标 Agent 的真实响应，没有自行补写或伪造。
- `busy`、`timeout` 和空回复均未被解释为成功。
- 通信使用的 `conversationId` 可用于查询 Virtual Office history。
