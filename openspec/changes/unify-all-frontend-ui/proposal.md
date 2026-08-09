## Why

Virtual Office currently exposes multiple independently styled frontend systems across the main office, management workflows, standalone tools, and the public website. The repository now has a canonical Figma system UI standard, so this change adopts that standard across every frontend surface while preserving the behavior and backend contracts that those surfaces already expose.

## What Changes

- Introduce one shared semantic frontend foundation for the canonical colors, typography hierarchy, spacing, radii, focus treatment, control states, and action tones defined by the Figma system UI standard.
- Standardize reusable buttons, navigation items, inputs, selects, toggles, cards, modal shells, dialogs, close controls, status badges, toasts, inline alerts, banners, and notification items.
- Migrate every repository-owned frontend surface, including current uncommitted frontend work, to the shared system: the main Virtual Office UI, chat and browser panels, settings, Agent Management, Human Resources, personal assets, meetings, projects and orchestration, archive room, human decisions, skills, MCP registry, standalone setup/models/cron pages, and the `website/` frontend.
- Preserve the office pixel-art scene as a domain visual asset while aligning its surrounding chrome, actions, overlays, dialogs, and feedback with the system standard.
- Preserve existing event handling, key DOM contracts, API calls, persistence timing, business states, and destructive-action behavior; this change does not redesign backend workflows.
- Add repeatable static, interaction, responsive, accessibility-state, and visual-regression checks for the migrated surfaces.
- No breaking backend, API, persistence, protocol, or data-format changes are introduced.

## Capabilities

### New Capabilities

- `frontend-ui-system`: Defines the canonical shared UI foundation, reusable component semantics, complete frontend-surface adoption, compatibility boundaries, and visual acceptance requirements.

### Modified Capabilities

- `project-task-orchestration`: Retains the approved orchestration workflow layout and interaction model while making the canonical system UI standard authoritative for global tokens, shared controls, icons, dialogs, action semantics, and feedback presentation.

## Impact

- Affected code is limited to repository-owned frontend HTML, CSS, frontend JavaScript rendering, and frontend-focused tests under `app/`, `website/`, and `tests/`.
- Existing in-progress frontend work, especially `redesign-settings-large-modal` and personal-assets UI changes, becomes part of the migration baseline and must not be overwritten or behaviorally reimplemented.
- Existing backend services, routes, request and response payloads, storage, configuration formats, provider behavior, SSE/WebSocket contracts, and business state machines remain unchanged.
- The canonical reference is Figma page `00 · SYSTEM UI STANDARD · AI START HERE` (`o6Crht2KV89peGoPpCAJsX`, node `356:240`). Existing feature-specific Figma frames remain authoritative for domain layout where they do not conflict with the canonical system standard.
