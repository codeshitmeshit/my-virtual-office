# VO Agent Project Authoring API and Operations

This document defines the HTTP and operational contract for Agent-authored Virtual Office projects. The runtime skill is `/skills/vo-project-authoring/SKILL.md`; Project Execution, review, acceptance, cancellation, and artifact access remain in `/skills/vo-project-workflow/SKILL.md`.

## Security and rollout boundary

Authoring and recurrence are local-only, disabled-by-default capabilities:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `VO_AGENT_PROJECT_AUTHORING_ENABLED` | `false` | Accept Agent authoring and scoped-maintenance actions |
| `VO_PROJECT_INSTANCE_RECURRENCE_ENABLED` | `false` | Reconcile recurrence registrations and materialize occurrences |
| `VO_PROJECT_INSTANCE_RECURRENCE_DISPATCH_PAUSED` | `false` | Pause occurrence dispatch without deleting durable intent |

Agent routes accept only loopback requests without a browser `Origin`. They require `X-VO-Agent-Action: project-authoring` and a registered `X-VO-Agent-Id`. Agent callers must never acquire `X-VO-Management-Token`; management endpoints are for the trusted local user surface and validate that token before reading mutation bodies.

Request bodies, initial task counts, pending queues, maintenance queues, audit history, recurrence history, outbox capacity, worker count, batch size, retry delay, attempts, and occurrence claim duration have bounded `VO_PROJECT_AUTHORING_*` or `VO_PROJECT_RECURRENCE_*` configuration in `app/services/project_authoring_config.py`.

## Actor and draft contract

Every initial task has one `responsibleActor` and one `executorActor`; they may be the same. An actor is either a registered, eligible Agent (`{"type":"agent","id":"..."}`) or the current local user (`{"type":"user","id":"user:local"}`). A human executor remains trackable but cannot start automated Project Execution. Excluded or missing Agents are rejected when drafting, confirming, instantiating, and materializing recurrence occurrences.

The Agent supplies reviewer recommendations, not reviewer assignments. The trusted user may assign `reviewerActor` while editing the approved draft. A complete draft includes columns, all initial tasks and actors, an explicit recommendation per task, `agentMaintenanceMode`, template intent, and recurrence intent. Confirmation materializes the whole aggregate atomically and never starts Project Execution.

## Agent API

All Agent calls use the two identity headers above.

| Method and path | Authentication | Contract |
| --- | --- | --- |
| `POST /api/agent/project-authoring/requests` | identity headers | Submit `{idempotencyKey,draft}`; returns a pending request and exposes `requestSecret` only on first creation |
| `GET /api/agent/project-authoring/requests/{requestId}` | identity headers + `Authorization: Bearer {requestSecret}` | Read the sanitized status for that exact request and Agent |
| `GET /api/agent/projects/{projectId}/grant-status` | identity headers + confirmed request/grant secret | Validate the grant bound to that exact project and Agent |
| `POST /api/agent/projects/{projectId}/maintenance` | identity headers + grant secret | Submit `{idempotencyKey,mutation}` or apply an allowed autonomous routine task update |
| `POST /api/agent/project-recurrences/{recurrenceId}/occurrences` | identity headers + source-project grant secret | Materialize one idempotent occurrence by `occurrenceId` |

The request secret is held only in the Agent's current process memory. It must not be logged, persisted, echoed into chat, or reused across requests. A repeated submission must reuse the original idempotency key. If the secret is lost, the Agent cannot recover it; the trusted user can still inspect and decide the pending request. Once confirmation succeeds, that secret is the scoped project grant until revoked or rotated.

Status states are `pending`, `materializing`, `confirmed`, `rejected`, and `failed`. Poll at a bounded, low frequency. `failed` retains retryable state and its sanitized error; do not create an equivalent second request to bypass the state or a user rejection.

In `strict_confirmation`, every maintenance mutation becomes a pending maintenance request. In `autonomous`, only `routine_task_update` by the Agent assigned to that task may directly change the allowlisted execution state, description, checklist, evidence, or due date fields. Structural, role, reviewer, recurrence, workspace, archive, delete, and maintenance-mode changes always require user confirmation.

## Trusted user API and confirmation contract

The local “Agent project drafts” view uses these management-authenticated routes:

