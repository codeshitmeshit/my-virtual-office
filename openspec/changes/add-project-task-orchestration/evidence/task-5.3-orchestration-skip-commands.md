# Task 5.3 Evidence: Orchestration Skip Commands

## Scope

- Added `app/services/project_orchestration_skip.py` as a focused repository-backed command module.
- Added `request_task_skip(...)` for responsible task actors to request a skip with a required reason.
- Added `decide_task_skip(...)` for management-authorized approve/reject decisions.
- Kept orchestration skip state in `task.orchestrationSkip`; review skip remains `reviewResult.status == "skipped"` and is not reused as an orchestration terminal outcome.
- Added bounded `orchestrationSkipHistory` audit entries for request, approve, reject, and idempotent repeat decisions.
- Approved current-stage skips trigger `reconcile_stage(...)`; rejected skips do not count as terminal.

## Tests Added

- `test_task_responsible_actor_can_request_skip_with_audit_history`
- `test_skip_request_rejects_non_responsible_actor_and_review_skipped_is_not_terminal_skip`
- `test_management_approval_marks_skip_accepted_terminal_and_reconciles_current_run`
- `test_skip_rejection_is_audited_and_does_not_reconcile`
- `test_skip_decision_requires_management_authority_and_pending_request`
- `test_approved_skip_decision_is_idempotent_without_second_reconcile`

## Verification

```bash
.venv/bin/pytest -q tests/test_project_orchestration_skip.py
```

Result: `6 passed in 0.20s`

```bash
.venv/bin/pytest -q tests/test_project_orchestration_skip.py tests/test_project_orchestration.py tests/test_project_stage_dispatch.py tests/test_project_stage_start_server.py
```

Result: `57 passed in 1.11s`

```bash
.venv/bin/python -m py_compile app/services/project_orchestration_skip.py
```

Result: passed with no output.
