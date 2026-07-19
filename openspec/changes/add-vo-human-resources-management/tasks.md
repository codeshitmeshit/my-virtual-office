## 1. Compatibility Baselines And Test Harnesses

- [x] 1.1 Capture the pre-extraction archive-manager characterization baseline, including creation, rediscovery, Profile repair, communication-skill readiness, pause/resume, deletion and assignment protection, creation failure degradation, and restart-visible state; record the exact focused test commands and results as OpenSpec evidence.
- [x] 1.2 Add missing deterministic archive-manager characterization tests for concurrent reconciliation, provider timeout, create-success/Profile-failure repair, stale discovery, and repeated startup checks without changing production behavior.
- [x] 1.3 Capture and strengthen meeting/project compatibility tests for archive-manager meeting rejection, ordinary system-role assignment rejection, legacy meeting creation, executable meeting occupancy, terminal restoration, and stable archive-specific error codes.
- [x] 1.4 Add reusable fake system-Agent ports, fake clock/ID providers, temporary workspace builders, and provider-call assertions for subsequent lifecycle and HR unit tests without requiring a real OpenClaw installation.

## 2. Shared VO System-Agent Role And Profile Foundation

- [x] 2.1 Implement `app/services/system_agent_roles.py` with immutable role definitions, stable identity matching, assignable/deletable/meeting policies, role lookup, and focused validation/policy tests for archive manager, HR, unknown roles, and conflicting definitions.
- [x] 2.2 Implement `app/services/system_agent_profiles.py` with generic versioned template parsing, required-file validation, token rendering, safe workspace resolution, symlink/path rejection, atomic writes, update detection, and exhaustive filesystem unit tests.
- [x] 2.3 Implement the state and port contracts in `app/services/system_agent_lifecycle.py`, including normalized lifecycle states, bounded activity, injected provider/state/presence/clock/ID collaborators, and static tests proving the module does not import `server.py` or HTTP transport.
- [x] 2.4 Implement idempotent lifecycle reconciliation for existing, missing, partial, duplicate, stale, failed, and restarted provider Agent states, with deterministic tests for retries, concurrent calls, provider exceptions, timeouts, and partial Profile/skill success.
- [x] 2.5 Implement lifecycle pause, resume, public-state projection, metadata projection, and degraded-read semantics with tests for state transitions, automatic-work skip policy, resume reconciliation, last-error handling, and bounded activity.

## 3. Archive Manager Migration To Shared Lifecycle

- [x] 3.1 Introduce an Archive Room lifecycle adapter that preserves `archive-room/manager.json`, the existing Profile template/version, workspace rules, public fields, labels, and legacy function delegates; verify state and Profile compatibility before switching creation.
- [x] 3.2 Route archive-manager discovery, auto-creation, communication-skill synchronization, partial repair, and startup reconciliation through the shared lifecycle while preserving provider call parameters and existing error behavior; run the focused characterization suite.
- [x] 3.3 Route archive-manager pause/resume, presence projection, system-role metadata, deletion protection, assignment protection, and public state through shared role policy and lifecycle delegates without moving Archive Room maintenance logic.
- [x] 3.4 Remove obsolete duplicate archive lifecycle/Profile implementations after all callers migrate, add static ownership checks preventing lifecycle logic from returning to `app/server.py`, and run Archive Room Phase 1–8 plus communication-skill regression tests.

## 4. HR System Agent Bootstrap

- [x] 4.1 Add `app/hr-profile.md` and the HR role definition with stable ID `hr`, display name `HR`, non-assignable/non-deletable policy, meeting eligibility, HR-only responsibilities, structured output rules, and Profile rendering tests.
- [x] 4.2 Add the HR lifecycle adapter and `human-resources/hr.json` state repository, using the shared lifecycle for auto-create, rediscovery, Profile/skill repair, pause/resume, activity, error degradation, and public state; cover all paths with fake-provider tests.
- [x] 4.3 Add `VO_HR_ENABLED` bootstrap wiring and startup reconciliation as thin `app/server.py` construction/delegation, proving disabled startup has no provider or storage side effect and enabled repeated/restarted startup creates at most one HR.
- [x] 4.4 Generalize project assignment and Agent deletion checks to system-role policy, preserving archive-manager compatibility while rejecting HR with stable HR/system-role codes; update all legacy and extracted project call sites and tests.
- [x] 4.5 Generalize legacy and executable meeting participant validation to role policy so HR is eligible and archive manager remains ineligible; verify HR occupancy/restoration and prove HR attendance emits no automatic performance event.

