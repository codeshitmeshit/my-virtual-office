# Task 9.3 Focused Regression Evidence

## Scope

Focused verification for stage-pipeline orchestration across storage, materialization, command, lifecycle, review, schedule, realtime, chat, frontend, security, and visual behavior.

## Passing Commands

- `.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py tests/test_project_materialization.py tests/test_project_materialization_boundaries.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_authoring_direct_create.py tests/test_project_authoring_service.py tests/test_project_authoring_validation.py tests/test_project_templates.py`
  - Result: `98 passed in 12.20s`.
- `.venv/bin/python -m pytest -q tests/test_project_orchestration.py tests/test_project_orchestration_commands.py tests/test_project_stage_dispatch.py tests/test_project_orchestration_http.py tests/test_project_stage_start_server.py tests/test_project_orchestration_pause.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_recovery.py tests/test_project_orchestration_observability.py`
  - Result: `110 passed in 3.23s`.
- `.venv/bin/python -m pytest -q tests/test_execution_lifecycle.py tests/test_review_acceptance_service.py tests/test_project_scheduled_cron_phase2_3.py tests/test_project_scheduled_cron_phase4.py tests/test_project_recurrence_occurrences.py tests/test_dashboard_realtime.py tests/test_project_execution_dashboard_status.py tests/test_project_workflow_chat.py tests/test_agent_workspace_project_context.py`
  - Result: `81 passed in 52.66s`.
- `node tests/check_project_orchestration_modal.mjs && node tests/check_project_orchestration_api_contract.mjs && node tests/check_project_orchestration_page_wiring.mjs && node tests/check_project_marked_frontend_legacy_fields.mjs && node tests/check_project_marked_legacy_start_removed.mjs && node tests/check_project_orchestration_visual_snapshot.mjs`
  - Result: passed.
  - Visual snapshot: `openspec/changes/add-project-task-orchestration/evidence/figma/candidate-8.8-orchestration-overlay.png`.
  - Measured geometry: viewport `1512x742`, modal `1220x560`, canvas `1184x350`, `taskCount=9`, `stageCount=5`, `connectorCount=4`, `saveButtonCount=0`.
- `.venv/bin/python -m pytest -q tests/test_project_commands.py tests/test_project_execution_legacy_characterization.py`
  - Result: `24 passed in 0.38s`.
- `.venv/bin/python -m pytest -q tests/test_project_orchestration_http.py -k 'auth or token or forbidden or management or stale or authorization'`
  - Result: `10 passed, 9 deselected in 1.30s`.
- `git diff --check -- app project-orchestration.js tests openspec/changes/add-project-task-orchestration`
  - Result: passed.

## Recorded Failure

- `.venv/bin/python -m pytest -q tests/test_project_commands.py tests/test_project_execution_legacy_characterization.py tests/test_server_routes_module_split.py`
  - Result: `3 failed, 34 passed in 1.60s`.
  - Failed tests:
    - `tests/test_server_routes_module_split.py::test_agents_route_uses_agents_service_compatibility`
    - `tests/test_server_routes_module_split.py::test_config_route_uses_config_runtime_service_compatibility`
    - `tests/test_server_routes_module_split.py::test_browser_route_uses_browser_runtime_service_compatibility`
  - Failure shape: the route split compatibility tests expected `_handle_agents_list`, `_handle_health`, and `_handle_browser_status` attributes on `server.py`.
  - Assessment: this is outside the project-task orchestration focused path covered by task 9.3, but it is recorded for follow-up regression gating in task 9.4.

## OpenSpec CLI Availability

OpenSpec CLI remains unavailable in this environment:

- `openspec status --change add-project-task-orchestration --json`
  - Result: `openspec: command not found`.
- `openspec instructions apply --change add-project-task-orchestration --json`
  - Result: `openspec: command not found`.
- `npx --yes @openspec/cli validate add-project-task-orchestration --strict`
  - Result: npm 404, package not found.
- `npx --yes openspec validate add-project-task-orchestration --strict`
  - Result: npm could not determine executable to run.

## Unverified Scenarios

- Real AI project creation and live browser end-to-end acceptance are reserved for manual acceptance tasks 10.4 and 10.5.
- Complete all-repository regression and OpenSpec strict validation are reserved for task 9.4, pending a working OpenSpec CLI entry.

