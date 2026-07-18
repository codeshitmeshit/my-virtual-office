# Verification Evidence

## Task 10.5 — Conversation-confirmed direct creation

Run on 2026-07-18 from `/Users/bytedance/cosh/my-virtual-office` against implementation commit `785a0da` and its ancestors.

The prior Task 9.x sections below are retained as historical evidence for the original persisted-draft design. They are superseded by this section wherever they refer to request submission/status routes, draft review UI, pending-draft health, or confirmation-time materialization.

### Regression and contract results

- `.venv/bin/pytest -q tests/test_project*.py` — **319 passed in 11.00s**.
- `node tests/check_project_authoring_ui_removed.mjs` — passed.
- `node tests/check_vo_project_authoring_skill.mjs` — passed.
- `node tests/check_vo_project_authoring_docs.mjs` — passed.
- `node tests/check_agent_guide_static.mjs` — passed.
- `openspec validate add-agent-managed-vo-projects --strict` — passed.
- Live loopback reads of `/skills/index.md` and `/skills/vo-project-authoring/SKILL.md` exposed the natural-language confirmation flow and `POST /api/agent/project-authoring/projects` contract.

### Verification matrix

| Domain | Current evidence |
| --- | --- |
| Direct creation and confirmation assertion | `tests/test_project_authoring_direct_create.py` verifies explicit confirmation plus SHA-256 digest validation, complete aggregate creation, backlog state, and inactive workflow flags. |
| Security boundary | Agent HTTP tests verify loopback-only, no browser Origin, registered Agent/action headers, bounded bodies, identity matching, management-token separation, and hash-only grant persistence. |
| Idempotency and atomicity | Domain and HTTP tests verify same Agent/key/payload returns one project without reissuing `projectGrantSecret`; semantic reuse conflicts; workspace or root commit failure leaves no project, template, recurrence, outbox, grant, or idempotency residue. |
| Reviewer and actor policy | Validation/template tests preserve one responsible and executor actor per task, optional confirmed `reviewerActor`, explicit recommendation metadata, eligible-Agent checks, and trackable but non-executable `user:local` work. |
| No automatic execution | Direct domain and HTTP tests prove tasks begin in `backlog` with `workflowActive=false` and `projectExecutionFlowActive=false`; Project Execution boundary suites remain green. |
| Draft removal | The UI-removal checker proves the review assets, index wiring, and old browser tests are absent. Old Agent/management request paths have no active handlers; HTTP contract tests require removed writes to return 404 and retained GET tombstones to return `project_draft_route_removed`. |
| Skill and documentation | Static checks require proposal display before any API call, explicit confirmation, semantic-change reconfirmation/new key, reviewer default-none behavior, one-time in-memory grant handling, no management token, no auto execution, and the accepted unsigned provider-neutral chat limitation. |
| Templates, recurrence, and legacy cron | Direct recurring creation atomically writes its immutable template, recurrence, and outbox. Template compatibility, recurrence claim/deduplication/reconciliation, and all legacy `projectWorkflow`/`projectTask` schedule phases pass. |
| Maintenance and grant lifecycle | End-to-end HTTP tests preserve strict-confirmation versus assigned-task autonomous boundaries plus management-authenticated grant rotate/revoke and Agent/project scope. |
| Observability | Health ignores inert legacy `projectAuthoringRequests`, keeps credential-safe counters/alerts, and degrades on recurrence outbox age rather than pending draft age. |
| Flag-off and rollback compatibility | Configuration tests keep authoring and recurrence disabled by default and read at action time. Store/repository tests round-trip legacy root metadata and conservative project/template defaults without deleting old request records. |

### Current rollout conclusion

The supported authoring path is now: present the full natural-language proposal, wait for explicit confirmation of that version, compute its digest, and directly create one real but unstarted project. There is no active backend draft lifecycle or draft review UI. Existing `projectAuthoringRequests` data remains inert compatibility metadata, and disabling the authoring flag stops new writes without requiring a data down-migration.

## Task 9.2 — Focused verification matrix

Run on 2026-07-18 from `/Users/bytedance/cosh/my-virtual-office` against implementation commit `805e7e6` and its ancestors.

Aggregate command: `.venv/bin/pytest -q` over the focused files listed below.

Result: **145 passed in 2.50s**.

| Verification domain | Test files | Result |
| --- | --- | --- |
| Project commands | `tests/test_project_commands.py` | 7 passed |
| Repository and bounded root storage | `tests/test_project_repository.py`, `tests/test_project_authoring_store.py` | 27 passed |
| Management-token boundary | `tests/test_project_authoring_http_management.py`, `tests/test_project_authoring_http_contract.py` | 13 passed |
| Request-secret boundary | `tests/test_project_authoring_http_agent.py`, `tests/test_project_authoring_security.py` | 4 passed |
| Project Execution actor eligibility | `tests/test_project_execution_actor_eligibility.py` | 3 passed |
| Versioned templates and compatibility | `tests/test_project_templates.py`, `tests/test_project_template_compatibility.py` | 6 passed |
| Schedule and legacy cron behavior | `tests/test_project_schedule_service.py`, `tests/test_project_scheduled_cron_phase1.py` through `phase5.py` | 37 passed |
| Capacity limits and disabled flags | `tests/test_project_authoring_config.py` | 4 passed |
| Counters, durations, logs, health, queue age, alerts | `tests/test_project_authoring_observability.py` | 3 passed |
| Authoring service, validation, and audit | `tests/test_project_authoring_service.py`, `tests/test_project_authoring_validation.py`, `tests/test_project_authoring_audit.py` | 41 passed |

