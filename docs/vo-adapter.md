> 中文版: [vo-adapter.cn.md](vo-adapter.cn.md)

# Virtual Office Provider Adapter Guide

Status: implementation guide for new CLI/runtime providers

## Goal

This guide explains how a new CLI tool or local agent runtime should integrate
with My Virtual Office as a first-class provider.

The important idea is that Virtual Office should not care whether the provider
is backed by a CLI process, a local app-server, a native HTTP API, a WebSocket
gateway, or an external bridge. The provider adapter owns those details and
exposes a normalized contract to the office.

## Mental model

A complete integration has three layers:

1. Provider runtime bridge

   This is the provider-specific execution layer.

   Examples:

   - Codex: local `codex app-server --stdio`, or external HTTP bridge via
     `VO_CODEX_BRIDGE_URL`.
   - Claude Code: local `claude` CLI harness using stream JSON output.
   - Hermes: Hermes CLI fallback or native API run/event routes.

2. Virtual Office provider adapter

   This is a Python adapter under `app/providers/` plus server-side handler
   functions in `app/server.py`. It converts provider-specific behavior into
   normalized office agent discovery, chat/run results, status, history, and
   optional event streams.

3. Virtual Office communication surfaces

   These are office-owned APIs such as:

   - `POST /api/agent-platform-communications/send`
   - `GET /api/agent-platform-communications/history`
   - provider-specific chat/run routes
   - Project Execution and Executable Meeting call paths

If the adapter implements the normalized contract, other office features can
route messages to it without knowing the runtime internals.

## Integration levels

### Level 1: visible agent and blocking chat

This is the minimum useful integration.

The provider must support:

- discovery as one or more office agents
- a stable `providerKind`
- a stable office agent id
- blocking message execution
- normalized result fields
- office-owned request/reply history
- visible presence while a call is running

With this level, the provider can participate in:

- chat window messages
- AgentPlatform-to-AgentPlatform communications
- basic AI meeting turns
- basic Project Execution calls, if workspace behavior is safe enough

### Level 2: background runs and progress events

Add this when provider calls can take time or emit useful intermediate state.

The provider should support:

- run start endpoint
- server-side worker or async task
- streamed event normalization
- progress/history messages
- terminal run states
- cancellation

Codex, Claude Code, and Hermes background runs use `ProviderRunCoordinator`
with one run repository and event journal. Read-only `ProviderSSETransport`
provides UI streaming.

### Level 3: full office integration

Add this for complete parity with first-class providers.

The provider should support:

- approvals or human input
- cancellation/stop
- session or thread persistence
- context reset/compact if the runtime supports it
- modified-file evidence
- token/tool/reasoning metadata where available
- workspace selection
- Project Execution evidence
- safe artifact discovery
- deterministic test mode

## Provider agent shape

Discovery should return office agent dictionaries with this shape:

```json
{
  "id": "provider-profile",
  "statusKey": "provider-profile",
  "providerKind": "example",
  "providerType": "cli",
  "providerAgentId": "profile",
  "profile": "profile",
  "name": "Example Agent",
  "emoji": "🤖",
  "role": "Example Provider Agent",
  "model": "optional-model",
  "workspace": "/path/to/workspace",
  "lastActiveAt": 0,
  "capabilities": ["chat", "runs", "status", "sessions"]
}
```

Required fields:

- `id`: stable office id. Use a provider prefix, for example
  `example-default`.
- `statusKey`: key used by presence/status rendering. Usually same as `id`.
- `providerKind`: lowercase provider key used for routing.
- `providerType`: implementation class, such as `cli`, `api`, `gateway`,
  `app-server-bridge`, or `harness`.
- `providerAgentId` or `profile`: native provider identity.
- `name`: display name.

Recommended fields:

- `emoji`
- `role`
- `model`
- `workspace`
- `lastActiveAt`
- `capabilities`

## Provider class contract

Create an adapter under `app/providers/<provider>.py`.

The class should look roughly like this:

```python
class ExampleProvider:
    provider_kind = "example"
    provider_type = "cli"

    def __init__(self, enabled=False, binary=None, home_path=None, workspace=None, **opts):
        ...

    def is_available(self) -> bool:
        ...

    def discover_agents(self) -> list[dict]:
        ...

    def test(self) -> dict:
        ...

    def send_chat_message(
        self,
        message: str,
        conversation_id: str = "",
        session_id: str | None = None,
        timeout_sec: int | None = None,
        on_progress=None,
    ) -> dict:
        ...

    def cancel(self, session_id: str = "", run_id: str = "") -> dict:
        ...
```

Only `discover_agents()`, `test()`, and `send_chat_message()` are required for
Level 1. Everything else is optional but recommended for full integration.

## Normalized result contract

Every provider call should return a dictionary that can be passed to
`normalize_provider_result()`.

Minimum successful result:

