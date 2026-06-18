# Virtual Office Agent Tools

Status: canonical agent-facing tool index  
Scope: My Virtual Office Product

## Purpose

This document is the organized index for tools that agents can use through My Virtual Office. It avoids duplicate scattered instructions and points every platform toward the same office-owned surfaces.

The companion architecture document is `docs/UNIVERSAL-AGENT-HARNESS-SPEC.md`.

For a detailed agent operating manual with examples, parameters, and safety rules, see `docs/VO_AGENT_USAGE_GUIDE.md`.

## Built-in skills

Virtual Office seeds these skills into the Skills Library so agents can learn how to use office tools without custom platform code:

- `AgentPlatform-to-AgentPlatform_Communications`
- `VirtualOffice-Presence-and-Status`
- `VirtualOffice-Browser-Control`
- `VirtualOffice-Meetings`
- `VirtualOffice-Projects-and-Tasks`

Skills Library endpoints:

- `GET /api/skills-library`
- `GET /api/skills-library/<skill-name>`
- `POST /api/skills-library/apply`

The raw cross-platform communication skill is also exposed at:

- `GET /api/agent-platform-communications/skill`

## Tool surfaces

### Agent platforms

Use when the office needs to create or remove agents on a connected platform.

- `GET /api/agent-platforms`
- `POST /api/agent/create`
- `DELETE /api/agent/delete`

`POST /api/agent/create` accepts `platform: "openclaw"`, `platform: "hermes"`, `platform: "codex"`, or `platform: "claude-code"`. OpenClaw creation goes through Gateway `agents.create` / `agents.files.set` so the agent is runnable immediately and files are owned by the OpenClaw user. Hermes creation maps one office agent to one Hermes profile and uses `hermes profile create/delete`. Codex creation maps one office agent to a Codex workspace, writes `AGENTS.md` plus `.codex/agents/<profile>.toml`, and chats through Codex's native app-server JSON-RPC protocol. Claude Code creation maps one office agent to a Claude Code workspace, writes `AGENTS.md`, `CLAUDE.md`, and `.claude/agents/<profile>.md`, and chats through Claude Code's native `stream-json` CLI protocol.

Codex creation supports two location modes:

- `codexCreationMode: "standard"`: create under configured `codex.workspaceRoot` and register `$CODEX_HOME/agents/<profile>.toml` when native registration is enabled.
- `codexCreationMode: "custom"` with `codexCustomDirectory`: create `<codexCustomDirectory>/<profile>` and write project-local `.codex/agents/<profile>.toml`. Virtual Office stores a registry entry under `codex.workspaceRoot` so the custom agent remains discoverable.

Codex discovery also reads the standard `$CODEX_HOME/agents/*.toml` custom-agent directory and includes a synthesized `codex-main` entry for Codex's default Main agent.

Codex app-server approval requests are surfaced through chat history while a turn is running. The web chat renders pending command, file-change, and permission approval cards with Approve/Cancel controls. Integrations can also poll `GET /api/codex/approval/pending?agentId=<id>` and answer the active callback with `POST /api/codex/approval/respond` using `approval_id` and `choice: "approve"` or `"cancel"`.

Claude Code creation supports two location modes:

- `claudeCodeCreationMode: "standard"`: create under configured `claudeCode.workspaceRoot` and register `$CLAUDE_CONFIG_DIR/agents/<profile>.md` when native registration is enabled.
- `claudeCodeCreationMode: "custom"` with `claudeCodeCustomDirectory`: create `<claudeCodeCustomDirectory>/<profile>` and write project-local `.claude/agents/<profile>.md`. Virtual Office stores a registry entry under `claudeCode.workspaceRoot` so the custom agent remains discoverable.

Claude Code discovery also reads native `$CLAUDE_CONFIG_DIR/agents/*.md` subagents and includes a synthesized `claude-code-main` entry for Claude Code's default Main agent.

Claude Code chat uses `claude -p --output-format stream-json --include-partial-messages` with `--resume <session_id>` when available. The adapter converts assistant deltas, `tool_use` blocks, `tool_result` blocks, usage metadata, run completion, and interrupts into the same Virtual Office chat/event shapes used by Hermes and Codex.

Codex configuration is product-neutral:

- `VO_CODEX_BIN`: Codex CLI executable, default `codex` on `PATH`
- `VO_CODEX_HOME`: Codex auth/config home for this deployment, default `VO_STATUS_DIR/codex-home` in Docker
- `VO_CODEX_WORKSPACE_ROOT`: Office-created Codex agent workspaces
- `VO_CODEX_MAIN_WORKSPACE`: Workspace used by `codex-main` and native custom agents
- `VO_CODEX_INCLUDE_MAIN`: include Codex's default Main agent, enabled by default
- `VO_CODEX_INCLUDE_NATIVE_AGENTS`: read `$CODEX_HOME/agents/*.toml`, enabled by default
- `VO_CODEX_REGISTER_NATIVE_AGENTS`: write `$CODEX_HOME/agents/<profile>.toml` when creating VO Codex agents, enabled by default
- `VO_CODEX_PREFER_APP_SERVER`: native app-server integration on by default
- `VO_CODEX_SANDBOX`: Codex sandbox mode, Docker example defaults to `danger-full-access` because bubblewrap sandboxing usually needs extra container privileges
- `VO_CODEX_APPROVAL_POLICY`: Codex approval policy, default `never` so unattended Office runs do not hang on approval prompts

