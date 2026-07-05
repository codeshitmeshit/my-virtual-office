---
name: vo-codex-communication
description: 任意 CLI 或 agent 需要联系 Virtual Office 中 providerKind=codex 的 Codex 协作者时使用；主动探测 Virtual Office，通过其通信 API 向 codex-local 提问、分配任务或复用 conversationId 延续会话，并处理 completed、busy、timeout、失败和人工介入状态。在 OpenClaw 中不得对 Codex 使用 sessions_send。
---

# Virtual Office Codex 通信

## 目标

通过 Virtual Office 与 Codex 协作者 `codex-local` 通信，供 OpenClaw、Hermes、Claude Code 或其他能够访问 Virtual Office 的调用方复用，并确保 Codex 目标不会被误当作 OpenClaw 原生 agent 或 session。

最关键的路由规则：目标属于 `providerKind=codex` 时，必须走 Virtual Office API；只有目标属于 OpenClaw 原生 agent 时，才考虑 `sessions_send`。

如果任务是在判断是否处于 VO、选择哪个 VO skill、或决定普通 Codex 沟通是否应升级为正式 AI 会议，先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。本技能只处理已确定要联系 `providerKind=codex` 目标的普通通信。

## 核心约束

- 不要对 `codex-local` 调用 `sessions_send`。
- 不要用 `agentId=codex` 搜索 OpenClaw session。
- 不要绕过 Virtual Office 启动私人 Codex CLI 会话。
- Virtual Office 或 `codex-local` 不可用时，报告错误并停止；不要自动切换其他 Codex 通道。
- 每次默认发送边界清晰的任务。复杂任务可以发送，但应提示其更容易超时，不要仅因任务较复杂而拒绝发送。
- 不要用本技能提交或确认 AI 会议；正式会议申请、多方同步决策或用户确认会议上下文的场景先回到 本地 `/skills/vo-operating-guidelines/SKILL.md`。
- 不要要求 Codex 返回密钥、认证信息或越过工作区权限。

## 通信工作流

### 1. 确定 Virtual Office 地址

需要联系 Codex 时，主动探测 Virtual Office，不要仅凭历史信息认定它可用。

优先使用当前运行环境或 `start.sh` 启动配置中的端口。`start.sh` 会加载 `.env` 并导出 `VO_PORT`，服务端按这个端口启动；不要只探测 `8090`。如果当前 agent 位于容器或其他机器，使用其能够访问的 Virtual Office 地址，不要假设 `127.0.0.1` 指向宿主机。

```bash
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f /home/wo/code/my-virtual-office/.env ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' /home/wo/code/my-virtual-office/.env)"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
```

### 2. 检查服务和 Codex

先确认 Codex 集成健康。当前 VO 同时支持 GET 和 POST，这里使用无副作用的 GET 示例：

```bash
curl -sS "${VO_BASE_URL:-http://127.0.0.1:8090}/api/codex/test"
```

要求响应包含 `"ok": true`。Virtual Office 还应满足：

- `_VO_INT=1`
- `VO_CODEX_ENABLED=1`
- Codex CLI 已登录

再查询 agent：

```bash
curl -sS "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agents"
```

确认结果中存在：

```json
{
  "id": "codex-local",
  "providerKind": "codex"
}
```

任一检查失败时，向用户报告实际错误并停止，不要假装已发送任务。

### 3. 选择 Conversation ID

需要延续既有上下文时，必须复用相同的 `conversationId`，例如：

```text
main__codex__project-review
```

不同任务或需要隔离上下文时，使用稳定且能表达业务主题的新 ID，例如：

```text
main__codex__bug-123
main__codex__release-review
```

不要为同一业务会话中的每条消息随机创建 ID。

### 4. 发送消息

`fromAgentId` 必须使用调用方在 Virtual Office 中的实际 agent ID。OpenClaw 默认使用 `main` 作为发送方：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "main",
    "toAgentId": "codex-local",
    "conversationId": "main__codex__general",
    "message": "今天星期几？请直接回答。",
    "metadata": {
      "topic": "general-question"
    }
  }'
```

Hermes 通常使用 `hermes-default` 作为发送方：

```json
{
  "fromAgentId": "hermes-default",
  "toAgentId": "codex-local"
}
```

Claude Code 通常使用 `claude-code-local` 作为发送方：

```json
{
  "fromAgentId": "claude-code-local",
  "toAgentId": "codex-local"
}
```

Claude Code 或其他调用方不要冒用 `main` 或 `hermes-default`；先从 Virtual Office 的 agent 清单或当前运行上下文确认自己的 agent ID。无法确认发送方身份时，报告缺失信息并停止发送。

发送代码检查任务时，消息应说明范围和预期结果，例如：

```text
检查 app/server.py 中 Codex 路由是否存在明显错误，只报告高风险问题。
```

### 5. 解析结果

成功响应通常包含：

```json
{
  "ok": true,
  "conversationId": "main__codex__general",
  "reply": "今天是星期二。",
  "status": "completed",
  "modifiedFiles": [],
  "needsHumanIntervention": false
}
```

重点处理以下字段：

- `reply`：Codex 的最终回复。
- `status`：任务状态，例如 `completed`、`busy` 或 `timeout`。
- `modifiedFiles`：Codex 修改的文件。
- `needsHumanIntervention`：是否必须由用户介入。

Codex 的回复和文件修改结果会记录到 Virtual Office history。

## 状态处理

- `ok=false`：报告响应中的错误并停止，不要宣称任务成功。
- `status=completed`：向用户返回 `reply`，并在有内容时说明 `modifiedFiles`。
- `status=busy`：停止本次发送并报告 Codex 忙碌；不要立即重试或并发发送。
- `status=timeout`：报告结果未知；不要推定任务成功或失败，也不要立即重复提交相同任务。
- `needsHumanIntervention=true`：停止自动执行并通知用户需要介入。
- 未识别状态：原样报告关键响应字段，不自行编造结论。

## 质量检查

发送前确认：

- 已主动探测当前可访问的 Virtual Office。
- `/api/codex/test` 返回 `ok: true`。
- `/api/agents` 中存在 `id=codex-local` 且 `providerKind=codex`。
- 没有使用 `sessions_send`、OpenClaw session 搜索或私人 Codex CLI。
- 延续任务复用了原 `conversationId`，隔离任务使用了新的稳定 ID。
- 消息包含明确目标、必要上下文、范围和期望输出。

收到响应后确认：

- 已检查 `ok`、`status`、`reply`、`modifiedFiles` 和 `needsHumanIntervention`。
- 没有把 `busy` 或 `timeout` 当作成功。
- 没有在结果未知时立即重复提交可能仍在执行的任务。
