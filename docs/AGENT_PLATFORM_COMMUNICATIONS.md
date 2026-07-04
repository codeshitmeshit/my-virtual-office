> 中文版: [AGENT_PLATFORM_COMMUNICATIONS.cn.md](AGENT_PLATFORM_COMMUNICATIONS.cn.md)

# AgentPlatform-to-AgentPlatform Communications

Status: first working implementation

## Goal

Give My Virtual Office a built-in communication layer that agent platforms can use to talk to each other through the office instead of through offscreen private CLI calls.

This is the foundation for visible cross-platform conversations between OpenClaw, Hermes, Codex, and future provider adapters.

## Built-in skill

Skill name:

`AgentPlatform-to-AgentPlatform_Communications`

The skill is seeded into the Virtual Office Skills Library and is also exposed at:

`GET /api/agent-platform-communications/skill`

Agents can read/apply the skill and learn the endpoint without custom code.

## Send endpoint

`POST /api/agent-platform-communications/send`

Body:

```json
{
  "fromAgentId": "main",
  "toAgentId": "hermes-default",
  "message": "Hi Hermes, can you review this?",
  "conversationId": "optional-thread-id",
  "metadata": {"topic": "optional"}
}
```

Response:

```json
{
  "ok": true,
  "conversationId": "main__hermes-default",
  "messageId": "...",
  "replyMessageId": "...",
  "reply": "..."
}
```

## History endpoint

`GET /api/agent-platform-communications/history?conversationId=<id>`

Optional filters:

- `conversationId`
- `agentId`
- `limit`

Events are stored in:

`VO_STATUS_DIR/agent-platform-communications.jsonl`

Each event has a normalized shape with:

- schema
- id
- timestamp
- conversationId
- direction: `request` or `reply`
- from agent ref
- to agent ref
- text
- metadata
- visibleInOffice flag

## Current routing

The communication layer routes through the server-side agent-call abstraction:

- OpenClaw targets use existing OpenClaw workflow/gateway/CLI path.
- Hermes targets use the Hermes provider adapter.
- Codex targets use the optional Codex harness adapter when `VO_CODEX_ENABLED=1`.
- Future providers should implement the provider adapter interface and then can be called through the same layer.

## Visibility

This implementation logs conversations in an office-owned communication log. `/agent-chat` merges those communication events into each involved agent's chat-bubble payload so cross-platform agent conversations are visible instead of happening offscreen.

## Verified

Product instance tests passed:

- skill endpoint returns valid SKILL.md content
- skill appears in Skills Library
- `main` → `hermes-default` message routes successfully
- Hermes reply is logged as a reply event
- history endpoint returns request + reply
- Hermes presence switches to working during the call and idle after
- `/agent-chat` shows request/reply events under both participating agents

Codex live bridge:

- `VO_CODEX_ENABLED=1` discovers `codex-local` without requiring OpenClaw/Hermes
- `VO_CODEX_REPLY_TEXT=<text>` provides deterministic demo replies for communication tests
- without `VO_CODEX_BRIDGE_URL`, Virtual Office uses a local `codex app-server` bridge
- Codex events persist thread, turn, terminal-status, modified-file, and intervention metadata
- office conversations resume their mapped Codex thread across refreshes and service restarts
- Codex context can be compacted or reset through dedicated endpoints