```json
{
  "ok": true,
  "status": "completed",
  "reply": "final answer",
  "conversationId": "office-conversation",
  "sessionId": "native-session-or-thread",
  "runId": "native-run-or-turn",
  "modifiedFiles": [],
  "tools": [],
  "thinking": "",
  "tokenUsage": {},
  "providerMetadata": {}
}
```

Minimum failed result:

```json
{
  "ok": false,
  "status": "execution_failed",
  "error": "human readable error",
  "errorCode": "optional_machine_code",
  "reply": "",
  "needsHumanIntervention": false
}
```

Common terminal statuses:

- `completed`
- `cancelled`
- `timeout`
- `busy`
- `disabled`
- `provider_unavailable`
- `bridge_unavailable`
- `needs_human_intervention`
- `invalid_request`
- `execution_failed`

Use `provider_http_status()` in `provider_execution.py` to map provider status
to HTTP status.

## Server integration checklist

### 1. Configuration

Add config loading to `_load_vo_config()` in `app/server.py`.

Prefer environment variables plus optional `vo-config.json` fields:

```text
VO_EXAMPLE_ENABLED=1
VO_EXAMPLE_HOME=~/.example
VO_EXAMPLE_BIN=example
VO_EXAMPLE_WORKSPACE=/path/to/workspace
VO_EXAMPLE_TIMEOUT_SEC=600
VO_EXAMPLE_REPLY_TEXT=fixture reply
```

`VO_EXAMPLE_REPLY_TEXT` is strongly recommended for deterministic tests.

### 2. Discovery

Add a discovery function in `app/discovery.py`, or extend the provider-specific
discovery path in `server.py`.

The provider should be visible in:

- `GET /agents-list`
- `GET /api/agent-platforms`
- `/status` when presence defaults are added

### 3. Provider lookup

Add helper functions in `server.py` similar to existing provider helpers:

- `_get_example_agent(agent_key)`
- `_example_provider_from_config()`
- `_handle_example_test(body=None)`

### 4. Chat handler

Add a blocking chat handler:

```python
def _handle_example_chat(body):
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or "example-default"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    ...
    result = provider.send_chat_message(
        message,
        conversation_id=conversation_id,
        session_id=current_session_id,
        timeout_sec=timeout,
    )
    normalized = normalize_provider_result(
        "example",
        agent,
        result,
        conversation_id=conversation_id,
        session_id=result.get("sessionId", ""),
        run_id=result.get("runId", ""),
        modified_files=result.get("modifiedFiles") or [],
    )
    normalized["_status"] = provider_http_status(normalized)
    return normalized
```

The handler should:

- validate `message`
- validate target agent
- apply archive/guard logic if relevant
- set presence to `working` while running
- persist provider-visible history if the provider needs it
- normalize the result
- set presence back to `idle` or `offline`

### 5. Route registration

Add HTTP routes in `OfficeHandler`:

- `POST /api/example/chat`
- `POST /api/example/runs` if background runs are supported
- `GET /api/example/runs/<runId>/events` if SSE is supported
- `POST /api/example/runs/<runId>/stop` or `POST /api/example/cancel`
- `POST /api/example/reset` if sessions can reset
- `GET /api/example/history` if office-owned history is exposed
- `POST /api/example/test`

### 6. AgentPlatform communication routing

Add a branch in `_handle_agent_platform_comm_send()`:

```python
elif str(to_ref.get("providerKind") or "").lower() == "example":
    provider_result = _handle_example_chat({
        "agentId": to_ref["id"],
        "message": target_prompt,
        "timeoutSec": timeout,
        "conversationId": conversation_id,
        "fromType": "human" if is_human_source else "agent",
    })
    reply = provider_result.get("reply") or provider_result.get("error") or ""
    ok = bool(provider_result.get("ok"))
```

This is what lets other providers communicate with the new provider through:

```text
POST /api/agent-platform-communications/send
```

### 7. Project Execution routing

If the provider can safely operate in a project workspace, add it to the
Project Execution provider call path.

The provider must support:

- workspace override for each task
- timeout
- modified file collection if possible
- cancellation if possible
- clear terminal status
- no writes outside the selected workspace unless explicitly designed

Project Execution should call the same normalized chat/run handler, not a
separate private implementation.

### 8. Meeting routing

Add the provider to `_meeting_call_provider()` so Executable Meeting can call
it as a participant.

The meeting call path needs:

- `agentId`
- `message`
- `conversationId = meeting:<id>:participant:<agent>`
- timeout
- normalized `reply`

### 9. Presence and status

Use existing presence helpers so office users can see activity.

At minimum:

- set working while a call is active
- return to idle after success
- return to offline or idle with error metadata after failure

If the runtime emits native lifecycle events, map them to provider events:

- `run.started`
- `message.delta`
- `reasoning.available`
- `tool.started`
- `tool.completed`
- `approval.request`
- `run.completed`
- `run.failed`
- `run.cancelled`

### 10. History

There are two history scopes:

