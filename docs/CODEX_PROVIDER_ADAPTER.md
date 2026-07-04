> 中文版: [CODEX_PROVIDER_ADAPTER.cn.md](CODEX_PROVIDER_ADAPTER.cn.md)

# Codex Provider Adapter

Status: live bridge and project-execution provider

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
- `/api/codex/activity` returns correlated turn, reasoning, tool/file, interaction, and terminal events for the active office conversation.
- Office `conversationId` values are durably mapped to Codex thread IDs under `VO_STATUS_DIR`.
- The same office conversation resumes the same Codex thread across refreshes and service restarts.
- One turn or context-compaction operation may run at a time; later requests return `busy` rather than queueing.
- Approval and user-input requests fail closed by default as `needs_human_intervention`.
- When interaction mode is enabled for a turn, `/api/codex/interaction` can answer pending approval/user-input requests and continue the original turn.
- `/api/codex/cancel` requests cancellation of the active turn for the mapped Codex thread.
- Results include terminal status, Codex thread/turn IDs, duration, and modified file paths.
- `/api/codex/compact` compresses the current thread without clearing visible office history.
- `/api/codex/reset` invalidates the mapping so the next message starts a new thread.
- `/api/codex/history` reads the office-owned communication history for a conversation.

## Project execution

Codex provider refs are supported by the Projects feature. A Codex-backed task execution receives the selected project workspace and records normalized evidence for downstream review and user acceptance.

Project execution supports:

- project-level and task-level starts
- single-task starts and continuous project execution
- workspace validation and dirty-workspace confirmation
- system-managed auto workspaces and user-managed manual workspaces
- independent reviewer routing
- reviewer-skip confirmation when explicitly allowed
- cancellation of active task execution
- review start, user acceptance, rejection, and blocked outcomes
- changed-file evidence and Markdown artifact discovery under the project workspace
- safe inline Markdown artifact reads with path containment and size limits

Workspace controls:

- `VO_AUTO_PROJECT_WORKSPACE_ROOT` sets the root used when Virtual Office creates managed project workspaces.
- `VO_PROJECT_ROOTS` can restrict manual project workspaces to an allow-list of real paths.
- Managed workspaces can be deleted with their project; user-managed workspaces are never deleted by project deletion.

Relevant routes:

- `POST /api/projects/<projectId>/project-execution/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/cancel`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/review/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/accept`
- `GET /api/projects/<projectId>/artifacts`
- `GET /api/projects/<projectId>/artifacts/read?path=<relativePath>`

## Security boundary

- Turns use `workspace-write`, the configured workspace as the writable root, and network access disabled unless the user explicitly approves broader Codex behavior outside Virtual Office.
- Approval/user-input requests are never auto-approved by the adapter.
- The default app-server transport is local stdio. Do not expose an unauthenticated listener on a non-loopback interface.

## External bridge contract

When `VO_CODEX_BRIDGE_URL` is set, Virtual Office posts JSON to `<url>/execute` and `<url>/compact`. The bridge returns the normalized fields `ok`, `status`, `reply`, `threadId`, `turnId`, `modifiedFiles`, `needsHumanIntervention`, and optional error/timing fields.

## Compatibility and scope

`VO_CODEX_REPLY_TEXT` simulates a stable demo thread so chat, history, reset, and compaction can be tested without Codex authentication.

Current known limits:

- Only one local Codex collaborator is exposed by the adapter.
- Provider-neutral browser action routing is separate from the Codex bridge and is not a Codex-specific capability.
- `VO_CODEX_REPLY_TEXT` is for deterministic regression/demo mode and does not exercise live tool execution.
