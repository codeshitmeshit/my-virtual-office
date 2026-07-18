## Context

VO now has the backend primitives for complete project validation, atomic project/task creation, actor references, scoped grants, immutable templates, independent recurrence, and Project Execution safety gates. The first design added a persisted pending-draft state machine and a management-authenticated browser review surface before project creation.

The confirmed product change removes that backend draft concept. The Agent presents a natural-language proposal in the existing conversation, waits for explicit user confirmation there, then submits one structured direct-create request. Creation is considered low risk because it is reversible at the product level and never starts Project Execution; execution, review, acceptance, cancellation, and protected maintenance retain their separate gates.

The generic VO backend cannot cryptographically prove that an arbitrary provider conversation message came from the user. This design therefore treats conversational confirmation as a skill-level contract and records a bounded confirmation assertion/digest for audit. Backend safety comes from local-only registered-Agent access, complete validation, idempotency, atomic creation, scoped authority, and the invariant that creation does not execute work.

## Goals / Non-Goals

**Goals:**

- Let an explicitly invoked Agent present a complete natural-language project proposal and create the real project immediately after the user confirms it.
- Create the project, all tasks, role assignments, optional confirmed reviewer assignments, template version, recurrence intent, grant, and audit data in one idempotent root commit.
- Return the created project identifier and a one-time scoped grant without exposing the management token.
- Preserve responsible/executor semantics, optional reviewer defaults, controlled maintenance, immutable templates, independent recurrence, and legacy compatibility.
- Keep every created task unstarted until a separate Project Execution action passes existing gates.
- Remove the pending-draft API, state machine, polling, and browser review UI from the active product surface.

**Non-Goals:**

- Persisting or rendering the natural-language proposal as a backend draft.
- Cryptographic verification of provider chat confirmation in this release.
- Proactive project creation when the user did not ask for it or did not confirm the displayed proposal.
- Automatically executing, reviewing, accepting, cancelling, or closing a newly created project.
- Weakening management authentication for protected maintenance, grant administration, recurrence administration, or existing browser CRUD.

## Decisions

### 1. Keep `vo-project-authoring`, but make proposal confirmation conversational

The skill first reads the local VO roster, resolves candidates, and renders a natural-language proposal containing project type, tasks, responsible actors, executors, optional reviewer decisions, maintenance mode, and template/recurrence settings. It must stop until the user explicitly confirms that version. Any semantic change causes the skill to show a revised proposal and obtain a new confirmation.

After confirmation, the skill converts the proposal to the structured direct-create payload. `vo-project-workflow` continues to own execution, review, acceptance, cancellation, blockers, and artifacts.

This keeps the user interaction light while preserving an understandable confirmation moment. The natural-language proposal is conversation state, not a second durable product model.

### 2. Replace pending-request materialization with one atomic direct-create command

Add a transport-independent `create_confirmed_project` command that accepts:

```json
{
  "idempotencyKey": "agent:project:stable-key",
  "confirmation": {
    "confirmed": true,
    "summaryDigest": "sha256-of-displayed-proposal"
  },
  "project": {
    "title": "...",
    "projectType": "one_time|reusable|recurring",
    "columns": [],
    "tasks": [],
    "agentMaintenanceMode": "strict_confirmation|autonomous",
    "template": {},
    "recurrence": {}
  }
}
```

The backend validates the registered requesting Agent, confirmation assertion shape, complete project, actors, reviewer assignments, schedule, template intent, limits, and idempotency key before side effects. It prepares a managed workspace outside the repository lock, then performs one compare-and-set root update containing the complete project/task aggregate, authoring audit/source metadata, scoped grant hash, template version, recurrence definition, recurrence outbox intent, and Agent-scoped idempotency result. Commit failure cleans an uncommitted managed workspace.

The command never calls Project Execution. Created tasks use `backlog`, `workflowActive=false`, and `projectExecutionFlowActive=false`.

### 3. Bind direct-create idempotency to Agent and semantic payload

The idempotency scope is `(requestingAgentId, idempotencyKey)`. A retry with the same semantic payload returns the original project and never creates another workspace, template, recurrence, or task set. Reusing the key with a different project/confirmation digest returns a stable conflict.

The first successful response returns `projectGrantSecret`; only its hash is persisted. Later idempotent retries return the existing project and public grant status, not the secret. If the first response is lost, the user can rotate the grant through the trusted management surface. This is an intentional one-time-secret trade-off.

### 4. Treat conversational confirmation as an auditable assertion, not backend authorization

The Agent payload must assert `confirmed=true` and include a bounded SHA-256 digest of the exact natural-language proposal it displayed. The project audit stores the digest, requesting Agent, source surface, and creation time, but not conversation text or credentials.

The backend cannot independently validate that a provider chat message was user-authored. That limitation is accepted because the endpoint is loopback-only, requires a registered Agent action identity, creates only an unstarted project, and grants only project-scoped maintenance authority. If provider-neutral signed user-message evidence becomes available, it can be added without changing project creation semantics.

### 5. Preserve explicit actor references and reviewer defaults

Every task persists exactly one `responsibleActor` and `executorActor`; the same actor may hold both roles. Agent actors continue to project to `assignee` and `executorAgentId`; `user:local` remains trackable but not executable by Project Execution.

The natural-language proposal may recommend a reviewer for `high_risk`, `cross_team`, or `critical_delivery`. The structured request omits `reviewerActor` by default. It includes a reviewer assignment only when that assignment appeared in the confirmed proposal. Existing execution-time reviewer-skip confirmation remains unchanged.

