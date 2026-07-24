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
- [x] 4.6 Canonicalize the HR system Agent's visible name as uppercase `HR` at provider creation, lifecycle projection, and directory reconciliation while preserving stable ID `hr`; add regression coverage for legacy `Hr` state and roster values.

## 5. Transactional Human Resources Repository

- [x] 5.1 Implement `app/services/hr_repository.py` initialization, connection policy, schema metadata, transactional migration runner, foreign keys, busy timeout, safe database path, and failure-atomic schema tests using temporary SQLite databases.
- [x] 5.2 Add transactional Agent, identity-history, and introduction persistence with stable AI-ID uniqueness, optimistic/conflict behavior, status indexes, pagination, and tests for rename, duplicate discovery, inactive history, reactivation, and concurrent updates.
- [x] 5.3 Add daily-cycle, report-request, daily-report, assessment-version, and assessment-evidence persistence with date/Agent unique constraints, claim fencing, current-version invariants, JSON validation, pagination, and concurrency/restart tests.
- [x] 5.4 Add access-log and HR-activity persistence with successful-view uniqueness semantics, bounded queries, and retention-safe history; exclude obsolete access-grant storage from the final schema and management exports.
- [x] 5.5 Add management-only repository health and JSON diagnostic/export queries, corruption/migration failure reporting, size/page limits, and tests proving export is read-only and SQLite remains the sole authority.

## 6. HR Agent Directory And Introduction Workflow

- [x] 6.1 Implement `app/services/hr_directory.py` roster reconciliation across system, project, external, and synthetic Agents, with HR self-exclusion from report/assessment eligibility and tests for duplicate sources, changed names, unavailable providers, inactive states, and reactivation.
- [x] 6.2 Implement introduction request claiming and HR-to-Agent conversation orchestration with deterministic conversation keys, raw response preservation, neutral no-response, per-Agent failure isolation, and injected fake-conversation tests.
- [x] 6.3 Implement HR structured introduction summarization, schema validation, provenance/version persistence, stale-role clarification, and conflict-safe replacement with tests for valid, malformed, unsupported, missing, and changed self-descriptions.
- [x] 6.4 Implement safe directory projections containing only name, introduction, AI ID, availability, and readiness; add pagination/filtering and tests that reports, evidence, assessments, grants, and sensitive metadata never enter the directory view.

## 7. Built-in Agent HR Skill

- [x] 7.1 Create the canonical `skills/vo-agent-hr/SKILL.md`, register it in the VO built-in catalog and Agent Guide, cover safe roster lookup, controlled Agent lookup, self access-log lookup, trusted VO identity headers, and prohibited direct storage/management access, and add static content and endpoint-contract tests.
- [x] 7.2 Extract the existing builtin skill seeding into a generic managed-skill registry that preserves current communication-skill behavior, ownership markers, hashes, atomic replacement, legacy conflict handling, symlink protection, and all existing tests.
- [x] 7.3 Expose the canonical Agent HR Skill only through the current VO `/skills` catalog and Agent Guide, route matching intents from the VO operating guidelines, and add static tests proving HR runtime code never installs it into Agent workspaces.
- [x] 7.4 Use the trusted VO-internal interaction model for Agent HR queries: require loopback, no browser Origin, the HR action header, and a registered active self-declared AI ID without bearer credentials or Provider restrictions.
- [x] 7.5 Wire directory reconciliation independently of Provider credential readiness and verify OpenClaw, Hermes, Codex, Claude Code, and future registered Providers remain equally query-capable.
- [x] 7.6 Remove obsolete HR grant issuance/delivery runtime modules and per-Agent Skill/API authorization readiness projections.

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
- [x] 11.3 Implement trusted VO Agent identity validation requiring loopback, no browser Origin, Human Resources action header, and a known active self-declared AI ID without bearer or Provider checks; cover missing, unknown, inactive, browser-originated, and remote callers.
- [x] 11.4 Implement Agent directory, cross-Agent public detail, and self access-log application queries; commit exactly one access record before successful cross-Agent disclosure, exempt HR/human routes, and fail closed when audit persistence fails.
- [x] 11.5 Add thin `OfficeHandler` route delegation for all Human Resources management and Agent endpoints, reuse `managementFetch` challenge semantics, set minimal CORS/allowed headers, normalize errors, and add HTTP contract/security tests.

## 12. Human Resources User Experience