| Method and path | Body or result |
| --- | --- |
| `GET /api/project-authoring/requests?state=...&limit=...` | Bounded sanitized request list |
| `GET /api/project-authoring/requests/{requestId}` | Original proposal, editable approved draft, state, revision, and errors |
| `PUT /api/project-authoring/requests/{requestId}` | `{expectedRevision,draft}`; optimistic edit |
| `POST /api/project-authoring/requests/{requestId}/confirm` | `{expectedRevision,confirmationKey}`; one atomic materialization |
| `POST /api/project-authoring/requests/{requestId}/reject` | `{expectedRevision,reason}` |
| `POST /api/project-authoring/projects/{projectId}/maintenance/{maintenanceId}/confirm` | `{expectedRevision}` |
| `POST /api/project-authoring/projects/{projectId}/maintenance/{maintenanceId}/reject` | `{expectedRevision,reason}` |
| `POST /api/project-authoring/projects/{projectId}/grant/revoke` | Revoke all further Agent use of the current grant |
| `POST /api/project-authoring/projects/{projectId}/grant/rotate` | Invalidate the old secret and return a replacement once |

The user reviews the original proposal and working approved draft, including reviewer rationale, candidate, template/version, recurrence, and validation errors. `expectedRevision` rejects stale browser actions; `confirmationKey` and compare-and-set materialization make repeated confirmation safe. A `confirmed` response with `projectId` means one complete project exists, not that execution has started.

## Immutable templates and independent recurrence

`reusable` and `recurring` projects create or reference an immutable template version. A snapshot includes columns, complete task blueprints, actors, reviewer policy, maintenance mode, and execution settings. Updating a template appends a version; existing projects and recurrences keep their pinned `{templateId,version}`. Legacy templates are read as implicit version 1.

The trusted user may instantiate a pinned version with `POST /api/project-authoring/templates/{templateId}/instantiate` and `{version,idempotencyKey,overrides}`. Actors are revalidated at instantiation and the project is committed once.

A confirmed recurring draft writes a durable registration outbox entry. The bounded reconciler converges that entry to a Gateway `projectTemplateInstance` binding. Each callback claims an `occurrenceId` with an expiring owner token, loads the pinned template version, revalidates actors, prepares a workspace, and compare-and-set commits an independent project with source/template/occurrence traceability. Duplicate or restarted callbacks return the already materialized project and never reopen the source project.

Management pause/resume uses `POST /api/project-authoring/recurrences/{recurrenceId}/pause` or `/resume`. Global dispatch pause retains registrations and occurrences for later recovery.

## Failure and recovery runbook

1. **Feature disabled (`503`)**: keep both flags off during deployment. Enable authoring locally first; enable recurrence only after authoring health is clean. Disabling takes effect on the next action and does not delete stored requests.
2. **Capacity (`429`/`503`)**: inspect pending request age, per-Agent/global pending counts, per-project maintenance count, and outbox depth. Resolve or compact terminal work before raising a bounded limit.
3. **Draft validation or actor failure (`400`/`409`)**: refresh `/api/agents`, edit the same request revision, and retry confirmation. Do not create a parallel request.
4. **Workspace preparation failure**: the service removes a newly prepared managed workspace and leaves the request retryable as `failed`. Correct the workspace condition, edit if necessary, and confirm the same request again.
5. **Stale revision or duplicate action (`409`)**: reread request detail. If already `confirmed`, navigate to its `projectId`; otherwise repeat against the latest revision with the same logical confirmation key.
6. **Lost, revoked, or rotated secret (`403`)**: stop Agent polling/mutation. The user can decide pending work, revoke the compromised grant, or rotate once and transfer the new value through a trusted ephemeral channel. Old, cross-Agent, and cross-project secrets remain invalid.
7. **Outbox/Gateway failure**: pause global dispatch when needed. The reconciler retains durable intent, applies bounded exponential backoff, and raises intervention after max attempts. Fix Gateway/configuration, then resume; do not delete the binding intent.
8. **Occurrence actor invalid**: keep the occurrence failed and recurrence visible with an intervention alert. Restore/replace the actor through a user-confirmed template/recurrence change; never silently remap identity.
9. **Stuck occurrence claim**: wait for the configured claim lease to expire, then retry the same `occurrenceId`. Compare-and-set and source traceability prevent duplicate projects.
10. **Emergency rollback**: turn off authoring, turn on recurrence dispatch pause, allow in-flight writes to finish, deploy the previous code, and preserve root metadata. New readers are backward compatible and legacy projects/cron target kinds are not rewritten.

After any recovery, verify that credentials are absent from persisted root/audit data, the request or occurrence has one terminal result, recurrence bindings are converged, and no materialized task has an active Project Execution attempt unless a separate execution action explicitly started it.