Claude Code configuration is product-neutral:

- `VO_CLAUDE_CODE_BIN`: Claude Code CLI executable, default `claude` on `PATH`
- `VO_CLAUDE_CODE_HOME`: Claude config/auth directory for this deployment
- `VO_CLAUDE_CODE_WORKSPACE_ROOT`: Office-created Claude Code agent workspaces
- `VO_CLAUDE_CODE_MAIN_WORKSPACE`: Workspace used by `claude-code-main` and native subagents
- `VO_CLAUDE_CODE_MODEL`: optional default Claude Code model
- `VO_CLAUDE_CODE_PERMISSION_MODE`: Claude Code permission mode, default `acceptEdits`
- `VO_CLAUDE_CODE_INCLUDE_MAIN`: include Claude Code's default Main agent, enabled by default
- `VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS`: read `$CLAUDE_CONFIG_DIR/agents/*.md`, enabled by default
- `VO_CLAUDE_CODE_REGISTER_NATIVE_AGENTS`: write `$CLAUDE_CONFIG_DIR/agents/<profile>.md` when creating standard VO Claude Code agents, enabled by default

Never hardcode host usernames, personal auth paths, or a developer's local container layout into Codex or Claude Code product support.

Codex is an opt-in collaborator harness, not a created agent type. Enable it at startup with `VO_CODEX_ENABLED=1`; it appears as a visible office agent and receives messages through the same communication layer. `VO_CODEX_REPLY_TEXT=<text>` can be used for deterministic local regression until a live Codex bridge is configured.

### AgentPlatform-to-AgentPlatform Communications

Use when agents need to talk across providers and the exchange should be visible in Virtual Office.

- `POST /api/agent-platform-communications/send`
- `GET /api/agent-platform-communications/history`

Events are stored in:

- `VO_STATUS_DIR/agent-platform-communications.jsonl`

These events are merged into `/agent-chat`, so chat bubbles can show cross-platform interactions.

Supported routed targets today:

- OpenClaw agents
- Hermes profiles
- Codex harness agent, when `VO_CODEX_ENABLED=1`

### Presence and status

Virtual Office derives live presence from gateway/session activity. Use these
endpoints when an external adapter or broker needs to set an explicit visible
state that cannot be inferred automatically.

- `GET /api/presence`
- `GET /status`
- `POST /api/presence/<agentId>`

Allowed common states:

- `working`
- `idle`
- `break`
- `meeting`

### Browser control

Current safe read/status endpoints:

- `GET /browser-status`
- `GET /browser-tabs`
- `GET /browser-controller`

Important: agents should not use raw Kasm/CDP credentials directly. A provider-neutral browser action API should be added before non-OpenClaw agents are given direct browser control.

### Meetings

- `GET /api/meetings/active`
- `GET /api/meetings/history`
- `POST /api/meetings/create`
- `POST /api/meetings/end`
- `POST /api/meetings/end-all`

Meetings should always end with a summary/resolution/action items.

Executable Meeting for AI routes:

- `POST /api/meetings/executable/create`
- `GET /api/meetings/executable/<meetingId>`
- `GET /api/meetings/executable/<meetingId>/events?afterSeq=<seq>`
- `POST /api/meetings/executable/<meetingId>/run`
- `POST /api/meetings/executable/<meetingId>/transition`
- `POST /api/meetings/executable/<meetingId>/intervention`
- `POST /api/meetings/executable/<meetingId>/agenda-change`
- `POST /api/meetings/executable/<meetingId>/targeted-question`
- `POST /api/meetings/executable/<meetingId>/arbitration`
- `POST /api/meetings/executable/<meetingId>/moderator-takeover`
- `POST /api/meetings/executable/<meetingId>/conflict`
- `POST /api/meetings/executable/<meetingId>/action-items/<actionItemId>`
- `GET /api/meetings/executable/reconcile`

Supported meeting types are information gathering, decision discussion, and task collaboration. Executable meetings persist participants, stage, round state, transcript events, selected context snapshots, structured results, conflict state, and action-item drafts under the office meeting store.

AI-originated meeting request routes:

