## Why

Virtual Office already supports user-managed projects, tasks, templates, execution roles, reviews, and scheduled execution, but an Agent cannot safely author a complete project through the current runtime skills. Project mutations require the browser management token, creation is split across multiple non-atomic calls, and the existing scheduler reruns work inside one project instead of creating independently traceable recurring project instances.

## What Changes

- Add a dedicated VO project-authoring skill, separate from the existing execution-focused `vo-project-workflow` skill, for explicit user-requested project planning, creation, and maintenance.
- Keep the project proposal in the conversation as a natural-language summary. After the user explicitly confirms that summary, the Agent submits one complete structured create request that atomically creates the real project and all tasks; no backend draft or draft-review control surface is required.
- Add explicit task responsibility semantics for one responsible owner and one executor, allowing the same supported actor to hold both roles, while keeping reviewer optional by default.
- Recommend reviewers in the natural-language proposal for high-risk, cross-team, or critical-delivery tasks, while keeping the created task reviewerless by default unless the user explicitly confirms an assignment.
- Add project maintenance modes (`strict_confirmation` and `autonomous`) and enforce their mutation boundaries for Agent-originated changes.
- Extend reusable project templates so future instances preserve the confirmed task structure, responsibility rules, reviewer policy, and maintenance mode.
- Add recurring project definitions that create independent project instances on each due occurrence; template updates affect only future instances.
- Add idempotency, actor validation, audit history, direct-create failure reporting, scoped grants, and recurrence failure reporting for Agent-originated creation, maintenance, and recurring-instantiation operations.
- Preserve existing browser project CRUD, Project Execution, review, acceptance, and scheduled execution behavior.

## Capabilities

### New Capabilities

- `agent-project-authoring`: Conversation-confirmed direct VO project creation, task role assignment, optional reviewer recommendation, controlled maintenance, reusable templates, and independent recurring project instances.

### Modified Capabilities

None. Existing project execution service-boundary requirements remain compatible and unchanged.

## Impact

- Runtime skills and routing: `skills/vo-project-authoring`, `skills/vo-operating-guidelines`, and `skills/catalog.md`.
- Backend project domain: project commands/repository, an Agent direct-create service, template conversion, and recurring project instantiation; persisted draft-request state is not part of the product model.
- HTTP/control surface: one Agent-safe, idempotent direct-create API plus scoped maintenance APIs; the user confirms the natural-language proposal in the conversation rather than a backend draft UI.
- Persisted project/task records: responsibility actor references, maintenance mode, authoring/template/recurrence traceability, reviewer policy metadata, and audit data with backward-compatible defaults.
- Scheduler integration: reuse schedule validation and dispatch primitives where possible, but materialize a new project per occurrence instead of starting an existing project workflow.
- User control surface: no pending-draft management page is required. The real project appears after conversational confirmation and remains unstarted until a separate Project Execution action.
- Tests and docs: command, persistence, authorization, conversational-confirmation contract, idempotency, recurrence, compatibility, skill routing, and direct-create end-to-end coverage.
