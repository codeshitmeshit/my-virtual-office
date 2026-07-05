---
name: vo-meeting-execution
description: Virtual Office 中任意 CLI 或 agent 需要操作用户已确认的 executable meeting 时使用；覆盖会议详情、事件、run/transition、用户干预、议程调整、定向提问、仲裁、主持人接管、冲突处理和 action item 草稿，不用于提交或确认 AI 会议申请。
---

# Virtual Office 会议执行

## 目标

操作已经存在、且用户已确认或用户主动创建的 executable meeting。处理运行、暂停/恢复、事件跟踪、干预、冲突和 action item 草稿。AI 会议申请仍由 本地 `/skills/vo-operating-guidelines/SKILL.md` 和 `references/meeting-requests.md` 处理；本 skill 不自行 confirm/reject meeting request。

## 地址和身份

```bash
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f /home/wo/code/my-virtual-office/.env ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' /home/wo/code/my-virtual-office/.env)"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
curl -sS "$VO_BASE_URL/api/agents"
```

写操作中的 `by` 必须是真实用户或当前 VO agent ID。不要冒用 moderator 或其他参与者。

## 读取会议

```bash
curl -sS "$VO_BASE_URL/api/meetings/active"
curl -sS "$VO_BASE_URL/api/meetings/history"
curl -sS "$VO_BASE_URL/api/meetings/executable/MEETING_ID"
curl -sS "$VO_BASE_URL/api/meetings/executable/MEETING_ID/events?afterSeq=0"
```

关注 `stage`、`round`、`participants`、`participantState`、`events`、`result`、`conflicts`、`actionItemDrafts` 和版本字段。对特定快照动作优先带 `expectedVersion`。

## 推进和转场

运行或继续：

```bash
curl -sS -X POST "$VO_BASE_URL/api/meetings/executable/MEETING_ID/run" \
  -H 'Content-Type: application/json' \
  -d '{"by":"AGENT_ID"}'
```

转场：

```bash
curl -sS -X POST "$VO_BASE_URL/api/meetings/executable/MEETING_ID/transition" \
  -H 'Content-Type: application/json' \
  -d '{"action":"pause","by":"AGENT_ID","reason":"Waiting for user input","expectedVersion":3}'
```

常见 action 概念：`pause`、`resume`、`cancel`、`complete`、`fail`。使用本地服务实际接受的 action；失败时报告真实错误。

## 干预和决策

```bash
curl -sS -X POST "$VO_BASE_URL/api/meetings/executable/MEETING_ID/intervention" \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","kind":"user_message","text":"Add this user-approved context."}'
```

其他当前路由：

- `POST /api/meetings/executable/<meetingId>/agenda-change`
- `POST /api/meetings/executable/<meetingId>/targeted-question`
- `POST /api/meetings/executable/<meetingId>/arbitration`
- `POST /api/meetings/executable/<meetingId>/moderator-takeover`

用户上下文、仲裁和主持人接管属于用户控制面；没有明确用户授权时不要代替用户决策。

## 冲突处理

```bash
curl -sS -X POST "$VO_BASE_URL/api/meetings/executable/MEETING_ID/conflict" \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"AGENT_ID","action":"wait"}'
```

支持的 action 概念包括 `wait`、`reserve`、`replace`、`force_join`、`cancel_conflict`、`refresh`。`force_join` 必须有明确二次确认；advisory 只读，不会自动改变状态。

## Action item 草稿

```bash
curl -sS -X POST "$VO_BASE_URL/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID" \
  -H 'Content-Type: application/json' \
  -d '{"action":"confirm","by":"user","targetProjectId":"PROJECT_ID","title":"Task title","idempotencyKey":"meeting-MEETING_ID-action-ACTION_ITEM_ID-confirm"}'
```

支持 `update`、`reject`、`keep`、`confirm`。草稿不会自动变成项目任务；`confirm` 必须是用户控制动作，并使用 `idempotencyKey`。

## 安全规则

- 只操作已存在的 executable meeting；不要用本 skill 提交或确认 AI meeting request。
- 不自行选择最终会议上下文、仲裁结论、force join 或 action item 确认。
- 一个 agent 同时只能参加一场 executable meeting；遇到 conflict 先读取 advisory。
- 每次写操作后重新读取 detail/events 验证。
- 需要普通 agent 单轮沟通时使用通信 skill，不要开会。

## 质量检查

- 已确认 meetingId 存在且是 executable meeting。
- 已确认 `by` 身份、participants、stage、version 和 conflict 状态。
- 用户控制面动作已有明确授权。
- 未把 pending request 当成 active meeting。
- 已验证 run/transition/action item 后的会议状态。
