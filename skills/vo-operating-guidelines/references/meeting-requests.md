# AI 会议申请

当 `vo-operating-guidelines` 判断需要正式 AI 会议时，读取本文档并按这里的流程操作。本文只覆盖会议申请、查询和用户控制面，不替代普通 agent 通信 skill。

## 1. 识别可参会 AI

申请会议前查询可用 agent。优先使用当前运行环境或 `start.sh` 启动配置中的端口。`start.sh` 会加载 `.env` 并导出 `VO_PORT`，服务端按这个端口启动；不要只探测 `8090`。

```bash
vo_project_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f "$vo_project_root/.env" ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_project_root/.env")"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
```

基础列表：

```bash
curl -sS "$VO_BASE_URL/api/agents"
```

会议参与者优先使用 `/agents-list` 返回的 `key`，因为前端当前用该 key 作为选择值：

```bash
curl -sS "$VO_BASE_URL/agents-list"
```

重点查看：

```json
{
  "agents": [
    {
      "key": "main",
      "agentId": "main",
      "providerKind": "openclaw",
      "name": "gg"
    }
  ]
}
```

将 `key` 用作 `suggestedParticipants`。不要猜测或补全不存在的参会者 ID。

## 2. 自动批准风险检查

提交会议申请前，必须检查目标项目的会议自动批准策略。若当前服务端可能将 meeting request 自动 confirm 或 auto-run，则必须先告知用户，并等待用户确认是否仍要提交。

AI 不得在用户未确认的情况下触发可能自动开始的会议。如果不确定服务端是否会自动批准，则不要提交会议申请，只输出拟申请内容和风险说明。

建议先读取目标项目和已有会议请求：

```bash
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID"
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests"
```

如果项目或任务配置中存在自动批准、自动运行、会议阻塞自动恢复、或类似策略字段，先向用户展示会议草案、触发原因、参会者、预期产出、可能自动开始的风险，再等待明确确认。

## 3. 提交会议申请

Phase 4 当前只支持项目任务来源的 AI 会议申请：

```text
POST /api/projects/{projectId}/tasks/{taskId}/meeting-requests
```

示例：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests" \
  -H 'Content-Type: application/json' \
  -d '{
    "requestingAgentId": "main",
    "topic": "Architecture decision meeting",
    "purpose": "Choose the implementation direction",
    "goal": "Resolve the current blocker",
    "expectedOutcome": "A concrete decision and next steps",
    "reason": "I cannot safely decide this alone because another AI should review the tradeoffs",
    "suggestedParticipants": ["main", "hermes-default"],
    "suggestedModerator": "main",
    "meetingType": "discussion",
    "maxRounds": 2,
    "idempotencyKey": "PROJECT_ID:TASK_ID:architecture-blocker-v1"
  }'
```

关键字段：

- `requestingAgentId`：发起申请的 AI。
- `goal`：为什么要开会，要解决什么。
- `expectedOutcome`：会议结束应产出什么。
- `reason` 或 `cannotCompleteAloneReason`：为什么自己不能单独完成。
- `suggestedParticipants`：建议参会 AI，优先使用 `/agents-list` 的 `key`。
- `idempotencyKey`：强烈建议填写，避免重复提交。

`meetingType` 可选：

- `information`
- `discussion`
- `task`

申请成功后停止等待用户处理，不要假设会议已经开始。

## 4. 查询会议申请

查询全部申请：

```bash
curl -sS "$VO_BASE_URL/api/meetings/requests"
```

只查 pending：

```bash
curl -sS "$VO_BASE_URL/api/meetings/requests?status=pending"
```

查某个任务的申请：

```bash
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests"
```

## 5. 用户控制面

AI 只能申请和查询会议请求，不要自行调用确认或拒绝接口。

用户确认会议时可能选择：

```json
{
  "moderator": "main",
  "selectedContextIds": ["task:TASK_ID"],
  "supplementalContext": "Extra user-approved context"
}
```

自动推荐的上下文默认不会进入会议。只有用户确认时选择的 `selectedContextIds` 和补充的 `supplementalContext` 才会进入会议。

用户可以拒绝会议：

```text
POST /api/meetings/requests/{requestId}/reject
```

```json
{
  "reason": "This can be solved without a meeting"
}
```

拒绝原因会写回来源任务评论，AI 后续可以在任务上下文里看到。不要绕过用户决定继续推进会议。

## 6. 质量检查

提交或查询会议前确认：

- 已确认当前可访问 Virtual Office。
- 当前场景确实需要正式 AI 会议，而不是普通 agent 沟通。
- 项目任务来源已确认，且有有效 `projectId` 和 `taskId`。
- 已检查目标项目会议自动批准风险；不确定是否自动批准时，已先输出拟申请内容和风险说明并等待用户确认。
- `suggestedParticipants` 优先来自 `/agents-list` 的 `key`。
- 申请包含 `goal`、`expectedOutcome`、`reason` 和 `idempotencyKey`。
- 没有自行 confirm/reject 会议，也没有替用户选择最终会议上下文。
