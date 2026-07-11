> 中文版: [HERMES_PROVIDER_ADAPTER.cn.md](HERMES_PROVIDER_ADAPTER.cn.md)

# Hermes Provider Adapter

Status: native run streaming implementation

## Goal

Add Hermes Agent support without turning My Virtual Office into a pile of platform-specific conditionals.

OpenClaw remains on the existing, proven code path. Hermes support starts as a separate provider adapter that can later become the template for other agent platforms.

## Current adapter

Path: `app/providers/hermes.py`

The adapter exposes:

- `discover_agents()` — returns Hermes profiles as normalized office agents
- `discover_api_agents()` — discovers API Server-backed agents
- `discover_desktop_agents()` — discovers Desktop Backend-backed agents
- `test()` — checks the CLI/home adapter mode; the server's `/api/hermes/test` handler combines API Server, Desktop Backend, Gateway Platform, and CLI results
- `send_message(profile, message)` — sends a one-shot Hermes message through the public CLI and returns stdout
- `send_chat_message(profile, message, session_id)` — CLI chat fallback for installs without the native API server
- `HermesApiClient` — talks to Hermes' native API server for runs, SSE events, approvals, and stops
- `HermesDesktopBackendClient` — talks to Desktop's `hermes serve` status and WebSocket JSON-RPC surfaces
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
- `GET /api/status`
- WebSocket `/api/ws` TUI-gateway JSON-RPC

## Native streaming

The chat UI starts native runs with `POST /api/hermes/runs`, then opens `EventSource("/api/hermes/runs/{runId}/events")`. The server proxies normalized message, reasoning, tool, approval, and terminal events while keeping provider credentials server-side. Conversation history is persisted for reloads and session browsing.

When configured, Desktop Backend uses the same browser run/SSE contract while communicating with `hermes serve` through its TUI-gateway WebSocket API. The synchronous `/api/hermes/chat` path and CLI remain compatibility fallbacks.

## Messaging Gateway platform mode

The plugin under `integrations/hermes-platform/my_virtual_office/` lets Hermes Gateway poll queued office messages and post replies. This mode is separate from API Server and Desktop Backend; see [HERMES_PLATFORM_ADAPTER.md](HERMES_PLATFORM_ADAPTER.md).

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
- `VO_HERMES_DESKTOP_URL` / `hermes.desktopUrl`
- `VO_HERMES_DESKTOP_TOKEN` / `hermes.desktopToken`
- `VO_HERMES_DESKTOP_HOST_HEADER` / `hermes.desktopHostHeader`
- `VO_HERMES_DESKTOP_TCP_HOST` / `hermes.desktopTcpHost`
- `VO_HERMES_DESKTOP_TCP_PORT` / `hermes.desktopTcpPort`
- `VO_HERMES_DESKTOP_LOG_PATH` / `hermes.desktopLogPath`
- `VO_HERMES_PLATFORM_ENABLED` / `hermes.platformEnabled`
- `VO_HERMES_PLATFORM_TOKEN` / `hermes.platformToken`
- `VO_HERMES_PLATFORM_AGENT_ID` / `hermes.platformAgentId`

`preferApi` is accepted for compatibility with the reference implementation and maps to the same runtime behavior as `apiEnabled`.

Desktop auto-discovery may use an exposed readiness log, a previously configured URL, or visible loopback listeners. Docker deployments can route loopback Desktop services through `host.docker.internal` while preserving the logical Host header; the TCP host/port and Host header settings provide explicit overrides.

For Desktop port discovery, the integration may read a bounded tail of the configured readiness log. It extracts listener ports only and does not return or expose the raw log contents.

It does **not** read or expose:

- `.env`
- `auth.json`
- raw config
- raw memories
- raw log contents (apart from the bounded Desktop readiness scan described above)
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

`app/server.py` owns the HTTP routes, Virtual Office state, and run/session/platform orchestration. `app/providers/hermes.py` owns Hermes clients, discovery, and provider-protocol adaptation. The server exposes:

- `/api/hermes/test`
- `/api/hermes/chat`
- `/api/hermes/runs`
- `/api/hermes/runs/{runId}/events`
- `/api/hermes/desktop/discover`
- `/api/hermes-platform/*`
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
