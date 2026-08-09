# Task 10.6 final validation and traceability

Date: 2026-07-27
Change: `add-project-task-orchestration`
Task: `10.6 Run final openspec validate --strict, attach test and release evidence, and verify every confirmed requirement and scenario is traceable to completed tasks before requesting test-result confirmation.`

## OpenSpec Strict Validation

Command:

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result:

```text
Change 'add-project-task-orchestration' is valid
```

## Final Test Evidence

Python focused final regression:

```bash
.venv/bin/python -m pytest -q tests/test_project_authoring_direct_create.py tests/test_project_authoring_validation.py tests/test_project_authoring_http_contract.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_orchestration_store.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py tests/test_project_orchestration_http.py tests/test_project_orchestration_concurrency.py tests/test_project_orchestration_recovery.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_pause.py tests/test_project_orchestration_observability.py tests/test_project_orchestration_css.py tests/test_project_orchestration_release_preflight.py tests/test_project_orchestration_release_rehearsal.py tests/test_project_schedule_service.py tests/test_project_recurrence_execution.py tests/test_project_execution_legacy_characterization.py tests/test_project_materialization.py tests/test_project_materialization_boundaries.py tests/test_project_materialization_characterization.py tests/test_project_commands.py tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py tests/test_dashboard_realtime.py tests/test_project_workflow_chat.py tests/test_project_templates.py
```

Result:

```text
267 passed in 63.55s (0:01:03)
```

JavaScript project-orchestration and AI-facing contract checks:

```bash
node tests/check_project_orchestration_modal.mjs
node tests/check_project_orchestration_api_contract.mjs
node tests/check_project_orchestration_page_wiring.mjs
node tests/check_vo_project_authoring_skill.mjs
node tests/check_project_marked_legacy_start_removed.mjs
node tests/check_project_marked_frontend_legacy_fields.mjs
```

Results:

- `project orchestration modal runtime contract ok`
- `project orchestration API contract checks passed`
- `project orchestration page wiring checks passed`
- `VO project authoring skill contract passed`
- `marked project legacy start removal checks passed`
- `marked project frontend legacy-field checks passed`

Final visual snapshot:

```bash
VO_CDP_URL=http://127.0.0.1:9334 node tests/check_project_orchestration_visual_snapshot.mjs
```

Result: passed and regenerated `openspec/changes/add-project-task-orchestration/evidence/figma/candidate-8.8-orchestration-overlay.png`.

Measured highlights:

- viewport: `1512x742`
- overlay: `0,0,1512x742`
- modal: `x=146,y=91,width=1220,height=560`
- canvas: `x=164,y=228,width=1184,height=350`
- tasks/stages/connectors: `9/5/4`
- save button count: `0`
- modal/canvas colors match the Figma-derived tokens

## Final Release Evidence

Read-only release preflight:

```bash
.venv/bin/python scripts/project_orchestration_release_preflight.py --status-dir /root/home/cosh/my-virtual-office/data
```

Result summary:

- `canonicalProjectCount: 1`
- `legacyDeletionCandidateCount: 0`
- `readErrorCount: 0`
- current real project `project-9cf16b05-7593-40f0-ad99-a02e98404703` has `executionModel: stage_pipeline_v1` and 3 tasks.
- `destructiveActionsPerformed: []`

Release/rollback rehearsal:

```bash
.venv/bin/python scripts/project_orchestration_release_rehearsal.py --status-dir /root/home/cosh/my-virtual-office/data --backup-dir /root/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z
```

Result summary:

- `ok: true`
- backend compile: `ok: true`
- frontend assets present: `project-orchestration.css`, `project-orchestration-api.js`, `project-orchestration.js`
- new project smoke: `executionModel: stage_pipeline_v1`, `orchestrationState: draft`, stages `[1, 2]`, no forbidden fields
- pre-mutation invariant: `ok: true`, `markedProjectCount: 1`
- post-smoke invariant: `ok: true`, `markedProjectCount: 2`
- service stop: `startedHealthy: true`, `stopped: true`, `postStopConnectionRefused: true`
- previous code restore resolved `HEAD^` to `b2b66e21a4d3214a67be8d7bc5c5de5533137a53`
- project-store restore sandbox recovered the 10.2 backup and reported the three legacy deletion candidates as expected

## Requirement And Scenario Traceability

### project-task-orchestration