## 5. Transactional Human Resources Repository

- [x] 5.1 Implement `app/services/hr_repository.py` initialization, connection policy, schema metadata, transactional migration runner, foreign keys, busy timeout, safe database path, and failure-atomic schema tests using temporary SQLite databases.
- [x] 5.2 Add transactional Agent, identity-history, and introduction persistence with stable AI-ID uniqueness, optimistic/conflict behavior, status indexes, pagination, and tests for rename, duplicate discovery, inactive history, reactivation, and concurrent updates.
- [x] 5.3 Add daily-cycle, report-request, daily-report, assessment-version, and assessment-evidence persistence with date/Agent unique constraints, claim fencing, current-version invariants, JSON validation, pagination, and concurrency/restart tests.
- [x] 5.4 Add access-grant, access-log, and HR-activity persistence with hashed secrets only, rotation/revocation, successful-view uniqueness semantics, bounded queries, retention-safe history, and tests that stored/exported values never contain raw grants.
- [x] 5.5 Add management-only repository health and JSON diagnostic/export queries, corruption/migration failure reporting, size/page limits, and tests proving export is read-only and SQLite remains the sole authority.

## 6. HR Agent Directory And Introduction Workflow

- [x] 6.1 Implement `app/services/hr_directory.py` roster reconciliation across system, project, external, and synthetic Agents, with HR self-exclusion from report/assessment eligibility and tests for duplicate sources, changed names, unavailable providers, inactive states, and reactivation.
- [x] 6.2 Implement introduction request claiming and HR-to-Agent conversation orchestration with deterministic conversation keys, raw response preservation, neutral no-response, per-Agent failure isolation, and injected fake-conversation tests.
- [x] 6.3 Implement HR structured introduction summarization, schema validation, provenance/version persistence, stale-role clarification, and conflict-safe replacement with tests for valid, malformed, unsupported, missing, and changed self-descriptions.
- [x] 6.4 Implement safe directory projections containing only name, introduction, AI ID, availability, and readiness; add pagination/filtering and tests that reports, evidence, assessments, grants, and sensitive metadata never enter the directory view.

## 7. Managed Agent-Directory Skill And Agent Grants

- [x] 7.1 Create the canonical `skills/vo-agent-directory/SKILL.md` covering safe roster lookup, controlled Agent lookup, self access-log lookup, grant use, and prohibited direct storage/management access; add static content and endpoint-contract tests.
- [x] 7.2 Extract the existing builtin skill seeding into a generic managed-skill registry that preserves current communication-skill behavior, ownership markers, hashes, atomic replacement, legacy conflict handling, symlink protection, and all existing tests.
- [x] 7.3 Implement `app/services/hr_skill_publisher.py` for canonical directory-skill publication and supported workspace installation with readiness states, path validation, conflict preservation, deterministic refresh, and fake-workspace tests.
- [x] 7.4 Implement per-Agent Human Resources grant issuance, digest storage, secure workspace grant-reference delivery, rotation, revocation on ineligibility/deletion, and unsupported-provider readiness without embedding secrets in `SKILL.md` or API responses.
- [x] 7.5 Wire directory reconciliation to skill/grant readiness refresh and verify one Agent's installation conflict or unsupported provider does not block directory updates, HR-initiated reports, or other Agent installations.

## 8. Daily Reporting Domain

