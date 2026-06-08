# Codex Provider Adapter

Status: Phase 5 live bridge

The Codex adapter exposes one local Codex collaborator as a first-class Virtual Office agent without requiring OpenClaw or Hermes.

## Startup flags

- `VO_CODEX_ENABLED=1` enables the Codex harness.
- `VO_CODEX_AGENT_ID=local` sets the stable provider id. The office id becomes `codex-local`.
- `VO_CODEX_AGENT_NAME=Codex` sets the display name.
- `VO_CODEX_WORKSPACE=/path/to/repo` sets the readable and writable workspace.
- `VO_CODEX_MODEL=<model>` optionally overrides the Codex model.
- `VO_CODEX_BIN=codex` selects the local Codex CLI used by the default bridge.
- `VO_CODEX_REPLY_TEXT=<text>` enables deterministic regression replies.
- `VO_CODEX_BRIDGE_URL=<url>` overrides the local bridge with an externally managed HTTP bridge.

## Live bridge behavior

- Discovery returns one normalized `providerKind: "codex"` agent.
- Virtual Office starts and reuses a local `codex app-server` process by default.
- `/api/agent-platform-communications/send` supports human and agent senders.
- `/api/codex/chat` is the human chat-window route.
- Office `conversationId` values are durably mapped to Codex thread IDs under `VO_STATUS_DIR`.
- The same office conversation resumes the same Codex thread across refreshes and service restarts.
- One turn or context-compaction operation may run at a time; later requests return `busy` rather than queueing.
- Approval and user-input requests fail closed as `needs_human_intervention`.
- Results include terminal status, Codex thread/turn IDs, duration, and modified file paths.
- `/api/codex/compact` compresses the current thread without clearing visible office history.
- `/api/codex/reset` invalidates the mapping so the next message starts a new thread.
- `/api/codex/history` reads the office-owned communication history for a conversation.

## Security boundary

- Turns use `workspace-write`, the configured workspace as the writable root, and network access disabled.
- Phase 5 never auto-approves Codex approval requests.
- The default app-server transport is local stdio. Do not expose an unauthenticated listener on a non-loopback interface.

## External bridge contract

When `VO_CODEX_BRIDGE_URL` is set, Virtual Office posts JSON to `<url>/execute` and `<url>/compact`. The bridge returns the normalized fields `ok`, `status`, `reply`, `threadId`, `turnId`, `modifiedFiles`, `needsHumanIntervention`, and optional error/timing fields.

## Compatibility and scope

`VO_CODEX_REPLY_TEXT` simulates a stable demo thread so chat, history, reset, and compaction can be tested without Codex authentication.

Project automation, long-running orchestration, cancellation controls, interactive permission prompts, and streamed tool/file UI remain Phase 6 or later scope.
