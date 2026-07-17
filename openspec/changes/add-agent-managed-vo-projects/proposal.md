## Why

Virtual Office already supports user-managed projects, tasks, templates, execution roles, reviews, and scheduled execution, but an Agent cannot safely author a complete project through the current runtime skills. Project mutations require the browser management token, creation is split across multiple non-atomic calls, and the existing scheduler reruns work inside one project instead of creating independently traceable recurring project instances.

## What Changes

- Add a dedicated VO project-authoring skill, separate from the existing execution-focused `vo-project-workflow` skill, for explicit user-requested project drafting and maintenance.
- Add a persisted Agent project-draft request flow: an Agent submits a complete draft, the user reviews or edits it through a trusted VO control surface, and confirmation atomically materializes the project and all tasks.
- Add explicit task responsibility semantics for one responsible owner and one executor, allowing the same supported actor to hold both roles, while keeping reviewer optional by default.
- Add reviewer recommendation metadata for high-risk, cross-team, or critical-delivery tasks without allowing the Agent to self-confirm the reviewer.
- Add project maintenance modes (`strict_confirmation` and `autonomous`) and enforce their mutation boundaries for Agent-originated changes.
- Extend reusable project templates so future instances preserve the confirmed task structure, responsibility rules, reviewer policy, and maintenance mode.
- Add recurring project definitions that create independent project instances on each due occurrence; template updates affect only future instances.
- Add idempotency, actor validation, audit history, status polling, and failure reporting for Agent-originated draft, confirmation, maintenance, and recurring-instantiation operations.
- Preserve existing browser project CRUD, Project Execution, review, acceptance, and scheduled execution behavior.

## Capabilities

### New Capabilities

- `agent-project-authoring`: Agent-drafted VO project creation, trusted user confirmation, task role assignment, optional reviewer recommendation, controlled maintenance, reusable templates, and independent recurring project instances.

### Modified Capabilities

None. Existing project execution service-boundary requirements remain compatible and unchanged.

## Impact

- Runtime skills and routing: `skills/vo-project-authoring`, `skills/vo-operating-guidelines`, and `skills/catalog.md`.
- Backend project domain: project commands/repository, a new project-authoring request service/store, template conversion, and recurring project instantiation.
- HTTP/control surface: Agent-safe draft submission and status APIs plus management-authenticated user confirm/edit/reject APIs.
- Persisted project/task records: responsibility actor references, maintenance mode, source draft/template/recurrence traceability, reviewer recommendation metadata, and audit data with backward-compatible defaults.
- Scheduler integration: reuse schedule validation and dispatch primitives where possible, but materialize a new project per occurrence instead of starting an existing project workflow.
- User control surface: pending draft review/edit/confirm/reject visibility is required so confirmation is trustworthy and does not expose the management token to an Agent.
- Tests and docs: command, persistence, authorization, idempotency, recurrence, compatibility, skill routing, and end-to-end confirmation coverage.
