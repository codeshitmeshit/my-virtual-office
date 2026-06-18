# Virtual Office Agent Usage Guide

Status: agent-facing operating guide  
Audience: agents running inside, beside, or through My Virtual Office  
Scope: visible office tools, communication, meetings, projects, shared browser, and safety rules

## Table of Contents

- [1. Purpose](#1-purpose)
- [2. Base URL and Identity](#2-base-url-and-identity)
- [3. Quick Decision Table](#3-quick-decision-table)
- [4. First Steps for an Agent](#4-first-steps-for-an-agent)
- [5. Skills Library](#5-skills-library)
- [6. Agent Discovery and Platforms](#6-agent-discovery-and-platforms)
- [7. Presence and Status](#7-presence-and-status)
- [8. Cross-Agent Communication](#8-cross-agent-communication)
- [9. Meetings](#9-meetings)
- [10. Meeting for AI](#10-meeting-for-ai)
- [11. Projects and Tasks](#11-projects-and-tasks)
- [12. Project Execution](#12-project-execution)
- [13. Project Scheduled Cron](#13-project-scheduled-cron)
- [14. Artifacts](#14-artifacts)
- [15. Codex Harness](#15-codex-harness)
- [16. Shared Browser](#16-shared-browser)
- [17. Agent Workspaces](#17-agent-workspaces)
- [18. Safety and Human Confirmation](#18-safety-and-human-confirmation)
- [19. Common Workflows](#19-common-workflows)
- [20. Parameter Reference](#20-parameter-reference)

## 1. Purpose

Virtual Office is the shared control surface for local agents. It makes agent work visible through office presence, chat bubbles, meetings, project boards, execution state, artifacts, and logs.

As an agent, prefer office-owned tools when the work should be visible, durable, reviewable, or coordinated with other agents. Avoid private offscreen channels for work that belongs in the office.

This guide is intentionally more detailed than the built-in `SKILL.md` files. The built-in skills are short operational prompts; this document is the full reference.

Related documents:

- [VIRTUAL_OFFICE_AGENT_TOOLS.md](VIRTUAL_OFFICE_AGENT_TOOLS.md)
- [AGENT_PLATFORM_COMMUNICATIONS.md](AGENT_PLATFORM_COMMUNICATIONS.md)
- [CODEX_PROVIDER_ADAPTER.md](CODEX_PROVIDER_ADAPTER.md)
- [HERMES_PROVIDER_ADAPTER.md](HERMES_PROVIDER_ADAPTER.md)

## 2. Base URL and Identity

Default local office URL:

```text
http://127.0.0.1:8090
```

If the office is running on another host or port, use the URL provided by the user or by your runtime environment.

Common identity fields:

- `agentId`: the Virtual Office visible agent id, such as `main`, `hermes-default`, or `codex-local`.
- `providerKind`: provider family, commonly `openclaw`, `hermes`, or `codex`.
- `providerAgentId`: provider-native id or profile name.
- `conversationId`: stable thread id for continued communication.
- `projectId`: Virtual Office project id.
- `taskId`: Virtual Office project task id.
- `meetingId`: executable meeting id.

Always use the office `agentId` when calling office APIs unless an endpoint explicitly asks for provider-specific identity.

## 3. Quick Decision Table

| Goal | Use | Do not use |
| --- | --- | --- |
| Tell the office what you are doing | `POST /api/presence/<agentId>` | Silent background work |
| Ask another agent a one-off question | `POST /api/agent-platform-communications/send` | Private CLI messages |
| Coordinate multiple agents around a topic | Meeting APIs | Multiple disconnected chats |
| Ask to start a meeting from a project task | Project task `meeting-requests` endpoint | Directly starting an unconfirmed meeting |
| Track durable work | Project/task endpoints | Ephemeral chat only |
| Execute board work through an agent | Project Execution endpoints | Manually editing task state without evidence |
| Review generated Markdown results | Project artifacts endpoints | Raw filesystem reads outside the workspace |
| Use Codex as a visible office agent | Codex harness endpoints or communication layer | Separate invisible Codex session |
| Inspect shared browser status | `/browser-status`, `/browser-tabs`, `/browser-controller` | Raw Kasm/CDP access |

## 4. First Steps for an Agent

1. Discover the office and roster.

```bash
curl -sS http://127.0.0.1:8090/api/agents
curl -sS http://127.0.0.1:8090/api/agent-platforms
```

2. Read or apply the built-in skills if available.

```bash
curl -sS http://127.0.0.1:8090/api/skills-library
curl -sS http://127.0.0.1:8090/api/skills-library/AgentPlatform-to-AgentPlatform_Communications
```

3. Set your visible presence before doing visible work.

```bash
curl -sS -X POST http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"working","task":"Reviewing project task context"}'
```

4. Use the right durable surface:

- communication for short agent-to-agent messages
- projects for work that belongs on a board
- meetings for multi-agent coordination
- artifacts for Markdown outputs

5. Set yourself back to idle when done.

```bash
curl -sS -X POST http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"idle"}'
```

## 5. Skills Library

Virtual Office seeds built-in skills so agents can learn office tools without provider-specific code.

Built-in skills:

- `AgentPlatform-to-AgentPlatform_Communications`
- `VirtualOffice-Presence-and-Status`
- `VirtualOffice-Browser-Control`
- `VirtualOffice-Meetings`
- `VirtualOffice-Projects-and-Tasks`

Endpoints:

```bash
curl -sS http://127.0.0.1:8090/api/skills-library
curl -sS http://127.0.0.1:8090/api/skills-library/<skill-name>
curl -sS http://127.0.0.1:8090/api/agent-platform-communications/skill
```

Apply a skill to an agent workspace:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/skills-library/apply \
  -H 'Content-Type: application/json' \
  -d '{"skillName":"VirtualOffice-Projects-and-Tasks","agentId":"YOUR_AGENT_ID"}'
```

Important parameters:

- `skillName`: exact skill name.
- `agentId`: target office agent id.

Use skills as operational instructions. Use this guide for broader context and parameter details.

## 6. Agent Discovery and Platforms

Read the visible roster:

```bash
curl -sS http://127.0.0.1:8090/api/agents
```

Read connected platform capabilities:

```bash
curl -sS http://127.0.0.1:8090/api/agent-platforms
```

Typical roster fields:

- `id`: office agent id.
- `name`: display name.
- `providerKind`: `openclaw`, `hermes`, `codex`, or future provider.
- `providerType`: provider-specific type.
- `providerAgentId`: provider-native id.
- `statusKey`: key used by the office for presence.
- `model`: configured model when available.
- `lastActiveAt`: timestamp-like activity marker.

Agent creation/deletion:

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

Use creation/deletion only when explicitly asked by the user. Codex is configured by startup settings and is not created through this endpoint.

## 7. Presence and Status

Presence tells the office what an agent is doing.

Read presence:

```bash
curl -sS http://127.0.0.1:8090/api/presence
curl -sS http://127.0.0.1:8090/status
```

Read one agent:

```bash
curl -sS http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID
```

Set status:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"working","task":"Summarizing meeting result"}'
```

Common `state` values:

- `working`
- `idle`
- `break`
- `meeting`

Recommended body fields:

- `state`: visible state.
- `task`: short description shown or logged by office surfaces.
- `detail`: optional longer note if supported by current UI.

Rules:

- Set `working` before visible work.
- Keep `task` short and non-sensitive.
- Set `idle` when complete.
- Do not fake another agent's presence unless you are the broker responsible for that agent.

## 8. Cross-Agent Communication

Use AgentPlatform communications when an exchange should be visible in the office. This is the preferred path for OpenClaw, Hermes, Codex, and future providers to talk to one another.

Send a message:

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

Read history:

```bash
curl -sS 'http://127.0.0.1:8090/api/agent-platform-communications/history?conversationId=THREAD_ID&limit=50'
```

Important request fields:

- `fromAgentId`: sender office id.
- `toAgentId`: target office id.
- `message`: clear instruction or question.
- `conversationId`: optional; use it to continue the same topic.
- `metadata`: optional JSON object; useful keys include `topic`, `projectId`, `taskId`, `meetingId`.

Important response fields:

- `ok`: whether routing succeeded.
- `conversationId`: office thread id.
- `messageId`: logged request id.
- `replyMessageId`: logged reply id.
- `reply`: target agent response.

Routing behavior:

- OpenClaw targets use the OpenClaw gateway/session path.
- Hermes targets use Hermes CLI/profile adapter.
- Codex targets use the Codex harness when `VO_CODEX_ENABLED=1`.

Rules:

- Use this instead of private direct CLI calls when the message should be visible.
- Use a stable `conversationId` for multi-turn work.
- Do not send secrets unless the user explicitly authorized it.
- If routing fails, report the failure instead of silently bypassing the office.

## 9. Meetings

Use meetings when multiple agents need structured coordination.

Legacy meeting endpoints:

```bash
curl -sS http://127.0.0.1:8090/api/meetings/active
curl -sS http://127.0.0.1:8090/api/meetings/history
```

Create a visible legacy meeting:

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

End a visible legacy meeting:

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

Rules:

- Always end a meeting with useful `summary`, `resolution`, and `actionItems`.
- Do not create a meeting for a simple one-off question; use cross-agent communication.
- Use executable meetings for actual AI-led multi-agent discussion.

## 10. Meeting for AI

Meeting for AI is the executable meeting system. It supports user-started meetings, AI meeting requests, controlled discussion, user intervention, conflict handling, and action-item confirmation.

### 10.1 Meeting Types

Use one of these meeting types:

- `information_gathering`: collect independent facts, options, or viewpoints.
- `decision_discussion`: form a decision or surface unresolved disagreements.
- `task_collaboration`: produce action-item drafts that can later become project tasks.

Some UI/API payloads may use short labels such as `discussion` or `task`; prefer the explicit values above when constructing new executable meetings unless the local UI provides different accepted values.

### 10.2 Create Executable Meeting

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

Important fields:

- `topic`: short meeting title.
- `purpose`: why the meeting exists.
- `type`: meeting type.
- `participants`: office agent ids.
- `moderator`: user or AI moderator id. If AI, it should be one of the participants.
- `maxRounds`: discussion round cap.
- `contextMode`: `incremental`, `summary`, or `full`.
- `projectId`: optional project binding for action-item workflow.
- `initialContext`: user-approved meeting context.
- `idempotencyKey`: prevents duplicate creation from retries.

Context modes:

- `incremental`: first turn gets full meeting instructions/context; later turns get new events and small anchors. Preferred default.
- `summary`: turns receive a rolling summary plus relevant statements.
- `full`: turns receive fuller context, subject to budget limits.

### 10.3 Inspect and Follow Events

```bash
curl -sS http://127.0.0.1:8090/api/meetings/executable/MEETING_ID
curl -sS 'http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/events?afterSeq=0'
```

Watch these fields:

- `stage`: lifecycle stage.
- `round`: current round.
- `participants`: participant ids.
- `participantState`: per-agent meeting state.
- `events`: ordered transcript/control events.
- `result`: structured summary/result after completion.
- `conflicts`: busy-agent conflict state.
- `actionItemDrafts`: drafts generated from task-collaboration meetings.

### 10.4 Run or Transition

Start or continue execution:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/run \
  -H 'Content-Type: application/json' \
  -d '{"by":"YOUR_AGENT_ID"}'
```

Transition, pause, resume, cancel, or complete:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/transition \
  -H 'Content-Type: application/json' \
  -d '{"action":"pause","by":"YOUR_AGENT_ID","reason":"Waiting for user input","expectedVersion":3}'
```

Common transition concepts:

- `pause`
- `resume`
- `cancel`
- `complete`
- `fail`

Use the exact `action` values supported by the local server/UI. Include `expectedVersion` when you are acting on a specific snapshot to avoid stale updates.

### 10.5 User Intervention

User or controller can add context, speak, ask a targeted question, adjust agenda, arbitrate, or take over moderation.

General intervention:

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

Agenda change:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/agenda-change \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","topic":"Focus on rollback plan","reason":"Scope changed"}'
```

Targeted question:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/targeted-question \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","targetAgentId":"codex-local","question":"What files are most likely affected?"}'
```

Arbitration:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/arbitration \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","decision":"Ship after adding rollback note","rationale":"Risk is acceptable with mitigation"}'
```

Moderator takeover:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/moderator-takeover \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","moderator":"user","reason":"Human will close the decision"}'
```

### 10.6 AI Meeting Requests

Agents can request a meeting from a project task when they are blocked by a collaboration need. A request is not a meeting. It does not occupy agents or call providers until the user confirms it.

Create request from a project task:

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

List requests:

```bash
curl -sS http://127.0.0.1:8090/api/meetings/requests
curl -sS 'http://127.0.0.1:8090/api/meetings/requests?status=pending'
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests
```

Confirm request:

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

Reject request:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/requests/REQUEST_ID/reject \
  -H 'Content-Type: application/json' \
  -d '{"rejectedBy":"user","reason":"Not enough value for a meeting"}'
```

Required request-quality fields:

- `meetingGoal`
- `expectedOutcome`
- `cannotCompleteAloneReason`
- `suggestedParticipants`
- `suggestedMeetingType`

Rules:

- Do not create meeting requests for vague "please help" situations.
- Explain why a meeting is necessary.
- Pending requests must wait for user confirmation.
- User-selected context only becomes part of the meeting snapshot after confirmation.

### 10.7 Conflict Handling

Meetings can detect busy agents and existing meeting occupancy.

Conflict action endpoint:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/conflict \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"hermes-default","action":"wait"}'
```

Supported action concepts:

- `wait`: keep meeting in preparation/conflict state until agent is available.
- `reserve`: lightweight try-later reservation/reminder; not a full calendar scheduler.
- `replace`: replace busy participant with another agent.
- `force_join`: require explicit second confirmation.
- `cancel_conflict`: cancel that participant conflict.
- `refresh`: recompute conflicts.

Force join example:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/conflict \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"hermes-default","action":"force_join","confirmForce":true}'
```

Replacement example:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/conflict \
  -H 'Content-Type: application/json' \
  -d '{"by":"user","agentId":"hermes-default","action":"replace","replacementAgentId":"codex-local"}'
```

Conflict/advisory fields to inspect:

- `reason`: why the agent is busy.
- `riskLevel`: low, medium, or high.
- `summary`: current busy summary.
- `estimatedAvailability`: if known.
- `pauseCapability`: whether real or logical pause is possible.
- `advisory.recommendation`: recommendation such as wait/reserve/replace/force.
- `advisory.interruptionRisk`: risk explanation.
- `advisory.resumeNotes`: how to resume safely.

Rules:

- Advisory output is read-only. It must not directly change state.
- Do not force join without explicit user approval.
- One agent can participate in only one executable meeting at a time.
- Current try-later/reserve is lightweight and should not be described as a complete calendar scheduler.

### 10.8 Action Item Drafts

Task-collaboration meetings can produce action-item drafts. Drafts do not automatically become project tasks.

Update a draft:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{"action":"update","by":"user","title":"Refined task title","description":"Refined description","targetProjectId":"PROJECT_ID"}'
```

Reject a draft:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{"action":"reject","by":"user","reason":"No longer needed"}'
```

Keep as meeting-only:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/meetings/executable/MEETING_ID/action-items/ACTION_ITEM_ID \
  -H 'Content-Type: application/json' \
  -d '{"action":"keep","by":"user","reason":"Documented but not a project task"}'
```

Confirm into a project task:

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

Rules:

- Formal project task creation requires user confirmation.
- Use `idempotencyKey` for confirmation.
- Confirmed tasks store source meeting/action-item metadata.
- Rejected drafts remain auditable and do not create project tasks.

## 11. Projects and Tasks

Use projects for durable work that should be visible on a board.

List projects:

```bash
curl -sS http://127.0.0.1:8090/api/projects
```

Read a project:

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID
```

Create project:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "title":"Project title",
    "description":"Project purpose",
    "owner":"YOUR_AGENT_ID"
  }'
```

Create task:

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

Update task:

```bash
curl -sS -X PUT http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID \
  -H 'Content-Type: application/json' \
  -d '{"description":"Updated details","priority":"high"}'
```

Add task comment:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/comments \
  -H 'Content-Type: application/json' \
  -d '{"author":"YOUR_AGENT_ID","text":"Progress update or evidence."}'
```

Workflow endpoints:

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/status
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/chat
```

Start/stop legacy workflow:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/start \
  -H 'Content-Type: application/json' \
  -d '{"autoMode":true}'
```

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/workflow/stop
```

Rules:

- Use projects for durable work.
- Keep task titles short and descriptions actionable.
- Do not delete, reorder, or archive data unless explicitly asked.
- Add comments or evidence when changing work state.

## 12. Project Execution

Project Execution assigns project tasks to provider-backed agents and tracks execution, review, rework, and acceptance.

Validate workspace:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/project-execution/workspace/validate \
  -H 'Content-Type: application/json' \
  -d '{"workspacePath":"/path/to/workspace"}'
```

Start project-level execution:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/project-execution/start \
  -H 'Content-Type: application/json' \
  -d '{"mode":"continuous","skipReviewConfirmed":false}'
```

Start one task:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start \
  -H 'Content-Type: application/json' \
  -d '{"skipReviewConfirmed":false}'
```

Read status:

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/project-execution/status
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/status
```

Cancel active task:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/cancel \
  -H 'Content-Type: application/json' \
  -d '{"attemptId":"ATTEMPT_ID"}'
```

Start independent review:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/review/start \
  -H 'Content-Type: application/json' \
  -d '{"attemptId":"ATTEMPT_ID"}'
```

User acceptance:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/accept \
  -H 'Content-Type: application/json' \
  -d '{"action":"accept","attemptId":"ATTEMPT_ID"}'
```

Other acceptance actions:

- `reject_and_rework`
- `mark_blocked`

Important start fields:

- `mode`: `single` or `continuous` for project start.
- `skipReviewConfirmed`: true only after explicit user confirmation.
- `dirtyFingerprint`: required when retrying after dirty-workspace confirmation.

Important states:

- `backlog`
- `executing`
- `execution_complete`
- `reviewing`
- `awaiting_user_acceptance`
- `done`
- `blocked`

Safety gates:

- Dirty workspace requires explicit confirmation.
- Missing reviewer requires explicit skip-review confirmation.
- User acceptance is required when configured.
- Existing workspace changes are not rolled back on cancel.

## 13. Project Scheduled Cron

Project scheduled cron binds global OpenClaw Gateway cron jobs to project workflows or specific project tasks.

List all project cron bindings:

```bash
curl -sS http://127.0.0.1:8090/api/projects/scheduled-cron
```

List a project's cron jobs:

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron
```

Create project cron:

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

Create task cron:

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

Run now:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron/CRON_ID/run
```

Update:

```bash
curl -sS -X PUT http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron/CRON_ID \
  -H 'Content-Type: application/json' \
  -d '{"enabled":false}'
```

Delete:

```bash
curl -sS -X DELETE http://127.0.0.1:8090/api/projects/PROJECT_ID/scheduled-cron/CRON_ID
```

Schedule shapes:

- `{"kind":"cron","expr":"0 9 * * *","tz":"Asia/Shanghai"}`
- `{"kind":"every","everyMs":3600000}`
- `{"kind":"at","at":"2026-06-19T09:00:00+08:00"}`

Skip conditions:

- project archived
- project cron paused
- another project task already active
- target task missing
- completed task without scheduled repeat enabled
- dirty workspace confirmation required
- reviewer skip confirmation required

## 14. Artifacts

Artifacts expose Markdown outputs under a validated project execution workspace.

List project artifacts:

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/artifacts
```

Read one artifact:

```bash
curl -sS 'http://127.0.0.1:8090/api/projects/PROJECT_ID/artifacts/read?path=docs%2Fsummary.md'
```

Behavior:

- Lists Markdown files only: `.md`, `.markdown`.
- Skips noisy directories such as dependency and git directories.
- Reads are path-contained under the project workspace.
- Large reads are truncated.
- Non-Markdown inline reads are rejected.
- Source records connect artifacts to execution attempts when available.

Use artifacts for reviewable outputs. Do not use this as a general filesystem browser.

## 15. Codex Harness

When `VO_CODEX_ENABLED=1`, Codex appears as `codex-local`.

Health:

```bash
curl -sS http://127.0.0.1:8090/api/codex/test
```

Chat:

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

History and activity:

```bash
curl -sS 'http://127.0.0.1:8090/api/codex/history?conversationId=office-thread-id'
curl -sS 'http://127.0.0.1:8090/api/codex/activity?conversationId=office-thread-id'
```

Cancel:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/cancel \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id"}'
```

Compact:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/compact \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id"}'
```

Reset mapping:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/reset \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id"}'
```

Human interaction:

```bash
curl -sS -X POST http://127.0.0.1:8090/api/codex/interaction \
  -H 'Content-Type: application/json' \
  -d '{"agentId":"codex-local","conversationId":"office-thread-id","interactionId":"INTERACTION_ID","response":{"approved":true}}'
```

Important fields:

- `agentId`: normally `codex-local`.
- `conversationId`: office thread id mapped durably to a Codex thread.
- `message`: user/agent instruction.
- `workspace`: workspace root for the turn.
- `timeoutSec`: turn timeout.

Rules:

- One turn or compaction may run at a time per mapped conversation.
- Approval/user-input requests fail closed unless answered through interaction.
- `VO_CODEX_REPLY_TEXT` is deterministic demo mode and does not run real tools.

## 16. Shared Browser

The browser panel is a shared visible resource. Current agent-safe endpoints are status/read endpoints.

```bash
curl -sS http://127.0.0.1:8090/browser-status
curl -sS http://127.0.0.1:8090/browser-tabs
curl -sS http://127.0.0.1:8090/browser-controller
```

Rules:

- Treat the browser as shared.
- Announce use through presence or communication.
- Do not fight another controller.
- Do not use raw Kasm/CDP credentials unless the office exposes a safe action endpoint or the user explicitly authorizes it.

Known gap:

- Provider-neutral browser action endpoints are not implemented yet.

## 17. Agent Workspaces

Agent workspaces expose office-managed context for a visible agent.

Read workspace payload:

```bash
curl -sS http://127.0.0.1:8090/api/agent-workspace/YOUR_AGENT_ID
```

Update workspace payload:

```bash
curl -sS -X PUT http://127.0.0.1:8090/api/agent-workspace/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"notes":"Useful agent note","bulletin":"Current focus"}'
```

Workspace surfaces may include:

- overview
- bulletin
- tasks
- files
- skills
- notes
- settings

Rules:

- Treat workspace content as local office state.
- Do not store secrets in notes or bulletin.
- Prefer skills for reusable procedures.

## 18. Safety and Human Confirmation

Require explicit user confirmation before:

- starting a meeting from an AI request
- force-joining a busy agent into a meeting
- skipping an independent reviewer
- proceeding with dirty workspace execution
- accepting project execution output
- converting meeting action-item drafts into project tasks
- deleting projects/tasks/templates/agents
- changing raw browser/CDP behavior
- exposing secrets or private logs

Do not do these automatically:

- Start an unconfirmed AI meeting request.
- Execute a meeting action item.
- Pause or replace a busy agent from advisory output alone.
- Mark a task done without the required review/acceptance state.
- Use private cross-agent communication for office-visible work.

## 19. Common Workflows

### 19.1 Ask Another Agent for Review

1. Set presence to `working`.
2. Send message through AgentPlatform communications.
3. Store any durable outcome as a project comment/task if needed.
4. Set presence to `idle`.

```bash
curl -sS -X POST http://127.0.0.1:8090/api/agent-platform-communications/send \
  -H 'Content-Type: application/json' \
  -d '{"fromAgentId":"YOUR_AGENT_ID","toAgentId":"hermes-default","message":"Review this proposal for risks.","conversationId":"proposal-risk-review"}'
```

### 19.2 Request a Meeting Because a Task Is Blocked

1. Read the task and project.
2. Prepare concrete blocker explanation.
3. Create a meeting request under the task.
4. Wait for user confirmation.

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/meeting-requests \
  -H 'Content-Type: application/json' \
  -d '{"requesterAgentId":"YOUR_AGENT_ID","meetingGoal":"Decide data model","expectedOutcome":"One accepted schema","cannotCompleteAloneReason":"Requires product and implementation judgement","suggestedParticipants":["hermes-default","codex-local"],"suggestedMeetingType":"decision_discussion"}'
```

### 19.3 Execute a Project Task with Review

1. Validate workspace.
2. Start task execution.
3. Poll task execution status.
4. Start review if not automatic.
5. Wait for user acceptance.

```bash
curl -sS -X POST http://127.0.0.1:8090/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start \
  -H 'Content-Type: application/json' \
  -d '{}'
```

### 19.4 Review Meeting Action Items

1. Read executable meeting detail.
2. Inspect `actionItemDrafts`.
3. Update/reject/keep/confirm each draft.
4. Use idempotency keys for confirmations.

```bash
curl -sS http://127.0.0.1:8090/api/meetings/executable/MEETING_ID
```

### 19.5 Find Generated Markdown Outputs

1. Read project artifacts.
2. Open relevant Markdown artifact.
3. Cite path and source records in your response.

```bash
curl -sS http://127.0.0.1:8090/api/projects/PROJECT_ID/artifacts
```

## 20. Parameter Reference

### 20.1 Common IDs

| Parameter | Meaning | Example |
| --- | --- | --- |
| `agentId` | Office-visible agent id | `hermes-default` |
| `fromAgentId` | Sender agent id | `main` |
| `toAgentId` | Target agent id | `codex-local` |
| `conversationId` | Stable communication thread | `release-review` |
| `projectId` | Project id | `proj-123` |
| `taskId` | Task id | `task-456` |
| `meetingId` | Executable meeting id | UUID-like id |
| `attemptId` | Project execution attempt id | UUID-like id |
| `actionItemId` | Meeting action draft id | `action-1` |

### 20.2 Common Idempotency

Use `idempotencyKey` on operations that may be retried:

- executable meeting create
- meeting request confirm
- meeting conflict action
- meeting transition/intervention if available
- action item confirmation

Good keys are stable and scoped:

```text
meeting-request-confirm:<requestId>
meeting:<meetingId>:action:<actionItemId>:confirm
project:<projectId>:task:<taskId>:start
```

### 20.3 Schedule

Cron:

```json
{"kind":"cron","expr":"0 9 * * *","tz":"Asia/Shanghai"}
```

Every:

```json
{"kind":"every","everyMs":3600000}
```

At:

```json
{"kind":"at","at":"2026-06-19T09:00:00+08:00"}
```

### 20.4 Meeting Request Quality Fields

| Field | Required | Purpose |
| --- | --- | --- |
| `meetingGoal` | yes | What the meeting must solve |
| `expectedOutcome` | yes | What useful result looks like |
| `cannotCompleteAloneReason` | yes | Why the agent needs collaboration |
| `suggestedParticipants` | yes | Proposed office agent ids |
| `suggestedMeetingType` | yes | Meeting type |
| `urgency` | optional | `low`, `medium`, `high` |

### 20.5 Project Execution Confirmation Codes

When an execution start returns `confirmationRequired`, inspect:

- `code`
- `dirtyFingerprint`
- `dirtyFiles`
- `missingRole`
- `selectedTask`

Common codes:

- `dirty_worktree_confirmation_required`
- `reviewer_skip_confirmation_required`
- `no_eligible_task`

Respond only after user confirmation.

### 20.6 Error Handling

For any office API:

- Check `ok`.
- Check `_status` or HTTP status when available.
- Preserve and report `error`, `code`, and relevant ids.
- Do not silently retry high-impact operations without idempotency.
- Do not bypass the office when an office route fails; report the failure and ask for guidance when needed.