### 6. Keep scoped maintenance grants and protected mutation boundaries

Direct creation generates a grant bound to the project, creating Agent, grant version, and maintenance mode. `strict_confirmation` converts all Agent maintenance into pending maintenance requests. `autonomous` directly permits only assigned-task routine fields: execution state, description, checklist, evidence, and due date.

Task creation/deletion, role/reviewer changes, recurrence changes, archive/delete, workspace changes, and maintenance-mode changes remain management-confirmed. Grant rotate/revoke and recurrence pause/resume remain management-authenticated.

### 7. Keep immutable templates and independent recurrence

Reusable and recurring direct-create requests create or reference one immutable template version. Existing instances remain pinned; new versions affect only future instances. Legacy templates remain implicit version 1.

Recurring creation commits a durable outbox intent with the project. The bounded reconciler registers a distinct `projectTemplateInstance` Gateway target. Every occurrence uses expiring claims and compare-and-set creation to produce one independent, unstarted project. Existing `projectWorkflow` and `projectTask` cron targets remain unchanged.

### 8. Use a separate Agent direct-create route

Add `POST /api/agent/project-authoring/projects`. It is loopback-only, rejects browser `Origin`, requires `X-VO-Agent-Action: project-authoring` and a registered `X-VO-Agent-Id`, enforces bounded JSON, and never accepts or exposes `X-VO-Management-Token`.

Keep `GET /api/agent/projects/{projectId}/grant-status` and `POST /api/agent/projects/{projectId}/maintenance`. Keep management-authenticated maintenance confirmation, grant rotate/revoke, template instantiation, recurrence pause/resume, and health routes.

Remove active routing for Agent draft submission/status and management draft list/detail/edit/confirm/reject. Existing `/api/projects` protection is unchanged.

### 9. Remove the draft review surface and preserve inert legacy metadata

Remove the “Agent project drafts” UI entry, JavaScript, CSS, locale strings, and related browser/static tests. The created real project becomes visible through the normal Projects UI immediately after direct creation.

Previously persisted authoring-request collections remain readable as inert compatibility metadata so rollback and old data loading do not fail. No new request is written, legacy pending requests are not automatically materialized, and health/queue metrics stop counting them as active work. A later explicit retention change may compact them; this refactor performs no destructive migration.

### 10. Simplify capacity, observability, and rollout

Retain body size, initial task count, audit/history, maintenance queue, outbox capacity, worker, retry, and claim limits. Pending-draft per-Agent/global limits and terminal-draft retention are no longer active product limits, though old fields may remain readable for configuration compatibility.

Observability records direct-create totals, failures, conflicts, durations, grant failures, maintenance results, recurrence outbox depth/age, occurrence outcomes, cleanup failures, and intervention alerts. Health no longer reports legacy pending drafts as live queue work.

`VO_AGENT_PROJECT_AUTHORING_ENABLED` gates direct creation and autonomous maintenance. `VO_PROJECT_INSTANCE_RECURRENCE_ENABLED` and dispatch pause retain their current behavior. Rollout starts with both flags off, enables local direct creation, verifies no execution starts, enables autonomous allowlist, then enables recurrence. Rollback disables creation, pauses recurrence, drains or accepts the outbox as inert, and preserves ordinary created projects.

## Risks / Trade-offs

- **Conversation confirmation is not cryptographically provable by the backend.** Mitigation: explicit-only skill contract, digest audit, loopback registered-Agent boundary, atomic idempotent creation, and no automatic execution. This is the principal accepted product trade-off.
- **A lost first response loses the grant secret.** Mitigation: the project remains created and visible; management grant rotation restores scoped access.
- **Removing the review UI reduces post-proposal editing before creation.** Mitigation: edits happen naturally in conversation; every semantic revision requires the Agent to present the proposal again.
- **Legacy pending requests become inert.** Mitigation: preserve data compatibility and do not auto-create from them; document that they require the old compatible version if recovery is needed.
- **Workspace and Gateway effects remain outside one distributed transaction.** Mitigation: workspace cleanup around root CAS and durable recurrence outbox reconciliation.
- **Autonomous maintenance and stale recurrence actors retain prior risks.** Mitigation: narrow allowlist, assignment checks, revocable grants, per-occurrence actor validation, and intervention alerts.

## Migration Plan

1. Add direct-create command/tests by reusing complete draft validation and atomic materialization internals without writing request state.
2. Add the Agent direct-create HTTP route and one-time project grant response; retain management authentication on all protected routes.
3. Update the skill to present a natural-language proposal, wait for explicit confirmation, then call direct create; remove polling and request-secret instructions.
4. Remove draft review UI/assets/routes and stop counting legacy request records as active health queue work.
5. Update documentation and focused tests for idempotency, no partial state, one-time grant, reviewer default, and no auto-execution.
6. Run legacy project/template/cron/Project Execution compatibility and rollout tests with flags off first.

Rollback disables direct creation and autonomous maintenance, pauses recurrence, and deploys the previous compatible code. Real projects created by the new path remain ordinary backward-readable projects. Legacy authoring-request metadata remains preserved and ignored by the new active flow.

## Open Questions

- A future provider-neutral signed confirmation reference could replace the current assertion/digest without changing the direct-create project contract.
- A future retention change may compact inert legacy authoring-request records, but this change intentionally performs no deletion.
