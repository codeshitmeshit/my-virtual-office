# My Virtual Office Fork

> This is the optional English companion document. The primary README is Chinese: [README.md](README.md).

This repository is a second-development fork of the open-source project [eliautobot/my-virtual-office](https://github.com/eliautobot/my-virtual-office). It keeps the original pixel-art office idea and extends it into a local-first AI agent control surface for OpenClaw, Hermes, Codex, and other local agent runtimes or CLI harnesses.

Thanks to the original project author and community for the foundation. This fork is not an official upstream release. Upstream Docker images, product licensing, deployment instructions, and feature descriptions may not apply to this repository.

![My Virtual Office](screenshot.png)

## What This Fork Is

This fork is a local AI team console:

- Visualize agent presence and activity in a pixel-art office.
- Chat with OpenClaw, Hermes, and Codex agents from one UI.
- Route cross-platform agent communication through Virtual Office.
- Manage projects, tasks, reviews, acceptance, and artifacts.
- Observe Codex live bridge turns, reasoning, tool/file activity, approvals, cancellation, and compaction.
- Manage meetings, skills, agent workspaces, browser view, SMS, and local metrics.

## Implemented Areas

### Office Canvas

- Real-time pixel-art office canvas.
- Agent walking, idle, working, meeting, and break states.
- A* pathfinding, collision handling, and wall occlusion.
- Layout editor for furniture, walls, floors, branches, labels, and desks.
- Agent appearance, branch, desk, role, and emoji customization.
- Office pet, weather windows, day/night cycle, animated furniture, and clock.

### Provider Support

- OpenClaw remains a first-class provider through the existing gateway/session paths.
- Hermes profiles are discovered through the local Hermes CLI.
- Codex can be exposed as `codex-local` through the local Codex harness.
- Cross-provider communication is routed through `/api/agent-platform-communications/send`.
- Provider activity is normalized into the office agent list, presence state, chat bubbles, and logs.

### Codex Live Bridge

Set `VO_CODEX_ENABLED=1` to expose a local Codex collaborator.

Supported routes include:

- `POST /api/codex/chat`
- `GET /api/codex/activity`
- `GET /api/codex/history`
- `POST /api/codex/interaction`
- `POST /api/codex/cancel`
- `POST /api/codex/compact`
- `POST /api/codex/reset`

The default bridge uses local `codex app-server`. `VO_CODEX_BRIDGE_URL` can point to an externally managed bridge. `VO_CODEX_REPLY_TEXT` is available for deterministic regression/demo mode and does not exercise live tool execution.

### Projects And Task Execution

The project board supports durable project work:

- Projects, columns, tasks, comments, checklists, tags, and templates.
- Automatic or manual project workspace binding.
- System-managed project workspace root via `VO_AUTO_PROJECT_WORKSPACE_ROOT`.
- Manual workspace allow-listing via `VO_PROJECT_ROOTS`.
- Workspace validation and dirty-workspace confirmation.
- Project-level and task-level execution.
- Single-task and continuous project execution modes.
- OpenClaw, Hermes, and Codex provider routing.
- Separate executor and independent reviewer roles.
- Reviewer-skip confirmation when explicitly allowed.
- Cancellation, failure evidence, blocked states, review, rework, user acceptance, and rejection.
- Markdown artifact discovery and safe read endpoints.

See [docs/VIRTUAL_OFFICE_AGENT_TOOLS.md](docs/VIRTUAL_OFFICE_AGENT_TOOLS.md).

### Meetings

- Meeting creation, active state, history, and manual ending.
- Executable AI meetings with rounds, pause/resume/cancel, user intervention, agenda changes, targeted questions, arbitration, and moderator takeover.
- Information-gathering, decision-discussion, and task-collaboration meeting types.
- User-started meetings with participant, moderator, max-round, context mode, and optional project binding controls.
- AI-started meeting requests that require user review, editing, confirmation, or rejection before any meeting starts.
- Pre-meeting context candidates from the current project, source task, related same-project tasks, and prior same-project meetings; only user-selected context enters the immutable meeting snapshot.
- Busy-agent conflict detection with advisory recommendations, wait, replace, force-join second confirmation, and lightweight try-later handling.
- Original-work snapshots before joining and idempotent resume attempts after meeting completion, cancellation, or failure.
- Task-collaboration meetings can produce action-item drafts; confirmed drafts create project tasks with source meeting traceability.
- AI meeting requests with quality gates and urgency handling.
- Meeting state projection onto the office canvas.

Meeting for AI safety boundaries:

- Pending AI meeting requests do not occupy agents or call participant providers.
- Advisory turns are read-only recommendations and never pause work, replace participants, or force-start meetings by themselves.
- One agent can participate in only one executable meeting at a time.
- Meeting action items are not executed automatically; user confirmation is required before project tasks are created.

### Skills And Workspaces

- Central Skills Library for reusable `SKILL.md` files.
- Copy library skills into individual agent workspaces.
- Agent workspace panel with overview, bulletin, tasks, files, skills, notes, and settings.

### Optional Panels

- Chat with Markdown, attachments, image preview, and Codex reasoning summary.
- Browser panel for a shared browser/VNC view.
- SMS panel backed by Twilio.
- PC metrics panel.
- API usage panel.
- Models panel.
- Cron page for agent jobs and project-bound scheduled tasks.

### Project Scheduled Tasks

Project cron binding connects the global OpenClaw Gateway cron scheduler to Virtual Office projects:

- Start a full project workflow or a selected project task on a schedule.
- Supports `cron`, `every`, and one-shot `at` schedules.
- Gateway owns the cron job; Virtual Office owns the project binding metadata.
- Archived projects, paused project cron, already-active project execution, missing target tasks, and confirmation-required dispatches are skipped and recorded.
- Completed tasks do not repeat unless scheduled repeat is enabled on the task.
- Recent dispatch history and intervention alerts are shown on the project panel.

## Quick Start

This fork is designed for host-local startup.

```bash
git clone https://github.com/eliautobot/my-virtual-office.git
cd my-virtual-office
chmod +x start.sh
./start.sh
```

Open:

```text
http://localhost:8090/setup
```

Useful routes:

- Main app: `http://localhost:8090/`
- Setup: `http://localhost:8090/setup`
- Models: `http://localhost:8090/models`
- Cron: `http://localhost:8090/cron.html`
- Health: `http://localhost:8090/health`

## Docker Status

Direct Docker or Docker Compose startup is not the supported path for this fork. The current implementation depends heavily on host-local CLIs, workspaces, browser endpoints, OpenClaw/Hermes/Codex configuration, and filesystem permissions.

Docker files may remain from upstream or for reference, but they are not the supported deployment path for this fork.

## Configuration

Use `.env` or `vo-config.json`. Common variables:

| Variable | Purpose |
| --- | --- |
| `VO_PORT` | HTTP server port, default `8090` |
| `VO_WS_PORT` | WebSocket proxy port, default `8091` |
| `VO_STATUS_DIR` | Local state directory |
| `VO_OPENCLAW_PATH` | OpenClaw home path |
| `VO_GATEWAY_URL` | OpenClaw Gateway WebSocket URL |
| `VO_GATEWAY_HTTP` | OpenClaw Gateway HTTP URL |
| `VO_HERMES_ENABLED` | Enable Hermes profile discovery |
| `VO_HERMES_HOME` | Hermes home/profile root |
| `VO_HERMES_BIN` | Hermes CLI path |
| `VO_CODEX_ENABLED` | Enable Codex harness |
| `VO_CODEX_BIN` | Codex CLI path |
| `VO_CODEX_WORKSPACE` | Codex writable workspace |
| `VO_CODEX_MODEL` | Optional Codex model override |
| `VO_CODEX_BRIDGE_URL` | Optional external Codex bridge |
| `VO_BROWSER_PANEL` | Enable browser panel entry |
| `VO_CDP_URL` | Browser CDP endpoint |
| `VO_VIEWER_URL` | Browser viewer/VNC endpoint |
| `VO_AUTO_PROJECT_WORKSPACE_ROOT` | Root for system-managed project workspaces |
| `VO_PROJECT_ROOTS` | Path-separated allow-list for manual project workspaces |
| `VO_PC_METRICS_ENABLED` | Enable local metrics panel |
| `VO_API_USAGE` | Enable API usage panel |

See [.env.example](.env.example).

## Security

This is a high-privilege local control surface. It can connect local CLIs, read/write project workspaces, operate agents, show browser views, send SMS, and trigger model calls.

Recommended:

- Keep it on localhost, LAN, or a private network such as Tailscale.
- Do not expose `8090`, `8091`, OpenClaw Gateway, or CDP directly to the public internet.
- Use strong access control for machines that can reach the service.
- Choose project and Codex workspaces carefully.
- Treat dirty workspace confirmation, reviewer-skip confirmation, and user acceptance as real safety gates.

## Tests

Example commands:

```bash
npm test
.venv/bin/python tests/test_project_execution.py
.venv/bin/python tests/test_codex_bridge.py
.venv/bin/python tests/test_meeting_for_ai_phase1.py
.venv/bin/python tests/test_meeting_for_ai_phase4.py
.venv/bin/python tests/test_project_scheduled_cron_phase1.py
.venv/bin/python tests/test_project_scheduled_cron_phase2_3.py
.venv/bin/python tests/test_project_scheduled_cron_phase4.py
```

Exact commands depend on your local virtual environment and installed dependencies.

## Documentation

- [docs/VO_AGENT_USAGE_GUIDE.md](docs/VO_AGENT_USAGE_GUIDE.md)
- [docs/VIRTUAL_OFFICE_AGENT_TOOLS.md](docs/VIRTUAL_OFFICE_AGENT_TOOLS.md)
- [docs/AGENT_PLATFORM_COMMUNICATIONS.md](docs/AGENT_PLATFORM_COMMUNICATIONS.md)
- [docs/CODEX_PROVIDER_ADAPTER.md](docs/CODEX_PROVIDER_ADAPTER.md)
- [docs/HERMES_PROVIDER_ADAPTER.md](docs/HERMES_PROVIDER_ADAPTER.md)
- [docs/UNIVERSAL-AGENT-HARNESS-SPEC.md](docs/UNIVERSAL-AGENT-HARNESS-SPEC.md)
- [docs/SKILLS-LIBRARY-SPEC.md](docs/SKILLS-LIBRARY-SPEC.md)
- [docs/MULTI-CHAT-ARCHITECTURE.md](docs/MULTI-CHAT-ARCHITECTURE.md)

## Credits

This fork is based on [eliautobot/my-virtual-office](https://github.com/eliautobot/my-virtual-office). Thanks to the original author for the pixel office, agent visualization, and web app foundation.

This repository is not the official upstream release. Fork-specific features, docs, and integrations are maintained here. Refer to [LICENSE](LICENSE) and dependency/resource licenses for licensing details.

## License

MIT
