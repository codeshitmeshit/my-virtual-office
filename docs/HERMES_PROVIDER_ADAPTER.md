# Hermes Provider Adapter

Status: first implementation

## Goal

Add Hermes Agent support without turning My Virtual Office into a pile of platform-specific conditionals.

OpenClaw remains on the existing, proven code path. Hermes support starts as a separate provider adapter that can later become the template for other agent platforms.

## Current adapter

Path: `app/providers/hermes.py`

The adapter exposes:

- `discover_agents()` — returns Hermes profiles as normalized office agents
- `test()` — checks the configured Hermes CLI/home and returns detected profiles
- `send_message(profile, message)` — sends a one-shot Hermes message through the public CLI and returns stdout

It uses safe public Hermes surfaces only:

- `hermes profile list`
- `hermes profile show <profile>`
- `hermes -z <message>`
- `hermes --profile <profile> -z <message>` for named profiles

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