- `GET /api/meetings/requests`
- `GET /api/meetings/requests/<requestId>`
- `POST /api/meetings/requests/<requestId>/confirm`
- `POST /api/meetings/requests/<requestId>/reject`
- `GET /api/projects/<projectId>/tasks/<taskId>/meeting-requests`
- `POST /api/projects/<projectId>/tasks/<taskId>/meeting-requests`

Meeting requests are for project-task collaboration blockers. A valid request must explain the meeting goal, expected outcome, why the requester cannot complete alone, suggested participants, and suggested meeting type. Pending requests never reserve participants or call meeting providers; only user-confirmed requests become executable meetings.

Conflict handling uses `POST /api/meetings/executable/<meetingId>/conflict` with actions such as `wait`, `reserve`, `replace`, `force_join`, `cancel_conflict`, and `refresh`. Medium/high-risk conflicts can include a busy-agent advisory recommendation, estimated availability, interruption risk, and resume notes. Advisory output is read-only; the user or caller must still choose a resolution.

Task-collaboration meeting results can expose action-item drafts. `POST /api/meetings/executable/<meetingId>/action-items/<actionItemId>` supports user-controlled draft update, rejection, meeting-only retention, and confirmation into a project task. Confirmation is idempotent and stores source meeting/action-item metadata on the created task.

### Projects and tasks

- `GET /api/projects`
- `GET /api/projects/<projectId>`
- `POST /api/projects`
- `POST /api/projects/<projectId>/tasks`
- `PUT /api/projects/<projectId>/tasks/<taskId>`
- `GET /api/projects/<projectId>/workflow/status`
- `POST /api/projects/<projectId>/workflow/start`
- `POST /api/projects/<projectId>/workflow/stop`
- `GET /api/projects/scores`

Use these for durable work that belongs on a board.

Project execution endpoints are available for assigning board work to provider-backed agents and tracking review/acceptance state:

- `POST /api/projects/<projectId>/project-execution/workspace/validate`
- `POST /api/projects/<projectId>/project-execution/start`
- `GET /api/projects/<projectId>/project-execution/status`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/cancel`
- `GET /api/projects/<projectId>/tasks/<taskId>/project-execution/status`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/review/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/accept`
- `GET /api/projects/<projectId>/artifacts`
- `GET /api/projects/<projectId>/artifacts/read?path=<relativePath>`

Project execution currently supports OpenClaw, Hermes, and Codex provider refs, independent reviewer routing, dirty-workspace confirmation, reviewer-skip confirmation, cancellation, acceptance/rejection/blocking, and markdown artifact discovery.

Project-bound scheduled cron endpoints connect the Gateway cron scheduler to project execution:

- `GET /api/projects/scheduled-cron`
- `GET /api/projects/<projectId>/scheduled-cron`
- `POST /api/projects/<projectId>/scheduled-cron`
- `PUT /api/projects/<projectId>/scheduled-cron/<cronId>`
- `DELETE /api/projects/<projectId>/scheduled-cron/<cronId>`
- `POST /api/projects/<projectId>/scheduled-cron/<cronId>/run`

Virtual Office owns the project binding metadata in `VO_STATUS_DIR/project-cron-bindings.json`; the OpenClaw Gateway owns the underlying cron job. Supported targets are `projectWorkflow` and `projectTask`. Supported schedules are `cron`, `every`, and one-shot `at`.

Dispatch may skip instead of starting execution when a project is archived, project cron is paused, another task is active, a target task is missing, a completed task has not enabled scheduled repeat, or a dirty workspace / missing reviewer confirmation is required. These outcomes are recorded in project scheduled-cron history and surfaced as project alerts when human intervention is needed.

### Codex harness

When `VO_CODEX_ENABLED=1`, the Codex harness is exposed as an office agent and can be used through both chat and project execution.

- `GET /api/codex/test`
- `POST /api/codex/chat`
- `GET /api/codex/activity`
- `GET /api/codex/history`
- `POST /api/codex/interaction`
- `POST /api/codex/cancel`
- `POST /api/codex/compact`
- `POST /api/codex/reset`

The live bridge uses local `codex app-server` by default, or an external bridge when `VO_CODEX_BRIDGE_URL` is configured. `VO_CODEX_REPLY_TEXT=<text>` remains available for deterministic local regression tests.

## Organization rules

- Use this file as the canonical index.
- Use skill files for concise agent instructions.
- Use provider adapter docs for implementation details.
- Do not duplicate generic browser automation skills as Virtual Office browser skills. `agent-browser` is generic; `VirtualOffice-Browser-Control` is specifically for the office-owned browser surface.
- Future tools should add one section here and one built-in skill only if agents need direct instructions.

## Current gaps

- Provider-neutral browser action endpoint is not implemented yet.
- File/upload tool skill is not yet added; add it only after the intended agent-facing file endpoints are finalized.
- Calendar/scheduler skill is not yet added; add it only if Virtual Office owns those endpoints instead of delegating to OpenClaw/provider tools.
