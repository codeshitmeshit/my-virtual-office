> 中文版: [HERMES_PROVIDER_ADAPTER.cn.md](HERMES_PROVIDER_ADAPTER.cn.md)

# Hermes Provider Adapter

Status: native API client plus opt-in server-side run/event integration

## Goal

Add Hermes Agent support without turning My Virtual Office into a pile of platform-specific conditionals.

OpenClaw remains on the existing, proven code path. Hermes support starts as a separate provider adapter that can later become the template for other agent platforms.

## Current adapter

Path: `app/providers/hermes.py`

The adapter exposes:

- `discover_agents()` — returns Hermes profiles as normalized office agents
- `test()` — checks the configured Hermes CLI/home and returns detected profiles
- `send_message(profile, message)` — sends a one-shot Hermes message through the public CLI and returns stdout
- `send_chat_message(profile, message, session_id)` — CLI chat fallback for installs without the native API server
- `HermesApiClient` — talks to Hermes' native API server for runs, SSE events, approvals, and stops
- `create_agent(name, role, model, emoji, profile)` — creates a Hermes profile for a Virtual Office agent
- `delete_agent(profile)` — deletes a Hermes profile through the public CLI

It uses safe public Hermes surfaces only:

- `hermes profile list`
- `hermes profile show <profile>`
- `hermes profile create <profile> --clone --clone-from default --no-alias --description <role>`
- `hermes profile delete <profile> --yes`
- `hermes -z <message>`
- `hermes --profile <profile> -z <message>` for named profiles
- `POST /v1/runs`
- `GET /v1/runs/{run_id}/events`
- `POST /v1/runs/{run_id}/approval`
- `POST /v1/runs/{run_id}/stop`

## Native API routing

Hermes native API use is opt-in. When `hermes.apiEnabled` or the reference-compatible alias `hermes.preferApi` is enabled and the API server reports run submission plus SSE event support, `/api/hermes/chat` starts a Hermes API run, consumes native events server-side, normalizes the result into the existing Virtual Office chat/history shape, and records reply, thinking, tool cards, run/session IDs, approval state, and errors.

If the native API server is disabled, unavailable, or cannot start a run, `/api/hermes/chat` keeps the existing CLI fallback path. Approval events from the native API are stored in the same pending approval queue used by the rest of the chat UI.

The reference branch describes browser `EventSource` proxy routes such as `/api/hermes/runs/{runId}/events`. This local migration has not replaced the chat transport with those browser SSE routes; it intentionally keeps the current chat/project/meeting contracts and consumes native run events inside the server request path.

## Configuration

Hermes integration is configured through `vo-config.json` or environment variables:

- `VO_HERMES_ENABLED` / `hermes.enabled`
- `VO_HERMES_HOME` / `hermes.homePath`
- `VO_HERMES_BIN` / `hermes.binary`
- `VO_HERMES_TIMEOUT_SEC` / `hermes.timeoutSec`
- `VO_HERMES_API_ENABLED` / `hermes.apiEnabled`
- `VO_HERMES_PREFER_API` / `hermes.preferApi`
- `VO_HERMES_API_URL` / `hermes.apiUrl`
- `VO_HERMES_API_KEY` / `hermes.apiKey`

`preferApi` is accepted for compatibility with the reference implementation and maps to the same runtime behavior as `apiEnabled`.

It does **not** read or expose:

- `.env`
- `auth.json`
- raw config
- raw memories
- raw logs
- raw SQLite DB contents

## Normalized Hermes agent shape

Example:

```json
{
  "id": "hermes-default",
  "statusKey": "hermes-default",
  "providerKind": "hermes",
  "providerType": "runtime",
  "providerAgentId": "default",
  "profile": "default",
  "name": "Hermes",
  "emoji": "⚕️",
  "role": "Hermes Agent",
  "model": "gpt-5.5",
  "provider": "openai-codex",
  "capabilities": ["chat", "status", "sessions"]
}
```

## Server integration

`app/server.py` only routes Hermes-specific behavior to the Hermes adapter:

- `/api/hermes/test`
- `/api/hermes/chat`
- `/api/hermes/history`
- `/api/hermes/history/clear`
- `/api/agent/create` with `platform: "hermes"`
- `/api/agent/delete` for `hermes-<profile>` agents

OpenClaw discovery, chat, model info, skills, transcripts, and gateway paths are intentionally kept unchanged for now.

## Future provider shape

A future generic provider interface should look roughly like:

```python
class AgentProvider:
    provider_kind: str
    provider_type: str

    def discover_agents(self) -> list[dict]: ...
    def test(self) -> dict: ...
    def send_message(self, native_agent_id: str, message: str, **opts) -> dict: ...
    def get_history(self, native_agent_id: str, **opts) -> dict: ...
    def get_status(self, native_agent_id: str, **opts) -> dict: ...
```

For now, only Hermes is implemented this way to avoid breaking existing OpenClaw behavior.
