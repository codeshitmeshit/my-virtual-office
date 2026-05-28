# Virtual Office Agent Tools

Status: canonical agent-facing tool index  
Scope: My Virtual Office Product / 8090

## Purpose

This document is the organized index for tools that agents can use through My Virtual Office. It avoids duplicate scattered instructions and points every platform toward the same office-owned surfaces.

The companion architecture document is `docs/UNIVERSAL-AGENT-HARNESS-SPEC.md`.

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

### AgentPlatform-to-AgentPlatform Communications

Use when agents need to talk across providers and the exchange should be visible in Virtual Office.

- `POST /api/agent-platform-communications/send`
- `GET /api/agent-platform-communications/history`

Events are stored in:

- `VO_STATUS_DIR/agent-platform-communications.jsonl`

These events are merged into `/agent-chat`, so chat bubbles can show cross-platform interactions.

### Presence and status

Use when an agent starts/stops visible work.

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