- [x] 12.1 Add `app/human-resources.css`, the first-level Human Resources toolbar entry, independent modal shell, script/style registration, and responsive list/detail layout without coupling to Archive Room JavaScript state.
- [x] 12.2 Implement `app/human-resources.js` management-token overview loading and rendering for HR state, Agent availability totals, daily status counts, recent activity, unresolved/failed prioritization, loading, empty, and degraded states with pure-helper Node tests.
- [x] 12.3 Implement Agent detail rendering for identity/provenance, raw versus normalized reports, assessment versions, workload history, evidence, blockers, improvements, workflow state, and authorized access history with pagination and stale-request protection.
- [x] 12.4 Implement HR pause/resume and cycle run/close/retry controls with confirmation, busy/error feedback, scroll/state preservation, and tests proving existing data remains browsable while HR is paused or failed.
- [x] 12.5 Add complete English/Chinese localization, accessible labels, focus/keyboard/close behavior, semantic state labels, and localization-integrity/static JavaScript checks for every Human Resources workflow and error state.
- [x] 12.6 Add a deterministic browser acceptance fixture and script covering first-level navigation, HR lifecycle, roster/detail, daily statuses, assessment separation, access history, pagination, pause/resume, and partial/degraded failures.
- [x] 12.7 Remove the duplicate modal-header lifecycle badge and add a management-only active Agent-team synchronization control backed by forced roster discovery, Provider-neutral directory reconciliation, UI refresh, and focused service/API/UI/browser tests.
- [x] 12.8 Show the next daily-report collection time in the HR overview using a server-calculated VO-timezone schedule projection with scheduled, due-for-catch-up, and scheduler-disabled states; cover API, localization, pure UI, and browser rendering.
- [x] 12.9 Add a separate management-only `补充信息` action that asynchronously asks only available non-HR Agents with missing introduction text, directly summarizes already received responses, isolates per-Agent failures, prevents duplicate concurrent runs, records bounded activity, aligns the versioned HR Profile introduction contract with the strict evidence-validating parser, and covers service/API/HTTP/UI/browser contracts.
- [x] 12.10 Add a management-only `日报` correction action with an available-Agent select-all/individual dialog, bounded single-flight execution, explicit same-date report replacement and revision, immediate selected-Agent reassessment with prior-version retention, failure-safe preservation of existing data, and focused repository/service/API/HTTP/UI tests.
- [x] 12.11 Add versioned JSON request contexts and exact preferred JSON response templates to introduction and scheduled/manual daily-report questions, retain a natural-language Provider fallback with raw-response preservation, align HR Profile normalization/assessment examples with strict runtime parsers, and cover prompt identity/date/schema escaping and compatibility paths with focused tests.
- [x] 12.12 Persist accepted/processing/complete/failed state for every asynchronous HR management command, make Agent-team synchronization asynchronous, expose active commands in the overview, poll and restore running state in the UI, and cover refresh persistence, single-flight, terminal replacement, API, localization, and UI helpers with focused tests.
- [x] 12.13 Extract one transport-neutral VO Agent communication application service, delegate the public HTTP route and HR introduction/daily workflows to the same service, preserve visible history and stable Provider failure codes, avoid loopback HTTP, and cover the service boundary with focused unit and routing regressions.
- [x] 12.14 Rename the built-in HR capability from `vo-agent-directory` to `vo-agent-hr`, adopt the trusted VO-internal caller-ID model, remove Provider grant delivery and HR authorization-readiness UI/API state, and cover every Provider, Skill, HTTP, audit, UI, and static boundary with focused tests.
- [x] 12.15 Permanently remove the obsolete `access_grants` table, Agent Skill/grant readiness columns, grant repository methods, and grant export surface; add a transactional schema-v3 cleanup migration and focused tests proving existing development databases lose the legacy rows while retaining Agent and HR records.
- [x] 12.16 Wire the automatic HR runtime end to end: reuse the shared periodic-timer interface, refresh the Agent roster, normalize accepted raw reports before assessment across normal/close/retry/restart paths, persist page-managed automatic enablement and `HH:MM` with an enabled `18:00` default, expose management API/UI controls, and cover failure isolation, dynamic updates, runtime wiring, HTTP, UI, and project-recurrence compatibility with focused tests.

## 13. Pre-Merge Regression Evidence

- [x] 13.1 Run and record focused Python/Node integration suites for shared lifecycle, HR repository/directory/skill/reporting/assessment/scheduler/governance/API/UI, resolving every failure without weakening specified assertions.
- [x] 13.2 Run and record Archive Room Phase 1–8, archive-manager Phase 4, Agent communication skill/routing, project assignment/actor, meeting lifecycle/service-boundary, provider, management-token, i18n, and static modularity regressions.
- [x] 13.3 Run live local browser acceptance with fake provider data and record screenshots/assertions for the Human Resources happy path, permissions, partial failures, and degraded-read path.

## 14. Agent Configuration Authority And Mutation Security

