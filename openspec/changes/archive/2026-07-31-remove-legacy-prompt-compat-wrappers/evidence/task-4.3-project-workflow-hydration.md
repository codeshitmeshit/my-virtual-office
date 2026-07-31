## Task 4.3 Project / Workflow Hydration Protection

Date: 2026-07-31

### Change summary

Protected service-owned prompt helpers from broad `server.py` hydration:

- `app/server_services/projects.py`
  - Added `_SERVICE_OWNED_PROMPT_HELPERS` for:
    - `_project_execution_build_prompt`
    - `_project_execution_build_review_prompt`
  - `_hydrate()` now skips these keys so `server.py` duplicates cannot overwrite service-owned prompt helpers.
  - Added missing unfinished checklist focus rendering to the service-owned project execution prompt helper, preserving current prompt behavior once hydration no longer masks it.
- `app/server_services/workflow.py`
  - Added `_SERVICE_OWNED_PROMPT_HELPERS` for:
    - `_wf_build_project_context`
    - `_wf_build_task_prompt`
    - `_wf_build_review_prompt`
    - `_wf_build_rework_prompt`
  - `_hydrate()` now skips these keys.
- `tests/test_prompt_formatter_static.py`
  - Added static coverage asserting both split services declare prompt-helper hydration protection.

### Verification commands

- `PYTHONPATH=app .venv/bin/python -m py_compile app/server_services/projects.py app/server_services/workflow.py tests/test_prompt_formatter_static.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_project_execution_prompt_formatting.py tests/test_workflow_prompt_formatting.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q`
  - Result: `15 passed`.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.

### Risk / follow-up

`app/server.py` still contains project/workflow prompt wrappers and legacy workflow pipeline call sites. Task 4.4 should remove obsolete wrappers where possible or record retained delegates with removal conditions.