- [x] 8.1 Implement `app/services/hr_reporting.py` cycle creation, eligible-roster snapshot, request states, per-Agent claims, one-cycle-per-local-date and one-report-per-Agent/date invariants, with duplicate trigger and concurrent claim tests.
- [x] 8.2 Implement visible HR-to-Agent daily requests through an injected conversation port, preserving sender/target context, deterministic idempotency keys, raw responses, timeout/failure classification, and per-Agent isolation.
- [x] 8.3 Implement HR-owned report normalization and strict structured parsing for completed work, projects/tasks, artifacts, blockers, help requests, and submission metadata; retain raw reports on normalization failure and reject unsupported or oversized output.
- [x] 8.4 Implement submission-window closure, neutral `not_submitted`, late submission into the same dated record, duplicate response handling, normalization retry, and tests proving non-response never creates a synthetic report or low-work conclusion.
- [x] 8.5 Implement cycle and per-Agent public/management status projections for waiting, submitted, late, not submitted, normalization failed, skipped, and complete states with accurate aggregate counts and pagination tests.

## 9. Evidence And HR Performance Assessment

- [x] 9.1 Implement `app/services/hr_evidence.py` typed read-only ports and sanitizers for dated project/task transitions, relevant meeting contributions, artifact metadata, execution results, blockers, and waiting states, with per-source caps and privacy/secret exclusion tests.
- [x] 9.2 Implement `app/services/hr_assessments.py` structured assessment schema/parser enforcing contribution, workload, rationale, evidence, blockers, strengths, improvements, runtime diagnosis, information sufficiency, HR identity, allowed workload values, and no score/rank fields.
- [x] 9.3 Implement HR-only assessment orchestration after cycle closure, combining report and bounded evidence, using `insufficient_information` when evidence is inadequate, and proving meeting attendance or non-submission alone cannot determine performance.
- [x] 9.4 Implement assessment idempotency, one current version per Agent/date, prior-version retention, late-report/evidence revision reasons, evidence linkage, and per-Agent failure isolation with retry and concurrent evaluation tests.
- [x] 9.5 Add explicit non-punitive guards preventing assessment output from automatically pausing, deleting, reassigning, ranking, or numerically scoring Agents; verify existing project scores remain behaviorally separate.

## 10. Durable Scheduler And Observability

- [x] 10.1 Implement validated HR configuration for master/scheduler switches, VO timezone, daily time, submission window, worker count, timeout, and retry limits, with defaults, invalid-value handling, and boundary tests.
- [x] 10.2 Implement `app/services/hr_scheduler.py` due-time calculation, DST/local-date handling, today's-only startup catch-up, open-cycle recovery, no historical backfill, and deterministic fake-clock tests.
- [x] 10.3 Implement durable report and assessment claim processing with bounded worker pools, claim expiry/fencing, retry limits, queue backpressure, graceful feature-disable behavior, and tests for dual loops, restarts, late workers, and one-Agent stalls.
- [x] 10.4 Add thin startup reconciliation-loop wiring plus manual run/close/retry commands that use the same durable scheduler paths; verify HTTP threads do not wait for whole-cycle provider work.
- [x] 10.5 Implement `app/services/hr_observability.py` counters, durations, queue age, lifecycle/directory/report/assessment/query/skill metrics, rate-limited sanitized logs, and a health snapshot with tests against raw report, assessment, token, credential, and provider-envelope leakage.

## 11. Human And Agent API Boundaries

- [x] 11.1 Implement `app/services/hr_governance.py` caller roles and server-side full/public/self projections with field allowlists, stable denial codes, and exhaustive matrix tests for human, HR, self, cross-Agent, inactive Agent, and unknown caller.
- [x] 11.2 Implement management application queries/commands in `app/services/hr_api.py` for overview, Agent detail, access log, health/export, HR pause/resume, and cycle run/close/retry with pagination, body limits, and no transport imports.
- [x] 11.3 Implement Agent grant authentication requiring loopback, no browser Origin, Human Resources action header, known AI ID, constant-time bearer digest match, active grant, and identity binding; cover spoofing, missing, expired, revoked, mismatched, and unsupported-provider cases.
- [ ] 11.4 Implement Agent directory, cross-Agent public detail, and self access-log application queries; commit exactly one access record before successful cross-Agent disclosure, exempt HR/human routes, and fail closed when audit persistence fails.
- [ ] 11.5 Add thin `OfficeHandler` route delegation for all Human Resources management and Agent endpoints, reuse `managementFetch` challenge semantics, set minimal CORS/allowed headers, normalize errors, and add HTTP contract/security tests.

