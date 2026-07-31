## Task 4.4 Evidence: Project/Workflow Wrapper Removal

Status: passed

Changed files:
- `app/server.py`
- `tests/test_prompt_formatter_static.py`

What changed:
- Removed obsolete `server.py` project execution prompt wrappers:
  - `_project_execution_build_prompt`
  - `_project_execution_build_review_prompt`
- Removed obsolete `server.py` workflow prompt wrappers:
  - `_wf_build_project_context`
  - `_wf_build_task_prompt`
  - `_wf_build_review_prompt`
  - `_wf_build_rework_prompt`
- Kept runtime workflow dispatch in `server.py`, but changed prompt construction call sites to hydrate and call `server_services.workflow` directly.
- Removed no-longer-needed prompt formatting imports from `server.py`.
- Added the removed project/workflow wrapper names to the static removed-wrapper guardrail.

Verification:
- `rg "_project_execution_build_prompt\\(|_project_execution_build_review_prompt\\(|_wf_build_project_context\\(|_wf_build_task_prompt\\(|_wf_build_review_prompt\\(|_wf_build_rework_prompt\\(" app/server.py app/server_services -n`
  - `app/server.py` has no local definitions for these wrappers.
  - `app/server.py` runtime workflow call sites call `server_services.workflow` helpers.
  - Authoritative definitions remain in `app/server_services/projects.py` and `app/server_services/workflow.py`.
- `rg "server\\._(project_execution_build_prompt|project_execution_build_review_prompt|wf_build_project_context|wf_build_task_prompt|wf_build_review_prompt|wf_build_rework_prompt)" tests -g '*.py' -n`
  - No matches.
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/projects.py app/server_services/workflow.py tests/test_prompt_formatter_static.py`
  - Passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_project_execution_prompt_formatting.py tests/test_workflow_prompt_formatting.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q`
  - `15 passed`
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Passed.