| Requirement | Scenarios | Traceable Tasks | Evidence And Tests |
| --- | --- | --- | --- |
| Marked new projects use mandatory orchestration | A new project is created; a marked project contains an unassigned task; legacy project data is prepared for release | 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 10.2, 10.3, 10.4 | `task-1.4-release-preflight.md`, `task-2.1-project-orchestration-model.md`, `task-2.2-markdown-store-round-trip.md`, `task-2.3-canonical-materialization.md`, `task-2.4-creation-source-parity.md`, `task-2.5-authoring-validation-template-snapshots.md`, `task-10.2-preflight-awaiting-cleanup-approval.md`, `task-10.3-release-rollback-rehearsal.md`, `task-10.4-manual-acceptance.md`; tests: authoring/materialization/orchestration store/validation/release preflight/rehearsal |
| Figma-aligned orchestration workspace | Orchestration modal is rendered; visual acceptance is performed; modal footer is rendered | 8.1, 8.2, 8.3, 8.6, 8.7, 8.8, 10.5 | `task-8.1-figma-reference-capture.md`, `task-8.2-figma-css-shell.md`, `task-8.3-isolated-modal-runtime.md`, `task-8.6-project-page-wiring.md`, `task-8.7-dom-runtime-tests.md`, `task-8.8-visual-screenshot-test.md`, `task-10.5-final-figma-visual-acceptance.md`; tests: `check_project_orchestration_modal.mjs`, `check_project_orchestration_page_wiring.mjs`, `check_project_orchestration_visual_snapshot.mjs`, `test_project_orchestration_css.py` |
| Orchestration edits auto-save | A task is moved between stages; persistence rejects an edit | 3.1, 3.3, 3.4, 8.4, 10.4 | `task-3.1-orchestration-autosave-command.md`, `task-3.3-orchestration-put-route.md`, `task-3.4-api-client-contract-tests.md`, `task-8.4-drag-add-autosave.md`, `task-10.4-manual-acceptance.md`; tests: orchestration commands/http/concurrency/API contract/modal runtime |
| Stage numbering remains complete and contiguous | A new task is added; the last task leaves a stage; multiple tasks share a stage | 2.1, 3.1, 3.2, 8.4 | `task-2.1-project-orchestration-model.md`, `task-3.1-orchestration-autosave-command.md`, `task-3.2-task-create-delete-structural-edits.md`, `task-8.4-drag-add-autosave.md`; tests: orchestration model/commands/http/store/modal runtime |
| Explicit project start locks orchestration | An owner starts a valid project; a user only edits orchestration | 4.2, 4.3, 4.4, 7.5, 8.5, 10.4 | `task-4.2-stage-preflight-reservation.md`, `task-4.3-reserved-task-attempt-preparation.md`, `task-4.4-marked-project-start.md`, `task-7.5-legacy-start-removal.md`, `task-8.5-orchestration-state-controls.md`, `task-10.4-manual-acceptance.md`; tests: stage dispatch/start server/orchestration http/legacy removal checks |
| Stages execute in order and tasks within a stage execute in parallel | A stage becomes active; one parallel task remains unfinished; a non-final stage finishes | 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 10.4 | `task-4.1-bounded-dispatcher.md`, `task-4.2-stage-preflight-reservation.md`, `task-4.3-reserved-task-attempt-preparation.md`, `task-4.4-marked-project-start.md`, `task-4.5-queue-rejection-partial-submission.md`, `task-5.1-stage-reconciliation.md`, `task-5.2-terminal-callback-reconciliation.md`, `task-10.4-manual-acceptance.md`; tests: stage dispatch/start server/concurrency/recovery |
| Exceptions pause advancement and skips require approval | A task fails or becomes blocked; a responsible actor requests a skip; a skip is approved; a skip is rejected | 4.5, 5.1, 5.2, 5.3, 5.4, 9.1, 10.4 | `task-4.5-queue-rejection-partial-submission.md`, `task-5.1-stage-reconciliation.md`, `task-5.2-terminal-callback-reconciliation.md`, `task-5.3-orchestration-skip-commands.md`, `task-5.4-skip-api-delegates.md`, `task-9.1-concurrency-regressions.md`, `task-10.4-manual-acceptance.md`; tests: skip/http/concurrency/stage dispatch |
| Paused projects can be re-orchestrated without rewriting completed history | Re-orchestration is requested during execution; the revised pipeline is edited; the revised pipeline resumes | 6.1, 6.2, 6.3, 6.4, 6.5, 8.5, 10.4 | `task-6.1-phase-one-pause.md`, `task-6.2-phase-two-pause-cancellation.md`, `task-6.3-paused-editing-resume.md`, `task-6.4-pause-resume-routes.md`, `task-6.5-startup-recovery.md`, `task-8.5-orchestration-state-controls.md`, `task-10.4-manual-acceptance.md`; tests: pause/recovery/concurrency/orchestration http |
| Final stage completion completes the project | The final stage reaches accepted terminal outcomes; human acceptance is required | 5.1, 5.2, 5.5, 10.4 | `task-5.1-stage-reconciliation.md`, `task-5.2-terminal-callback-reconciliation.md`, `task-5.5-final-project-completion.md`, `task-10.4-manual-acceptance.md`; tests: stage dispatch/start server/review acceptance |

