## Context

VO already has a durable project store, browser CRUD routes, `ProjectRepository`, extracted project command services, reusable project templates, task `assignee`/`executorAgentId`/`reviewerAgentId` fields, and Gateway-backed scheduled execution. It also has an established AI-request pattern for meetings: an Agent creates a non-materializing pending request, while a management-authenticated user confirms, edits, or rejects it.

The current `vo-project-workflow` skill intentionally covers execution rather than authoring. All `/api/projects` POST/PUT/DELETE mutations require the per-process management token, which an Agent skill must not receive or expose. Current project creation also creates an empty project before tasks are added, template cloning drops role details, and project cron starts existing work instead of generating independent project instances.

This change therefore spans runtime skills, HTTP routing, project-domain services, persistence, scheduling, and a small trusted user control surface. Existing local-first deployment and persisted projects must remain readable without a mandatory migration.

## Goals / Non-Goals

**Goals:**

- Let an Agent respond to an explicit user request by submitting a complete VO project draft without possessing management credentials.
- Require a trustworthy user confirmation before the first project mutation.
- Materialize a confirmed project and all initial tasks atomically and idempotently.
- Represent one responsible actor and one executor actor per task, while projecting compatible Agent roles into current execution fields.
- Keep reviewer absent by default and preserve existing reviewer-skip gates.
- Support strict and autonomous Agent-maintenance policies with a narrow protected boundary.
- Support versioned manual templates and scheduled creation of independent project instances.
- Preserve current project CRUD, execution, reviews, acceptance, and scheduled-execution behavior.

**Non-Goals:**

- Proactive project creation when the user did not ask for it.
- Replacing the Project Execution, review, acceptance, or existing cron workflow.
- Adding a general organization-wide human directory; the initial human actor is the current VO user identity.
- Automatic task execution immediately after project materialization unless separately requested through existing execution gates.
- Expanding the first release into reminders,催办, full project acceptance, or project-closing automation.

## Decisions

### 1. Add `vo-project-authoring` instead of expanding `vo-project-workflow`

The new skill owns project drafting, candidate recommendation, pending-request status, template instantiation, recurrence authoring, and policy-controlled maintenance. `vo-project-workflow` remains the execution/review/acceptance skill.

This preserves a clear safety boundary: authoring decides what durable work should exist, while execution decides how approved work runs. The VO skills index and catalog will route between them.

Alternative considered: add creation commands to `vo-project-workflow`. Rejected because its current description and safety gates are execution-specific, and mixing management-token-free authoring requests with execution commands would make both the skill and authorization boundary harder to audit.

### 2. Reuse the pending-request pattern and the project-store atomic boundary

Add a transport-independent `project_authoring` service, but persist its requests, idempotency records, approved grants, versioned templates, recurrence definitions, and recurrence outbox alongside `projects` under the existing project-store root. `MarkdownProjectStore` must be extended to round-trip these bounded root collections; storing them in a second file would make a draft transition and project creation impossible to commit atomically.

The Agent-facing endpoint can submit and read its sanitized pending drafts but cannot materialize a project. Management-authenticated endpoints allow the user control surface to edit, confirm, or reject. The request state machine is:

```text
pending -> materializing -> confirmed
   |            |
   |            +-> failed -> materializing (retry)
   +-> rejected
```

Every edit increments a request revision. Confirmation supplies the expected revision and uses a compare-and-set transition to `materializing`, preventing two browser actions from materializing different snapshots. It then validates actors and schedule data, prepares a workspace outside the repository lock, and performs one `update_root` commit containing the complete project aggregate, approved snapshot, confirmed request state, idempotency record, versioned-template changes, recurrence definition, and durable recurrence-registration outbox intent. A stable confirmation idempotency key maps the draft to exactly one project. Failed workspace preparation is cleaned up before the commit; a failed root commit also cleans up an uncommitted system-managed workspace.

Gateway recurrence registration is not performed synchronously inside confirmation. A bounded reconciler consumes the durable outbox after commit, registers or repairs the Gateway job idempotently, and records success or an intervention alert. This avoids pretending a local file commit and an external Gateway call are one transaction while ensuring the confirmed recurrence intent is never lost.

Alternative considered: let the skill call existing project CRUD with the management token after conversational confirmation. Rejected because it would expose a high-authority browser credential to arbitrary Agent execution and the backend could not distinguish a genuine user confirmation from an Agent assertion.

### 3. Add explicit actor references with compatibility projections

New authored tasks persist:

```json
{
  "responsibleActor": {"type": "user|agent", "id": "..."},
  "executorActor": {"type": "user|agent", "id": "..."},
  "reviewerActor": null
}
```

For an Agent executor, `executorAgentId` is populated for existing Project Execution. For an Agent responsible actor, `assignee` is populated for existing UI, score, and workload projections. The current VO user actor is valid for tracking-only human work; a human executor cannot start automated Project Execution until an Agent executor is assigned. Legacy tasks without actor references are read through a compatibility adapter derived from `assignee`, `executorAgentId`, and `reviewerAgentId`.