1. Office communication history

   Stored in:

   ```text
   VO_STATUS_DIR/agent-platform-communications.jsonl
   ```

   This is owned by Virtual Office and powers visible cross-provider messages.

2. Provider native history

   Optional. Store only what the provider adapter needs to resume sessions.
   Avoid reading or exposing private raw provider data unless the provider's
   public API explicitly supports it.

## Background run and SSE contract

If the provider supports streaming output, register a capability adapter and
use `ProviderRunCoordinator` plus `ProviderSSETransport`; do not create a
second run/event authority.

Recommended event names:

- `run.started`
- `message.delta`
- `reasoning.available`
- `tool.started`
- `tool.completed`
- `tool.failed`
- `approval.request`
- `run.completed`
- `run.failed`
- `run.cancelled`

Recommended run start response:

```json
{
  "ok": true,
  "runId": "example-...",
  "providerPath": "example-cli",
  "agent": {
    "id": "example-default",
    "name": "Example",
    "providerKind": "example",
    "profile": "default"
  }
}
```

Recommended SSE payload fields:

```json
{
  "runId": "example-...",
  "agentId": "example-default",
  "conversationId": "thread",
  "sessionId": "native-session",
  "runNativeId": "native-run",
  "status": "running",
  "text": "delta",
  "reply": "final reply",
  "error": "",
  "modifiedFiles": [],
  "needsHumanIntervention": false,
  "providerPath": "example-cli"
}
```

## Approvals and human input

Approval and human-input requests must fail closed unless the user explicitly
responds.

Recommended behavior:

- Normalize pending approvals as `needsHumanIntervention: true`.
- Surface enough metadata for UI display: title, description, choices,
  operation id, interaction id.
- Provide a response endpoint such as:

  ```text
  POST /api/example/interaction
  POST /api/example/approval/respond
  ```

- Never auto-approve file writes, shell commands, external network access, or
  credential use.

## Cancellation

If the provider has long-running calls, implement cancellation.

Recommended behavior:

- Store active operation by `agentId + conversationId`.
- Return `busy` when a second operation would collide.
- Provide a stop/cancel route.
- Mark terminal state as `cancelled` when the provider confirms cancellation.
- If cancellation is best-effort, report that clearly in the normalized result.

## Workspace and file safety

For providers that can edit files:

- accept a per-call workspace override
- resolve workspace paths with `realpath`
- restrict writes to the selected workspace
- never delete user-managed workspaces implicitly
- collect modified file paths when possible
- return modified file paths as relative or display-safe paths
- avoid exposing secrets, raw auth files, provider memory DBs, or private logs

Project Execution depends on this boundary.

## Deterministic test mode

Every provider should support a deterministic reply fixture.

Example:

```text
VO_EXAMPLE_REPLY_TEXT="fixture response"
```

When set, the adapter should:

- skip the real runtime call
- return `ok: true`
- return stable `sessionId`/`runId`
- emit no real tools
- modify no files

This makes chat, routing, history, and UI tests independent of provider
authentication.

## Testing checklist

Add tests for these behaviors:

- provider disabled returns a clear error
- provider test endpoint reports installed/auth status
- discovery returns normalized agent shape
- blocking chat validates message and agent id
- successful chat returns normalized result
- failure maps to provider HTTP status
- AgentPlatform send routes to the provider
- request and reply are appended to communication history
- presence switches to working and then idle/offline
- deterministic reply mode works without provider auth
- run/SSE emits started, progress, and terminal events if supported
- cancel returns a terminal state if supported
- Project Execution can call the provider when workspace is valid
- Project Execution blocks or reports intervention when workspace/roles fail
- Executable Meeting can call the provider as a participant

## Minimal implementation sequence

1. Add `app/providers/example.py`.
2. Add config fields in `_load_vo_config()`.
3. Add discovery into roster aggregation.
4. Add `_handle_example_test()` and `_handle_example_chat()`.
5. Add HTTP routes.
6. Add `_handle_agent_platform_comm_send()` routing branch.
7. Add deterministic reply tests.
8. Add Project Execution and Meeting routing if the provider should participate.
9. Add background run/SSE, approvals, cancellation, and file evidence.

## Design rules

- Keep provider-specific code inside the adapter and thin server routing.
- Do not let general office features call provider CLIs directly.
- Do not read private provider internals when a public API or CLI surface exists.
- Normalize results before returning them to office features.
- Prefer visible office communication over offscreen private CLI messages.
- Treat workspace writes, shell execution, browser access, and credentials as
  explicit safety boundaries.

## Current references

- `app/providers/codex.py`
- `app/providers/codex_app_server.py`
- `app/providers/claude_code.py`
- `app/providers/hermes.py`
- `app/provider_execution.py`
- `docs/AGENT_PLATFORM_COMMUNICATIONS.md`
- `docs/CODEX_PROVIDER_ADAPTER.md`
- `docs/HERMES_PROVIDER_ADAPTER.md`
- `docs/VIRTUAL_OFFICE_AGENT_TOOLS.md`
