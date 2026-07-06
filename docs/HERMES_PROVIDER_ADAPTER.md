# Hermes Provider Adapter

Status: native run streaming implementation

## Goal

Add Hermes Agent support without turning My Virtual Office into a pile of platform-specific conditionals.

OpenClaw remains on the existing, proven code path. Hermes support starts as a separate provider adapter that can later become the template for other agent platforms.

## Current adapter

Path: `app/providers/hermes.py`

The adapter exposes:

- `discover_agents()` — returns Hermes profiles as normalized office agents
- `discover_api_agents()` — returns an API-backed `hermes-default` agent when the Hermes App/API server is reachable
- `test()` — checks Hermes App/API and CLI/home separately and returns detected agents/modes
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
- `GET /v1/capabilities`
- `GET /v1/models`

## Native streaming

The chat UI uses Hermes' native run flow when `preferApi` is enabled and the App/API server is available:

1. `POST /api/hermes/runs` validates the selected office agent, starts a Hermes run through `POST /v1/runs`, stores only the run metadata needed by Virtual Office, and returns `runId`.
2. The browser opens `EventSource("/api/hermes/runs/{runId}/events")`.
3. The server proxies Hermes' native SSE lifecycle events to the browser while keeping the Hermes API key server-side.
4. The browser renders `message.delta`, `tool.started`, `tool.completed`, `tool.failed`, `approval.request`, and terminal run events directly.
5. History is saved for reloads and transcript views, but `/api/hermes/history` is not the live transport for native API runs.

If the native API server is unavailable, `/api/hermes/chat` remains as a CLI compatibility fallback when the CLI is installed or mounted into the Virtual Office container.

## Configuration

Hermes integration is product-neutral and configured through `vo-config.json` or environment variables:

- `VO_HERMES_HOME` / `hermes.homePath`
- `VO_HERMES_BIN` / `hermes.binary`
- `VO_HERMES_API_URL` / `hermes.apiUrl`
- `VO_HERMES_API_KEY` / `hermes.apiKey`
- `VO_HERMES_PREFER_API` / `hermes.preferApi`
- `VO_HERMES_AUTO_START_PROFILE_APIS` / `hermes.autoStartProfileApis`
- `VO_HERMES_AUTO_START_DEFAULT_API` / `hermes.autoStartDefaultApi`
- `VO_HERMES_API_PROFILE_PORT_BASE` / `hermes.apiProfilePortBase`
- `hermes.apiProfiles.<profile>` for profile-specific API URL/key/auto-start overrides

Virtual Office only auto-starts local Hermes API servers for local URLs such as `127.0.0.1` or `localhost`, and only when an API key is configured. Remote/user-managed API URLs are detected and used, not overwritten.

For Docker-hosted Virtual Office, the preferred setup is API-only: configure `VO_HERMES_API_URL=http://host.docker.internal:8642` and `VO_HERMES_API_KEY` to match Hermes' `API_SERVER_KEY`. CLI paths are optional and only needed for fallback chat, profile discovery beyond the default API agent, or create/delete profile operations.

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