### project-execution-service-boundaries

| Requirement | Scenarios | Traceable Tasks | Evidence And Tests |
| --- | --- | --- | --- |
| Project and task behavior compatibility | A marked project or task operation is delegated; invalid project/task input is submitted; an unmarked legacy project is encountered before release | 1.1, 1.2, 2.1, 2.2, 2.5, 3.2, 7.4, 10.2, 10.3 | `task-1.1-removal-inventory.md`, `task-1.2-overlap-contracts.md`, `task-2.1-project-orchestration-model.md`, `task-2.2-markdown-store-round-trip.md`, `task-2.5-authoring-validation-template-snapshots.md`, `task-3.2-task-create-delete-structural-edits.md`, `task-7.4-legacy-field-removal.md`, `task-10.2-preflight-awaiting-cleanup-approval.md`, `task-10.3-release-rollback-rehearsal.md`; tests: materialization/project commands/orchestration validation/release preflight |
| Execution lifecycle invariants | Eligible stage execution starts; one task fails its execution gate; Git workspace snapshot fails; workspace is not a Git repository; provider execution fails | 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 9.1, 9.2 | `task-4.1-bounded-dispatcher.md`, `task-4.2-stage-preflight-reservation.md`, `task-4.3-reserved-task-attempt-preparation.md`, `task-4.4-marked-project-start.md`, `task-4.5-queue-rejection-partial-submission.md`, `task-5.1-stage-reconciliation.md`, `task-5.2-terminal-callback-reconciliation.md`, `task-9.1-concurrency-regressions.md`, `task-9.2-observability.md`; tests: execution lifecycle/stage dispatch/start server/orchestration observability |
| Scheduling and recovery compatibility | A scheduled marked project becomes due; scheduler evaluates a later-stage task; application restarts with an active marked project | 6.5, 7.1, 9.1, 10.4 | `task-6.5-startup-recovery.md`, `task-7.1-scheduling-marked-pipelines.md`, `task-9.1-concurrency-regressions.md`, `task-10.4-manual-acceptance.md`; tests: schedule service/recurrence execution/recovery/concurrency |
| API, event, and storage compatibility | A retained project execution contract is exercised; a removed progression contract is exercised; project state is persisted | 2.2, 3.3, 3.4, 7.2, 7.3, 7.4, 7.6, 8.6, 10.4 | `task-2.2-markdown-store-round-trip.md`, `task-3.3-orchestration-put-route.md`, `task-3.4-api-client-contract-tests.md`, `task-7.2-projection-fields.md`, `task-7.3-workflow-chat-task-scope.md`, `task-7.4-legacy-field-removal.md`, `task-7.6-storage-route-contract.md`, `task-8.6-project-page-wiring.md`, `task-10.4-manual-acceptance.md`; tests: orchestration http/API contract/dashboard realtime/workflow chat/storage route contract |
| Obsolete execution-mode authorities are removed | A marked project is materialized; a retained caller references an obsolete property; removal is verified | 1.1, 1.3, 2.3, 2.4, 2.5, 7.4, 7.5, 7.6, 9.3, 10.4 | `task-1.1-removal-inventory.md`, `task-1.3-legacy-characterization-tests.md`, `task-2.3-canonical-materialization.md`, `task-2.4-creation-source-parity.md`, `task-2.5-authoring-validation-template-snapshots.md`, `task-7.4-legacy-field-removal.md`, `task-7.5-legacy-start-removal.md`, `task-7.6-storage-route-contract.md`, `task-9.3-focused-regression.md`, `task-10.4-manual-acceptance.md`; tests: legacy characterization/static legacy removal/marked frontend legacy-field checks/authoring validation |

## Residual Gates And Notes

- Generic full-suite pytest collection remains unsuitable as a release signal without environment setup because root-level standalone scripts and live-service/provider tests have collection/runtime prerequisites. This was recorded in `task-9.4-complete-regression.md`.
- The final 10.6 regression command intentionally selects the project-orchestration, authoring, lifecycle, schedule, realtime, chat, materialization, release, and visual suites that directly cover the confirmed change.
- Real browser and real Agent direct-create acceptance are recorded in `task-10.4-manual-acceptance.md`.
- Final Figma visual acceptance is recorded in `task-10.5-final-figma-visual-acceptance.md`.