Alternative considered: reinterpret `assignee` as the new owner field and leave all roles as untyped strings. Rejected because it cannot safely distinguish the current user from an Agent and would make execution eligibility ambiguous.

### 4. Persist maintenance mode and protect structural mutations

Projects authored through this flow store `agentMaintenanceMode` and their approved requesting Agent. In strict mode, every Agent-originated management mutation becomes a pending maintenance request. In autonomous mode, only routine fields—task state, description, checklist, evidence, and due date—can be directly changed by an assigned Agent. Task creation/deletion, role or reviewer changes, recurrence changes, archive/delete, workspace changes, and maintenance-mode changes always require management-authenticated confirmation.

Existing execution-service transitions are not reclassified as authoring mutations and continue to follow their current gates.

Alternative considered: let autonomous mode use all current project PUT/POST routes. Rejected because those routes include destructive and authority-changing operations that exceed the user's approval of routine autonomous maintenance.

### 5. Version templates and instantiate from immutable snapshots

Extend user templates with a stable template id and append-only versions. Each version contains columns, complete task blueprints, actor references, reviewer policy, maintenance mode, and execution settings. Manual and recurring instantiation records the exact template version. Editing a template creates a new version rather than changing old snapshots.

Legacy templates remain readable as implicit version 1 and continue through the old browser route until explicitly upgraded. New authoring flows use the versioned service path.

Alternative considered: clone the latest mutable template at dispatch time. Rejected because edits would silently alter already-approved recurring work and make historical instances irreproducible.

### 6. Add a recurrence target that materializes projects

Reuse current schedule validation and Gateway cron integration, but introduce a distinct target kind such as `projectTemplateInstance`. Its binding records recurrence id, template id/version, requesting Agent, pause state, last status, and bounded occurrence history. The outbox reconciler registers the Gateway job with an idempotency key derived from the recurrence id and can safely repair missing bindings after restart.

A due callback performs an atomic root claim keyed by `(recurrenceId, occurrenceId)`, validates the immutable template actors, prepares any workspace outside the lock, and commits one complete project plus the occurrence result in a second compare-and-set root update. Other callbacks observe `claimed`, `created`, or `failed` rather than creating another instance. Claims have a configurable expiry and owner token so restart recovery can retry abandoned work without stealing a live dispatch. Failed workspace preparation releases the claim with retryable failure metadata; failed commits clean up uncommitted system-managed workspaces.

This path does not invoke current project/task execution starts. Existing `projectWorkflow` and `projectTask` target kinds remain unchanged.

Alternative considered: reset or reopen tasks in one long-lived project. Rejected because the confirmed product model requires independently traceable project instances and future-only template changes.

### 7. Activate a scoped project grant only after trusted confirmation

Draft submission follows the existing local Agent-request threat model: the endpoint is loopback-only, rejects browser `Origin` requests, requires bounded JSON plus an Agent-action header, validates a registered non-excluded requesting Agent, and performs no project mutation. It returns a random request secret and stores only its hash. Pending requests are capped per Agent and globally, and idempotency prevents retries from filling the queue.

When the user confirms the draft, the existing request secret becomes a revocable project grant bound to the created project, requesting Agent, approved maintenance mode, allowed operations, and grant version. The Agent supplies the bearer secret only to the Agent status and maintenance endpoints; the backend compares its hash and never returns or logs the secret again. Strict mode permits only status reads and maintenance-request submission. Autonomous mode additionally permits the explicit routine-update allowlist for tasks to which that Agent is assigned. Protected confirmation and structural changes retain the management-token gate. Revoking or rotating the grant immediately invalidates the old hash.

All Agent endpoints deny permissive CORS, all management endpoints keep the current management-token check, and all audit views redact secret material. This creates provider-neutral scoped authority without distributing the browser management token or trusting an arbitrary `requestingAgentId` field after confirmation.

Alternative considered: validate only the Agent id in the request body. Rejected because any local caller could impersonate an assigned Agent and exploit autonomous maintenance. Alternative considered: provision a reusable high-authority Agent token across all providers. Rejected because provider credential delivery is not uniform and the authority would be broader than one confirmed project.

### 8. Add a minimal management-authenticated review surface

The project UI gains a pending Agent project drafts view with edit, confirm, and reject actions. This is necessary because confirmation must be trustworthy and the management token is currently held only by the browser control surface. The skill polls the sanitized request status and reports the resulting project id after confirmation.

Alternative considered: treat a chat response as sufficient backend authorization. Rejected because the generic skill/API layer has no provider-neutral signed proof that a particular message came from the user.

### 9. Use additive versioned HTTP contracts

Add separate routes rather than weakening existing `/api/projects` management-token protection:

- `POST /api/agent/project-drafts` and `GET /api/agent/project-drafts/{id}` for low-authority Agent submission/status.
- `POST /api/agent/projects/{projectId}/maintenance` for scoped-grant maintenance.
- `GET /api/project-drafts`, `GET /api/project-drafts/{id}`, and management-authenticated edit/confirm/reject routes for the user control surface.
- Management-authenticated recurrence pause/resume and grant revoke/rotate routes.

