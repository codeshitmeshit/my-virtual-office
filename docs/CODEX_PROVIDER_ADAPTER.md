# Codex Provider Adapter

Status: Phase 4 MVP; live execution planned for Phase 5

The Codex adapter exposes a local Codex collaborator as a first-class Virtual Office agent without requiring OpenClaw or Hermes to be installed.

## Startup flags

- `VO_CODEX_ENABLED=1` enables the Codex harness.
- `VO_CODEX_AGENT_ID=local` sets the stable provider id. The office id becomes `codex-local`.
- `VO_CODEX_AGENT_NAME=Codex` sets the display name.
- `VO_CODEX_WORKSPACE=/path/to/repo` sets the workspace shown in metadata.
- `VO_CODEX_MODEL=<model>` sets display metadata.
- `VO_CODEX_REPLY_TEXT=<text>` returns deterministic replies for local/demo regression.
- `VO_CODEX_BRIDGE_URL=<url>` is reserved for the Phase 5 live bridge.

## Current behavior

- Discovery returns one normalized agent with `providerKind: "codex"` and `providerType: "harness"`.
- Presence defaults to idle from provider discovery and switches to working during office-mediated sends.
- `/api/agent-platform-communications/send` routes messages to the Codex adapter.
- `/agent-chat` shows request/reply communication events for the Codex agent.
- OpenClaw-only workspace files, HEARTBEAT, cron, model editing, and workspace skills are hidden for Codex.

## Boundary

The Phase 4 MVP does not execute a live Codex CLI session. If no live bridge or `VO_CODEX_REPLY_TEXT` is configured, messages are still logged visibly and the reply explains that the bridge is not configured.

Phase 5 should connect this adapter to a live Codex bridge: Virtual Office sends a message to Codex, Codex runs in a real CLI/session, and the final reply, status, timeout, and error events are returned to the same office communication/history surfaces. Project automation, long-running task orchestration, cancellation, permission prompts, and streamed tool/file events remain follow-up scope unless Phase 5 is explicitly expanded.
