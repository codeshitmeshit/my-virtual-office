## Task 4.5 Evidence: Project/Workflow Regressions

Status: passed

Scope covered:
- Project execution prompt shape.
- Project execution review prompt shape.
- Workflow task/review/rework prompt shape.
- Checklist output expectations.
- Split-service hydration protection.

Verification:
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_project_execution_prompt_formatting.py tests/test_workflow_prompt_formatting.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q`
  - `15 passed`
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/projects.py app/server_services/workflow.py app/services/project_execution_prompt_formatting.py app/services/workflow_prompt_formatting.py tests/test_project_execution_prompt_formatting.py tests/test_workflow_prompt_formatting.py`
  - Passed.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Passed.

Review result:
- Prompt-only tests now target split service/main prompt functions.
- Runtime call sites no longer need the removed `server.py` project/workflow prompt wrappers.
- Hydration guardrails keep service-owned prompt helpers from being overwritten by legacy server names.
