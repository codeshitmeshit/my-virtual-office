# VO Conversation-Confirmed Project Authoring

This document defines the Agent and operational contract for direct Virtual Office project creation. Project Execution, review, acceptance, cancellation, and artifacts remain separate under `/skills/vo-project-workflow/SKILL.md`.

## Product contract

The Agent presents a complete natural-language proposal in the conversation. The proposal identifies project type, tasks, responsible and executor actors, optional reviewer decisions, maintenance mode, and template/recurrence settings. The Agent waits for explicit confirmation of that exact version, computes its SHA-256 digest, and calls the direct-create API.

No backend draft is created. If the user changes any semantic field, the Agent presents the complete revised proposal and waits again. If the user does not confirm, no API call occurs.

The backend cannot cryptographically verify provider-neutral chat authorship. `confirmation.confirmed=true` is an Agent assertion audited with the proposal digest. This accepted limitation is bounded by loopback-only registered-Agent access, atomic idempotent creation, and project-scoped authority. Ordinary creation never starts Project Execution; a recurring occurrence starts automatically only when the separately displayed `create_and_execute` mode was confirmed.

## Project Execution creation semantics

Future Agent-created projects default to `projectExecutionEnabled=true`. Enabled means the project is capable of using Project Execution; it does not mean execution has started. Immediately after ordinary creation, `projectExecutionFlowActive=false` and `workflowActive=false`. The user must explicitly request project-level execution later.

The confirmation proposal always displays execution enabled/disabled, executor, reviewer or absence, start mode, and whether creation starts execution. An explicit tracking-only request sets `projectExecutionEnabled=false`; it does not prepare an executable workspace and may use human-only task executors. Omission is not tracking-only.

Enabled creation fails closed before commit when an executor is missing/unassignable or the workspace cannot be prepared. It never silently creates a legacy or tracking-only project. A failed attempt leaves no partial Project, and a system-managed workspace created only for that failed attempt is eligible for cleanup.

## Rollout and security

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `VO_AGENT_PROJECT_AUTHORING_ENABLED` | `false` | Gate direct creation and Agent maintenance |
| `VO_PROJECT_INSTANCE_RECURRENCE_ENABLED` | `false` | Gate recurrence intent and occurrence dispatch |
| `VO_PROJECT_INSTANCE_RECURRENCE_DISPATCH_PAUSED` | `false` | Pause dispatch without deleting durable intent |

Agent routes require loopback, no browser `Origin`, `X-VO-Agent-Action: project-authoring`, and a registered `X-VO-Agent-Id`. Agents must never acquire `X-VO-Management-Token`. Management authentication remains required for protected maintenance confirmation, grant rotation/revocation, template instantiation, recurrence pause/resume, health, and existing project CRUD. User-confirmed Agent maintenance and Agent-created project scheduled cron use dedicated `/api/agent/...` routes instead of the management-token surface.

## Direct-create API

`POST /api/agent/project-authoring/projects` accepts:

```json
{
  "idempotencyKey": "agent:project:stable-key",
  "confirmation": {
    "confirmed": true,
    "summaryDigest": "64 lowercase SHA-256 hex characters",
    "summaryText": "exact Markdown proposal confirmed by the user"
  },
  "project": {
    "title": "Release preparation",
    "projectType": "one_time",
    "agentMaintenanceMode": "strict_confirmation",
    "projectExecutionEnabled": true,
    "projectExecutionStartMode": "continuous",
    "columns": [{"id": "backlog", "title": "Backlog"}],
    "tasks": [{
      "title": "Prepare release evidence",
      "columnId": "backlog",
      "responsibleActor": {"type": "agent", "id": "owner"},
      "executorActor": {"type": "agent", "id": "builder"},
      "reviewerRecommendation": {"recommended": false, "triggers": []},
      "checklist": [{"text": "Release evidence is complete", "done": false}]
    }],
    "template": {"mode": "none"},
    "recurrence": {"enabled": false}
  }
}
```

Every task has one responsible actor and one executor actor; they may be the same. `user:local` work is trackable but cannot start automated execution. Reviewer is absent by default. A `reviewerActor` is included only when the confirmed proposal explicitly assigns it; risk recommendations alone do not assign authority.

The server rejects direct creation unless `confirmation.summaryText` contains the fixed VO project confirmation template and `confirmation.summaryDigest` equals the SHA-256 digest of that exact UTF-8 text. This does not cryptographically prove chat authorship, but it prevents bare `confirmed=true` requests and makes the Agent submit the same full proposal it claims the user confirmed.

The atomic commit contains the project, tasks, actor projections, authoring source/digest, optional immutable template version, recurrence definition, and outbox intent as applicable. Reusable is a project attribute and does not require a template. Legacy grant metadata may be stored for backward-compatible recurrence dispatch and administration, but project maintenance is authorized by explicit user-confirmed maintenance proposals. Tasks start in `backlog`; `workflowActive` and `projectExecutionFlowActive` are false.

Idempotency is scoped to Agent and key. Same key and semantic payload returns the original project. Same key with changed project or proposal digest returns `project_creation_idempotency_conflict`. Workspace or commit failure leaves no partial project.

If a response includes `projectGrantSecret`, callers must treat it as legacy compatibility data: do not log, cache, display, or use it for normal project maintenance. Idempotent retries return the project without a new secret.

## Maintenance and recurrence