- [x] 14.1 Inventory every Agent, office-config, Agent-workspace, Provider, branch, assignment, binding, create, and delete mutation route; record its current actor check, persistence authority, callers, and required keep/delegate/read-only/remove disposition, and add characterization tests before changing behavior.
- [x] 14.2 Implement `app/services/agent_profile_store.py` as the atomic revisioned owner of editable Agent profile and appearance fields, including stable-AI-ID lookup, bounded normalization, legacy office-config/`role` compatibility reads, atomic persistence, migration behavior, and focused concurrency/failure tests.
- [x] 14.3 Implement `app/services/agent_profile_configuration.py` with explicit human/Agent actor types, self/full mutation allowlists, one-field commands, `expectedRevision` conflict handling, responsibility/specialty descriptive semantics, HR-directory reconciliation ports, and exhaustive policy tests without importing `server.py`.
- [x] 14.4 Implement low-risk name, introduction, responsibility, specialty, and appearance mutation APIs that return per-field save state, the new revision, and a single-use 30-second server inverse token; implement revision-checked undo and tests for expiry, replay, conflict, malformed values, partial failure, and later-edit preservation.
- [x] 14.5 Implement server-issued high-risk confirmation challenges bound to actor, stable AI ID, action, normalized before/after digest, revision, and expiry for Provider, branch, workspace, assignment, binding, create, and delete operations; reject boolean-only confirmation, replay, payload substitution, stale revision, and expired challenges.
- [x] 14.6 Route every retained legacy mutation entry through management authorization and the same configuration/high-risk policy, or make it read-only/remove it according to the inventory; add direct-route negative tests proving the merged UI cannot be bypassed.
- [ ] 14.7 Add thin `OfficeHandler` construction/delegation for the new configuration services and routes, keep validation/state transitions out of `app/server.py`, and add static boundary plus HTTP contract tests.

## 15. Short-Lived Agent Management Browser Sessions

- [ ] 15.1 Implement `app/services/agent_management_sessions.py` with bounded in-memory launch-code and session repositories, cryptographically random values, stored digests, single-use exchange, idle/absolute expiry, per-Agent/global caps, cleanup, restart invalidation, and injected clock/randomness tests.
- [ ] 15.2 Add an originless loopback Agent session-mint endpoint requiring `X-VO-Agent-Action: agent-management` and a registered active self-declared AI ID; add tests for remote, browser-Origin, missing action, unknown/inactive Agent, Provider-neutral identity, and rate/cap enforcement.
- [ ] 15.3 Add same-origin one-time exchange and redirect handling that removes the launch code from the URL and sets an opaque `HttpOnly`, `SameSite=Strict`, path-scoped cookie with no-store/referrer protections; reject replay, cross-origin/CSRF, malformed, expired, and restarted codes.
- [ ] 15.4 Add browser Agent Management session resolution that rechecks active directory state and exposes only server-projected self/public roster, detail, HR, access-history, and low-risk self-mutation routes; prove management-token and Agent-session authorities never upgrade or inherit one another.
- [ ] 15.5 Add security-focused HTTP/browser tests for simultaneous human and Agent sessions, Agent switching attempts, selected-roster spoofing, cookie scope, expiry/re-entry, logout/invalidation, audit success/failure, and absence of launch codes or cookies from logs, localStorage, Skill files, and workspaces.

## 16. Merged Agent Management User Experience

- [ ] 16.1 Add focused `app/agent-management.js` and `app/agent-management.css` modules owning one modal shell, one roster/selection store keyed by stable AI ID, peer `代理配置`/`人事运营` tabs, per-tab loading/error/scroll restoration, and one top-right `×`; replace the independent Human Resources toolbar/modal and duplicate return/close controls with thin compatibility delegates during migration.
- [ ] 16.2 Add focused `app/agent-configuration.js` and `app/agent-configuration.css` modules for audience-projected identity, introduction, responsibility/specialty, appearance, assignment, Provider, branch, workspace, and binding views; keep restricted controls absent for Agents and migrate old `_acp*` rendering/state out of `app/game.js`.
- [ ] 16.3 Implement field-level automatic-save UI behavior: committed categorical edits save immediately, text edits use a short debounce, each field renders saving/saved/conflict/denied/failed state, successful edits expose bounded undo, and no global Agent configuration Save button remains.
- [ ] 16.4 Implement compact keyboard-accessible visual selectors for hair, clothing, accessories, glasses, held/desktop items, and other categorical appearance fields; preserve visible color swatches/palettes, focus management, current-value indication, preview updates, popover close-after-select, save feedback, and undo.
- [ ] 16.5 Refactor `app/human-resources.js` into an embeddable panel with explicit roster/selection/audience/data-adapter inputs, preserve background command polling and detail state, and render full human versus governed Agent public/self projections without reading Agent configuration globals.
- [ ] 16.6 Implement separate human and Agent data adapters: humans use `managementFetch`; Agents use only the scoped Agent Management session routes; both keep the same two-tab navigation while Agent HR views omit commands, assessment evidence, unrelated access history, and all restricted mutations.
- [ ] 16.7 Add confirmed high-risk interaction UI with Agent/action/before/after impact text and server challenge submission; cover stale/rejected confirmation, create/delete, Provider, branch, workspace, assignment, and binding outcomes without reintroducing a generic save button.
- [ ] 16.8 Complete English/Chinese localization, accessible tab/dialog/popover/status semantics, responsive layout, reduced-motion/focus behavior, and compatibility cleanup; remove obsolete independent HR modal and old `_acp*` implementation only after all callers and tests use the new modules.
- [ ] 16.9 Add pure Node/component tests and a deterministic local browser fixture covering shared selection and tab state, human/Agent projections, auto-save/undo/conflict, selector keyboard behavior, high-risk confirmation, asynchronous HR command restoration, empty/degraded states, unique close control, and absence of hidden restricted data in DOM/network fixtures.

