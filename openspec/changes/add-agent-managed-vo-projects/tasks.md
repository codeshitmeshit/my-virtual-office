## 1. Compatibility Foundation

- [x] 1.1 Add responsible, executor, and reviewer actor-reference validators plus legacy task-field projection helpers, with unit tests for same-actor roles, Agent, local-user, missing, and excluded actors.
- [x] 1.2 Extend `MarkdownProjectStore` root serialization/read repair to round-trip bounded authoring requests, idempotency, grant hashes, versioned templates, recurrences, and outbox data plus backward-compatible project/task defaults.
- [x] 1.3 Add Project Execution eligibility coverage proving human-executed tasks remain trackable but cannot start automated execution without an executable Agent.
- [x] 1.4 Add disabled-by-default authoring and recurrence feature flags plus configured body/task/pending/audit/history limits, outbox batch/concurrency/backoff settings, and stable overload errors before exposing any new write route.

## 2. Project Authoring Request Domain

- [x] 2.1 Add bounded project-authoring root collections under `ProjectRepository.update_root`, with sanitized public views, terminal compaction/tombstones, retention metadata, and corruption-safe tests.
- [x] 2.2 Implement complete draft validation for project fields, tasks, same-or-distinct required actors, optional user-confirmed reviewer recommendations, maintenance mode, template intent, recurrence rules, and request idempotency.
- [x] 2.3 Implement pending draft creation, revisioned detail/list/status, edit, reject, and immutable approved-snapshot commands with the documented state machine and audit tests.
- [x] 2.4 Implement compare-and-set confirmed-draft materialization that commits the request, complete project/task aggregate, user-approved reviewer assignments, idempotency, template/recurrence metadata, and outbox intent once, cleans up failed managed-workspace preparation, preserves retryable failures, and does not start Project Execution.

## 3. Agent and User HTTP Boundaries

- [x] 3.1 Add loopback/no-Origin, size-limited Agent draft submission and request-secret-protected status routes that validate a registered requesting Agent and never expose management credentials or stored secret hashes.
- [x] 3.2 Add management-authenticated draft list/detail/edit/confirm/reject routes with stable authorization, validation, conflict, and idempotency responses.
- [x] 3.3 Add HTTP contract tests proving Agent routes cannot materialize projects, browser-origin requests are rejected, request secrets cannot cross requests, and protected routes reject missing or invalid management tokens before mutation.
- [x] 3.4 Add management-authenticated scoped-grant revoke/rotate endpoints and Agent grant-status handling, with tests proving old, lost, cross-project, and cross-Agent grants cannot mutate state.

## 4. Controlled Project Maintenance

- [x] 4.1 Persist `strict_confirmation` and `autonomous` project maintenance modes plus a revocable, rotatable, hashed scoped grant bound to the approved authoring Agent and project.
- [x] 4.2 Add Agent-originated maintenance request commands for strict-mode and protected autonomous mutations, including management-confirmed atomic application.
- [x] 4.3 Add the scoped-grant autonomous routine-update allowlist for assigned Agents and regression tests rejecting missing/revoked grants, unassigned actors, structural changes, workspace changes, archive/delete, and role escalation.
- [x] 4.4 Add sanitized audit events for draft, confirmation, rejection, materialization, maintenance, and failed actions without persisting credentials.

## 5. Versioned Templates

- [x] 5.1 Add versioned template snapshots containing columns, complete task blueprints, actor references, reviewer policy, maintenance mode, and execution settings while adapting legacy templates as implicit version 1.
- [x] 5.2 Implement idempotent manual instantiation from an immutable template version with actor revalidation and one atomic project commit.
- [x] 5.3 Add template compatibility tests proving new versions affect only future instances and existing browser template behavior remains readable and usable.

## 6. Independent Project Recurrence

- [x] 6.1 Add a durable recurrence-registration outbox and bounded reconciler for a `projectTemplateInstance` binding that reuses schedule validation and Gateway integration without changing existing project/task execution target kinds.
- [x] 6.2 Implement expiring token-owned occurrence claims and compare-and-set independent project materialization with template/version/source traceability, workspace cleanup, restart recovery, and duplicate-callback protection.
- [x] 6.3 Add pause/resume, retry-safe failure, invalid-actor intervention alerts, occurrence history, restart recovery, and concurrent-dispatch tests.

## 7. Trusted User Review Surface

- [x] 7.1 Add a pending Agent project-drafts view that displays the original proposal, editable approved configuration, reviewer rationale, template/recurrence settings, and validation errors.
- [x] 7.2 Wire management-authenticated edit, confirm, and reject actions with duplicate-action suppression and visible created-project navigation.
- [x] 7.3 Add static and browser-level tests for pending, edited, confirmed, rejected, failed, and idempotently repeated review flows.

## 8. VO Skills and Documentation

- [x] 8.1 Add `skills/vo-project-authoring/SKILL.md` and agent metadata covering explicit-only invocation, roster lookup, complete draft construction, candidate confirmation, high-risk/cross-team/critical-delivery reviewer recommendations, request-secret handling, status polling, and maintenance boundaries.
- [x] 8.2 Update the live VO operating-guidelines routing and `skills/catalog.md` so authoring uses the new skill while execution/review/acceptance remains with `vo-project-workflow`.
- [x] 8.3 Document the Agent authoring APIs, user confirmation contract, actor semantics, template versioning, recurrence behavior, and operational failure/recovery procedures.

## 9. Verification and Rollout

- [x] 9.1 Add structured counters, duration measurements, redacted/rate-limited logs, health states, queue-age reporting, and intervention alerts for the authoring and recurrence pipelines.
- [x] 9.2 Run focused project command, repository, management-token, request-secret, execution-role, template, schedule, capacity-limit, observability, and authoring service tests and record the results as OpenSpec evidence.
- [x] 9.3 Run compatibility and end-to-end verification proving legacy projects and cron bindings are unchanged, one confirmed draft produces one complete project, and materialization never starts execution automatically.
- [x] 9.4 Rehearse flag-off deployment, local-only authoring enablement, autonomous allowlist enablement, recurrence enablement, grant revocation/rotation, outbox drain/pause, and code rollback; document observed gates and unresolved limitations.

## 10. Conversation-Confirmed Direct Creation Simplification

- [x] 10.1 Add an Agent-scoped `create_confirmed_project` domain command that validates a confirmation assertion and proposal digest, atomically creates the complete unstarted project/task aggregate with template/recurrence/grant data, returns the grant secret only on first creation, and enforces same-payload idempotency with conflict on key reuse.
- [x] 10.2 Add the loopback/no-Origin `POST /api/agent/project-authoring/projects` HTTP contract and remove active Agent draft submission/status plus management draft list/detail/edit/confirm/reject routing, while preserving management authentication for maintenance, grant administration, recurrence administration, and existing project CRUD.
- [ ] 10.3 Remove the Agent project-draft review UI wiring/assets and update authoring health so inert legacy request metadata is not treated as active pending work; retain backward-compatible root reads without deleting old request records.
- [ ] 10.4 Rewrite `vo-project-authoring`, VO routing, metadata, and operations documentation around natural-language proposal confirmation followed by direct creation, including semantic-change reconfirmation, reviewer-default behavior, one-time grant handling, no-auto-execution, and the accepted unsigned-chat-confirmation limitation.
- [ ] 10.5 Run and record focused direct-create, security, idempotency, atomicity, UI-removal, skill/docs, legacy project/template/cron, Project Execution, recurrence, observability, flag-off, and rollback-compatibility verification; update rollout evidence and confirm no active draft route or UI remains.