| Method and path | Contract |
| --- | --- |
| `POST /api/agent/projects/{projectId}/maintenance` | Apply a protected maintenance mutation after a fixed-template user confirmation, or use a legacy autonomous routine update with an existing grant |
| `POST /api/agent/projects/{projectId}/scheduled-cron` | Create a project scheduled cron after a fixed-template user confirmation; no management token is required |
| `POST /api/agent/project-recurrences/{recurrenceId}/occurrences` | Idempotently materialize one independent occurrence |
| `POST /api/project-authoring/projects/{projectId}/maintenance/{id}/confirm|reject` | Management decision for protected maintenance |
| `POST /api/project-authoring/projects/{projectId}/grant/rotate|revoke` | Management grant administration |
| `POST /api/project-authoring/recurrences/{recurrenceId}/pause|resume` | Management recurrence administration |
| `GET /api/project-authoring/health` | Credential-safe metrics, outbox age, and intervention alerts |

Maintenance requests without a grant must include `confirmation.confirmed=true`, the fixed maintenance confirmation `summaryText`, and a matching SHA-256 `summaryDigest`; the mutation is applied immediately after that confirmation contract is validated. Legacy `autonomous` grant calls directly permit only assigned-task `executionState`, `description`, `checklist`, `evidence`, and `dueDate`. Structural, role, reviewer, recurrence, workspace, archive/delete, mode changes, and project scheduled cron creation always require user confirmation.

Protected maintenance requests use `expectedRevision` for optimistic concurrency and a one-time `confirmationKey` for the management decision. An autonomous assigned-task change uses the `routine_task_update` operation; it cannot widen the allowed field set or change project structure.

Recurring project-template occurrences pin immutable `templateId,version` pairs and record a `projectTemplateInstance` projection. Reusable projects may have no template at all. Every recurrence stores one confirmed execution mode:

- `create_only` (default and historical compatibility): create one execution-capable but unstarted Project. The user starts it explicitly later.
- `create_and_execute`: atomically create the Project and a durable per-occurrence automatic-execution intent, then call the existing project-level start entry point after commit.

A due recurrence uses an expiring occurrence claim and compare-and-set commit keyed by `occurrenceId`. Duplicate or restarted callbacks return the same Project. Automatic start uses a separate expiring launch claim, so repeated or concurrent callbacks do not establish duplicate active attempts. Intent states are `pending`, `started`, `failed_retryable`, or `intervention_required`; bounded history and sanitized status counters make crash recovery observable without storing provider output or credentials. A retryable start failure never rolls back or duplicates the committed Project. An already active/completed Project is reconciled as started without another launch.

Agent project scheduled-cron creation is idempotent by Agent and key; it saves and enables a VO project-level scheduled configuration without asking for a management token. Scheduled project runs reuse the existing Project Execution start path (`projectWorkflow` or `projectTask`) when triggered; Gateway registration is an implementation detail and should not be exposed as a user prerequisite.

## Legacy draft compatibility

The previous request/status/edit/confirm/reject routes and draft review UI are removed. Previously persisted `projectAuthoringRequests` records remain inert compatibility metadata: they are readable by the store, not exposed as active work, not counted in health, not automatically materialized, and not deleted by this change.

## Failure and recovery runbook

1. **Feature disabled (`503`)**: enable direct authoring locally first; enable recurrence only after direct-create health is clean. Disabling recurrence stops new occurrence creation and automatic-start reconciliation; it does not cancel a Project that already started.
2. **Validation (`400`/`409`)**: refresh `/api/agents`. Missing/unassignable executors, invalid execution policy, and workspace preparation failures must be corrected; never retry by changing the request to tracking-only unless the user explicitly confirms that semantic change. Present a revised proposal and use a new key when semantics change.
3. **Idempotency conflict (`409`)**: do not overwrite the original result. Use a new key only after a newly confirmed semantic proposal.
4. **Workspace/commit failure**: managed uncommitted workspaces are cleaned; retry the unchanged confirmation with the same key.
5. **Lost first response**: locate the real project; do not recreate it. Rotate the grant through the trusted management surface.
6. **Revoked/cross-scope grant (`403`)**: stop Agent mutation; never reuse another project or Agent's secret.
7. **Outbox/scheduler failure**: pause dispatch, preserve durable intent, repair the scheduler dependency, then resume bounded reconciliation. Do not ask users to handle Gateway registration for ordinary VO project scheduled runs.
8. **Automatic-start failure**: leave the occurrence Project in place. Retry `failed_retryable` with the same occurrence; correct `intervention_required` through a confirmed executor/workspace/template change. Never create a replacement occurrence to force execution.
9. **Invalid recurrence actor**: retain the intervention alert; use a user-confirmed template/role correction rather than silent substitution.
10. **Rollback**: set `VO_AGENT_PROJECT_AUTHORING_ENABLED=false`, set `VO_PROJECT_INSTANCE_RECURRENCE_DISPATCH_PAUSED=true`, let in-flight atomic writes finish, and preserve root metadata. Then deploy the previous compatible code and verify ordinary Project/template/legacy cron reads. New canonical Project fields are backward-readable; additive recurrence `executionMode`/`executionIntent` fields may remain inert under old code. Stop an already running Project through existing Project Execution controls rather than deleting it.

Health is `disabled`, `healthy`, `paused`, `degraded`, or `intervention_required`. Recurrence outbox age of fifteen minutes degrades health; legacy pending draft age does not. Process-local counters reset on restart, while durable outbox and intervention state reconstruct operational health.