## 17. Automated Integrated Regression

- [ ] 17.1 Run and record focused Python tests for profile store/configuration policy, undo, confirmation challenges, legacy-route hardening, Agent session mint/exchange/resolution, HR projections/audit, and thin HTTP delegation; resolve every failure without weakening specified assertions.
- [ ] 17.2 Run and record focused Node/static/browser tests for the merged shell, configuration panel, Human Resources embedding, localization, accessibility, modularity, and prohibition on new Agent Management logic in `app/game.js` or `app/server.py`.
- [ ] 17.3 Run and record Archive Room Phase 1–8, archive-manager Phase 4, meetings, projects, Agent workspace, Agent create/delete, Provider/binding, communication Skill, management-token, existing HR, i18n, and server/service-boundary regressions.
- [ ] 17.4 Run local live-browser acceptance with deterministic fake Provider data for human authentication, Agent session exchange, both tabs, self/public/full disclosure, auto-save/undo, high-risk denial/confirmation, HR asynchronous commands, partial failures, degraded reads, and restart-invalidated session behavior; save assertions and screenshots as supporting evidence only.

## 18. Development-Machine End-To-End Regression Gate

- [ ] 18.1 Identify and document the approved development-machine target, deployment/start commands, VO and OpenClaw versions, configuration values, backup location, test Agent identities, browser entry method, feature-switch sequence, expected evidence paths, and rollback commands before any real-environment mutation.
- [ ] 18.2 Deploy the exact reviewed source to the development machine with `VO_HR_ENABLED=0` and the persisted automatic schedule disabled; from the browser capture a clean pre-enable baseline for Agent Management, Agent configuration, Agent workspace, Archive Room, projects, meetings, Providers, and existing Agent create/delete behavior.
- [ ] 18.3 Enable HR lifecycle and directory in stages; from the merged human UI verify management authentication, real OpenClaw HR auto-create/uniqueness/rediscovery/Profile repair, office visibility, pause/resume, Agent-team synchronization, missing-information completion, `vo-agent-hr` exposure, HR meeting eligibility, archive-manager isolation, and persisted refreshed projections.
- [ ] 18.4 From a real registered Agent, mint and exchange an Agent Management launch code and verify the same two-tab UI defaults to self, permits self low-risk auto-save and revision-checked undo, returns only public data for a colleague with audit evidence, denies identity switching and restricted fields/actions, expires/re-enters correctly, and never exposes human-only assessment evidence or HR commands.
- [ ] 18.5 From the authenticated human UI, execute representative Provider, branch, workspace, assignment, binding, create, and delete high-risk flows; verify impact text and server challenge binding, direct legacy-route denial without authorization, real downstream persistence, and refreshed roster/configuration state.
- [ ] 18.6 Run a controlled short daily cycle from browser-visible HR actions and trace stable command IDs through accepted/processing/terminal states, real HR-to-Agent communication, raw and normalized reports, non-response/late submission, evidence, assessment/insufficient-information, partial failure isolation, durable persistence, and final refreshed UI.
- [ ] 18.7 Restart VO and OpenClaw during or after controlled Agent configuration and HR work; verify profile/report/assessment persistence, lifecycle and claim recovery, duplicate prevention, launch/session invalidation and re-entry, final UI state, Archive Room, meetings, projects, and existing VO workflows.
- [ ] 18.8 Rehearse rollback in the approved order by disabling the automatic schedule and then HR, allowing claims to settle or expire, retaining HR data and Agent identity/configuration, proving existing VO and Archive Room remain operational, and recording restoration steps and outcomes.
- [ ] 18.9 Assemble the E2E evidence package with machine and version identifiers, source revision, switches/configuration, browser actions, screenshots or recording, HTTP/command/log correlation, persisted outcomes, failures/fixes/retries, restart and rollback results, and explicit uncovered scenarios; do not infer missing E2E coverage from lower-level tests.
- [ ] 18.10 Run final strict OpenSpec validation and specification-to-test traceability review, then prepare the separate test-result confirmation package without archiving the change.