## 12. Human Resources User Experience

- [ ] 12.1 Add `app/human-resources.css`, the first-level Human Resources toolbar entry, independent modal shell, script/style registration, and responsive list/detail layout without coupling to Archive Room JavaScript state.
- [ ] 12.2 Implement `app/human-resources.js` management-token overview loading and rendering for HR state, Agent availability totals, daily status counts, recent activity, unresolved/failed prioritization, loading, empty, and degraded states with pure-helper Node tests.
- [ ] 12.3 Implement Agent detail rendering for identity/provenance, raw versus normalized reports, assessment versions, workload history, evidence, blockers, improvements, workflow state, and authorized access history with pagination and stale-request protection.
- [ ] 12.4 Implement HR pause/resume and cycle run/close/retry controls with confirmation, busy/error feedback, scroll/state preservation, and tests proving existing data remains browsable while HR is paused or failed.
- [ ] 12.5 Add complete English/Chinese localization, accessible labels, focus/keyboard/close behavior, semantic state labels, and localization-integrity/static JavaScript checks for every Human Resources workflow and error state.
- [ ] 12.6 Add a deterministic browser acceptance fixture and script covering first-level navigation, HR lifecycle, roster/detail, daily statuses, assessment separation, access history, pagination, pause/resume, and partial/degraded failures.

## 13. Integrated Regression And Development-Machine Acceptance

- [ ] 13.1 Run and record focused Python/Node integration suites for shared lifecycle, HR repository/directory/skill/reporting/assessment/scheduler/governance/API/UI, resolving every failure without weakening specified assertions.
- [ ] 13.2 Run and record Archive Room Phase 1–8, archive-manager Phase 4, Agent communication skill/routing, project assignment/actor, meeting lifecycle/service-boundary, provider, management-token, i18n, and static modularity regressions.
- [ ] 13.3 Run live local browser acceptance with fake provider data and record screenshots/assertions for the Human Resources happy path, permissions, partial failures, and degraded-read path.
- [ ] 13.4 Identify and document the approved development-machine target, deployment/start commands, OpenClaw and VO versions, configuration values, backup location, feature-switch sequence, and rollback commands before any real-environment mutation.
- [ ] 13.5 Deploy to the development machine with `VO_HR_ENABLED=0` and scheduler disabled; run existing VO, archive-manager, Archive Room, project, meeting, and provider smoke tests and record a clean pre-enable baseline.
- [ ] 13.6 Enable HR lifecycle only and verify real OpenClaw auto-create, uniqueness, rediscovery, restart repair, Profile/communication skill, pause/resume, office visibility, HR meeting participation, archive-manager meeting rejection, assignment/deletion protection, and role isolation.
- [ ] 13.7 Enable directory, introduction, managed skill, and grants; verify real Agent discovery, HR self-exclusion, Agent self-description, skill refresh, secure grant delivery, public lookup, denial paths, access audit, and unsupported-provider readiness.
- [ ] 13.8 Enable a controlled short daily cycle and verify real HR-to-Agent requests, raw and normalized reports, non-response, late submission, evidence collection, assessment, insufficient-information behavior, failure isolation, duplicate trigger prevention, and restart recovery.
- [ ] 13.9 Execute rollback rehearsal by disabling scheduler then HR, allowing claims to settle/expire, preserving HR data and Agent identity, and proving Archive Room and existing VO workflows remain operational; record restoration steps and results.
- [ ] 13.10 Run final OpenSpec validation, assemble specification-to-test traceability and all local/development-machine evidence, document remaining unsupported provider delivery or other uncovered items, and prepare the separate test-result confirmation package without archiving the change.