Agent responses expose only the caller's sanitized request/project result. Management responses may expose the full original and approved snapshots but never the request secret hash. All mutating calls accept an idempotency key and optimistic revision where applicable. Existing route paths, payloads, status codes, CORS behavior, and management checks remain unchanged.

### 10. Bound capacity and persistence cost

Defaults are configurable but conservative: 64 KiB request bodies, at most 100 initial tasks per draft, at most 20 pending drafts per Agent, at most 500 pending drafts globally, at most 20 open maintenance requests per project, 100 audit events per request/project, and 100 occurrence records per recurrence. Terminal drafts older than 30 days are compacted during an off-path maintenance pass, retaining a tombstone with identifiers and final result. The authoring list APIs use indexed root maps and bounded summaries rather than scanning task files.

The outbox reconciler has a feature-configured worker count, batch size, retry backoff, and maximum attempts. Queue-full conditions reject new work with stable `429` or `503` errors without affecting existing project reads or execution. Configuration is read at process start for limits and worker sizing; feature-enable and dispatch-pause flags are checked on every relevant action.

### 11. Add feature flags, observability, and rollback controls

`VO_AGENT_PROJECT_AUTHORING_ENABLED` gates new draft submission and autonomous maintenance; `VO_PROJECT_INSTANCE_RECURRENCE_ENABLED` gates new recurrence registration and dispatch. Both default off during rollout. Disabling authoring stops new drafts and direct autonomous mutations but leaves management access to existing requests. Disabling recurrence stops new registrations and instance dispatch while preserving durable intents for later reconciliation.

Structured counters and duration measurements cover draft submitted/rejected/confirmed/failed, confirmation conflicts, grant failures, autonomous updates, outbox depth/age/retries, recurrence claims/duplicates/created/failed, workspace cleanup failures, and materialization latency. Logs are rate-limited by request/recurrence key, and the control surface displays pending depth and intervention alerts. Health reporting distinguishes disabled, idle, queued, processing, failed, and reconciled states.

## Risks / Trade-offs

- [The change is broader than a skill-only update] → Keep the first release focused on one draft flow, one minimal review surface, and additive compatibility fields; reuse project commands, repository, and scheduler primitives.
- [Workspace creation and Gateway registration are external side effects around an atomic project commit] → Prepare and clean up workspaces around compare-and-set commits; persist recurrence intents in an outbox and reconcile Gateway state idempotently outside the commit.
- [Legacy `assignee` semantics may diverge from new responsible actors] → Centralize actor projection and compatibility reads; keep existing fields populated for Agent-backed roles and add regression coverage.
- [A pending-request endpoint can be spammed by a local process] → Require loopback/no-Origin access, enforce registered Agent validation, body/rate/global pending limits, idempotency, bounded retention, and no materializing side effects.
- [A confirmed Agent secret can leak from tool output or logs] → Return it only at draft creation, store only its hash, prohibit echoing it in skill output, redact authorization headers, support revocation/rotation, and scope it to one project.
- [Autonomous maintenance can still make unwanted routine changes] → Require the scoped grant and task assignment, use a strict field allowlist, retain bounded audit/history, and make strict mode available per project.
- [Recurring actor assignments can become stale] → Revalidate every occurrence, fail without partial creation, and surface an intervention alert rather than silently substituting another actor.
- [Template versioning complicates the existing flat template schema] → Treat legacy templates as implicit v1 and add an adapter; do not rewrite existing project records during rollout.

## Migration Plan

1. Extend the project store to round-trip bounded authoring metadata and add actor-reference compatibility helpers without changing existing route behavior.
2. Add project-authoring services, request-secret hashing, and unit tests for validation, atomic materialization, idempotency, and legacy projections behind disabled feature flags.
3. Add Agent draft/status endpoints and management-authenticated edit/confirm/reject endpoints behind additive routes; keep authoring disabled by default.
4. Add versioned template instantiation, durable recurrence outbox, reconciler, and the independent-project recurrence target while leaving existing cron target kinds unchanged.
5. Add the minimal pending-draft control surface and runtime skill routing, then enable authoring for local test instances only.
6. Observe request conflicts, grant failures, outbox age, recurrence duplicates/failures, cleanup failures, and latency before enabling recurrence.
7. Run project command, persistence, management-token, Project Execution, template, scheduler, security, capacity, observability, and UI regression suites before broader enablement.

Rollback first disables both feature flags and pauses the recurrence reconciler, then removes skill routing if needed. Created projects remain ordinary backward-readable projects. Pending requests, grants, outbox intents, versioned templates, and recurrence bindings remain inert data; existing project APIs ignore additive fields. Code rollback is safe only after flags are off and outbox depth is stable at zero or explicitly accepted as inert.

## Open Questions

- Should the current VO user actor use a fixed local identifier or an existing profile identifier if VO later supports multiple human users? The first release can use a stable `user:local` identity behind an adapter.
- Should confirmed project drafts appear in the existing meeting-request-style sidebar queue or a dedicated Projects queue? This affects UI placement but not the backend contract.
- Should the request secret be stored by provider adapters for session recovery, or should a lost secret always require management-authenticated grant rotation? The safe first release requires rotation.
