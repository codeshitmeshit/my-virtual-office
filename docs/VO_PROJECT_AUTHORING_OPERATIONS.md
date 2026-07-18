# VO Conversation-Confirmed Project Authoring

This document defines the Agent and operational contract for direct Virtual Office project creation. Project Execution, review, acceptance, cancellation, and artifacts remain separate under `/skills/vo-project-workflow/SKILL.md`.

## Product contract

The Agent presents a complete natural-language proposal in the conversation. The proposal identifies project type, tasks, responsible and executor actors, optional reviewer decisions, maintenance mode, and template/recurrence settings. The Agent waits for explicit confirmation of that exact version, computes its SHA-256 digest, and calls the direct-create API.

No backend draft is created. If the user changes any semantic field, the Agent presents the complete revised proposal and waits again. If the user does not confirm, no API call occurs.

The backend cannot cryptographically verify provider-neutral chat authorship. `confirmation.confirmed=true` is an Agent assertion audited with the proposal digest. This accepted limitation is bounded by loopback-only registered-Agent access, atomic idempotent creation, project-scoped authority, and the invariant that creation never starts Project Execution.

## Rollout and security

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `VO_AGENT_PROJECT_AUTHORING_ENABLED` | `false` | Gate direct creation and Agent maintenance |
| `VO_PROJECT_INSTANCE_RECURRENCE_ENABLED` | `false` | Gate recurrence intent and occurrence dispatch |
| `VO_PROJECT_INSTANCE_RECURRENCE_DISPATCH_PAUSED` | `false` | Pause dispatch without deleting durable intent |

Agent routes require loopback, no browser `Origin`, `X-VO-Agent-Action: project-authoring`, and a registered `X-VO-Agent-Id`. Agents must never acquire `X-VO-Management-Token`. Management authentication remains required for protected maintenance confirmation, grant rotation/revocation, template instantiation, recurrence pause/resume, health, and existing project CRUD.

## Direct-create API

`POST /api/agent/project-authoring/projects` accepts:

```json
{
  "idempotencyKey": "agent:project:stable-key",
  "confirmation": {
    "confirmed": true,
    "summaryDigest": "64 lowercase SHA-256 hex characters"
  },
  "project": {
    "title": "Release preparation",
    "projectType": "one_time",
    "agentMaintenanceMode": "strict_confirmation",
    "columns": [{"id": "backlog", "title": "Backlog"}],
    "tasks": [{
      "title": "Prepare release evidence",
      "columnId": "backlog",
      "responsibleActor": {"type": "agent", "id": "owner"},
      "executorActor": {"type": "agent", "id": "builder"},
      "reviewerRecommendation": {"recommended": false, "triggers": []}
    }],
    "template": {"mode": "none"},
    "recurrence": {"enabled": false}
  }
}
```

Every task has one responsible actor and one executor actor; they may be the same. `user:local` work is trackable but cannot start automated execution. Reviewer is absent by default. A `reviewerActor` is included only when the confirmed proposal explicitly assigns it; risk recommendations alone do not assign authority.

The atomic commit contains the project, tasks, actor projections, authoring source/digest, grant hash, immutable template version, recurrence definition, and outbox intent as applicable. Tasks start in `backlog`; `workflowActive` and `projectExecutionFlowActive` are false.

Idempotency is scoped to Agent and key. Same key and semantic payload returns the original project. Same key with changed project or proposal digest returns `project_creation_idempotency_conflict`. Workspace or commit failure leaves no partial project.

The first success returns `projectGrantSecret`; only its hash is persisted. Idempotent retries return the project and public grant status without the secret. If the first response is lost, do not create another project—use management-authenticated grant rotation.

## Maintenance and recurrence

| Method and path | Contract |
| --- | --- |
| `GET /api/agent/projects/{projectId}/grant-status` | Validate the Agent/project scoped grant |
| `POST /api/agent/projects/{projectId}/maintenance` | Submit protected maintenance or an allowed autonomous routine update |
| `POST /api/agent/project-recurrences/{recurrenceId}/occurrences` | Idempotently materialize one independent occurrence |
| `POST /api/project-authoring/projects/{projectId}/maintenance/{id}/confirm|reject` | Management decision for protected maintenance |
| `POST /api/project-authoring/projects/{projectId}/grant/rotate|revoke` | Management grant administration |
| `POST /api/project-authoring/recurrences/{recurrenceId}/pause|resume` | Management recurrence administration |
| `GET /api/project-authoring/health` | Credential-safe metrics, outbox age, and intervention alerts |

`strict_confirmation` makes every Agent maintenance mutation pending. `autonomous` directly permits only assigned-task `executionState`, `description`, `checklist`, `evidence`, and `dueDate`. Structural, role, reviewer, recurrence, workspace, archive/delete, and mode changes always require user confirmation.

Protected maintenance requests use `expectedRevision` for optimistic concurrency and a one-time `confirmationKey` for the management decision. An autonomous assigned-task change uses the `routine_task_update` operation; it cannot widen the allowed field set or change project structure.

Reusable and recurring projects pin immutable `templateId,version` pairs. Each created project records its `projectTemplateInstance` projection. A due recurrence uses an expiring occurrence claim and compare-and-set commit keyed by `occurrenceId` to create one independent, unstarted project. Duplicate or restarted callbacks return the already materialized project. Legacy `projectWorkflow` and `projectTask` cron behavior is unchanged.

## Legacy draft compatibility

The previous request/status/edit/confirm/reject routes and draft review UI are removed. Previously persisted `projectAuthoringRequests` records remain inert compatibility metadata: they are readable by the store, not exposed as active work, not counted in health, not automatically materialized, and not deleted by this change.

## Failure and recovery runbook

1. **Feature disabled (`503`)**: enable direct authoring locally first; enable recurrence only after direct-create health is clean.
2. **Validation (`400`/`409`)**: refresh `/api/agents`. If the correction changes semantics, present the revised natural-language proposal and obtain confirmation again with a new key.
3. **Idempotency conflict (`409`)**: do not overwrite the original result. Use a new key only after a newly confirmed semantic proposal.
4. **Workspace/commit failure**: managed uncommitted workspaces are cleaned; retry the unchanged confirmation with the same key.
5. **Lost first response**: locate the real project; do not recreate it. Rotate the grant through the trusted management surface.
6. **Revoked/cross-scope grant (`403`)**: stop Agent mutation; never reuse another project or Agent's secret.
7. **Outbox/Gateway failure**: pause dispatch, preserve durable intent, repair the dependency, then resume bounded reconciliation.
8. **Invalid recurrence actor**: retain the intervention alert; use a user-confirmed template/role correction rather than silent substitution.
9. **Rollback**: disable authoring, pause recurrence, let atomic writes finish, preserve root metadata, deploy the previous compatible code, and verify ordinary project/legacy cron reads.

Health is `disabled`, `healthy`, `paused`, `degraded`, or `intervention_required`. Recurrence outbox age of fifteen minutes degrades health; legacy pending draft age does not. Process-local counters reset on restart, while durable outbox and intervention state reconstruct operational health.