Every domain was also rerun separately; all results above passed with no retry or deselection. The management HTTP group includes the authenticated health endpoint and verifies that secret hashes and claim tokens are absent from its response. The request-secret group verifies hash-only persistence and request/Agent scope. The execution-role group verifies that local-user execution remains trackable but cannot start automated execution.

## Task 9.3 — Compatibility and end-to-end verification

Run on 2026-07-18 after Task 9.2:

- `.venv/bin/pytest -q tests/test_project*.py` — **317 passed in 11.46s**.
- `node tests/check_project_authoring_review_static.mjs` — passed.
- `node tests/test_project_authoring_review_browser.mjs` — passed.
- `node tests/check_vo_project_authoring_skill.mjs` — passed.
- `node tests/check_vo_project_authoring_docs.mjs` — passed.

The Python suite includes legacy markdown writer/repository characterization, all five scheduled-cron phases, browser-template compatibility, and the isolated Agent/management HTTP contract. `test_confirm_materializes_complete_project_once_without_starting_execution` proves repeated confirmation returns the same project, persists exactly one complete project/task aggregate, leaves `workflowActive` and `projectExecutionFlowActive` false, and leaves the task in `backlog`. The cron suites continue to use the legacy target kinds while recurrence tests use the new `projectTemplateInstance` target independently.

The standalone `tests/test_workflow_e2e.py` was also attempted, but its import-time call targets the already-running external VO without a management token and was correctly rejected with `management_token_required`. It was not counted as a product failure or as passing evidence; the reproducible authoring E2E uses isolated storage and an explicit trusted management token in `tests/test_project_authoring_http_contract.py`.

## Task 9.4 — Rollout rehearsal

The rollout selection below was run on 2026-07-18 and completed with **17 passed in 0.35s**:

```text
tests/test_project_authoring_config.py::test_features_are_disabled_by_default_and_read_at_action_time
tests/test_project_authoring_http_agent.py::test_agent_submission_is_loopback_only_originless_bounded_and_hash_only
tests/test_project_authoring_service.py::test_autonomous_assigned_agent_can_apply_only_routine_task_fields
tests/test_project_authoring_service.py::test_autonomous_routine_update_rejects_structural_and_role_fields
tests/test_project_authoring_service.py::test_autonomous_routine_update_rejects_strict_unassigned_and_revoked_grants
tests/test_project_authoring_service.py::test_recurring_confirmation_commits_template_recurrence_and_outbox_together
tests/test_project_authoring_http_contract.py::test_project_grant_rotation_revocation_and_scope_are_enforced
tests/test_project_recurrence_reconciler.py::test_reconciler_registers_bounded_batch_with_distinct_template_instance_binding
tests/test_project_recurrence_reconciler.py::test_disabled_paused_and_live_claim_states_do_not_call_gateway
tests/test_project_recurrence_reconciler.py::test_pause_and_resume_keep_gateway_binding_and_root_state_aligned
tests/test_project_store_authoring_metadata.py::test_repository_root_update_persists_authoring_metadata_across_store_instances
tests/test_project_store_authoring_metadata.py::test_legacy_projects_receive_conservative_authoring_defaults
```

Observed rollout gates:

| Stage | Observed gate/result |
| --- | --- |
| Flag-off deployment | Both features default off and are read at action time; disabled authoring returns stable `503 project_authoring_disabled` without mutation. |
| Local-only authoring | Non-loopback, browser-Origin, wrong action header, mismatched Agent, and oversized requests stop before service mutation. |
| Autonomous allowlist | Assigned Agent routine fields apply; structural/role fields, strict mode, unassigned Agent, and revoked grant remain blocked or pending confirmation. |
| Recurrence enablement | Confirmation durably commits the pinned template, recurrence, and outbox together; Gateway registration occurs only when recurrence is enabled and not paused. |
| Grant rotation/revocation | Rotation invalidates the old value and returns one replacement; revocation, cross-project, and cross-Agent use fail. |
| Outbox drain/pause | Bounded batches drain to one `projectTemplateInstance` binding; disabled/paused states make zero Gateway calls; pause/resume preserves and updates the existing binding. |
| Code rollback preparation | With both write flags off and dispatch paused, root metadata survives store re-open; legacy projects receive conservative defaults and remain readable. No data down-migration is required. |

Operational rollback order is: disable Agent authoring, pause recurrence dispatch, wait for current atomic writes to finish, capture `/api/project-authoring/health`, deploy the previous code, preserve the markdown root, and verify legacy project/cron reads before restoring traffic.

Unresolved/intentional limitations:

- The rehearsal did not replace the binary of the currently running user VO or execute a production Gateway job; those require the deployment owner and trusted management token. It exercised the same repository, HTTP boundary, and Gateway-port contracts in isolated storage.
- In-memory counters and duration aggregates reset on process restart. Durable queue/request/recurrence state, queue age, audit, and intervention alerts are reconstructed from the root.
- A lost request/grant secret cannot be recovered. The user must use the management surface, revoke, or rotate as applicable.
- Rollback preserves new root metadata but an older binary will not expose the new authoring UI/API; re-enabling requires returning to a compatible version.
