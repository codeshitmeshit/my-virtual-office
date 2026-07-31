## Task 4.1 Project Execution Prompt Test Migration

Date: 2026-07-31

### Change summary

Moved project execution prompt tests away from `server.py` private wrappers:

- `tests/test_project_execution.py`
  - Replaced direct `server._project_execution_build_prompt(...)` calls with `server_services.projects._project_execution_build_prompt(...)`.
  - Replaced direct `server._project_execution_build_review_prompt(...)` call with `server_services.projects._project_execution_build_review_prompt(...)`.
  - Calls `project_service._hydrate()` before service prompt builder calls so tests retain the active server-backed project fixture context.
- `app/services/project_execution_prompt_formatting.py`
  - Restored reviewer prompt compatibility wording around the authorized task workspace, read-only inspection, and stale historical feedback.
- `tests/test_prompt_formatter_static.py`
  - Removed migrated project prompt wrapper references from the registered server-private wrapper test inventory.

### Verification commands

- `rg "server\\._project_execution_build_(prompt|review_prompt)" tests/test_project_execution.py tests/test_prompt_formatter_static.py -n`
  - Result: no matches.
- `PYTHONPATH=app .venv/bin/python -m py_compile tests/test_project_execution.py tests/test_prompt_formatter_static.py app/services/project_execution_prompt_formatting.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_project_execution_prompt_formatting.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q`
  - Result: `11 passed`.

### Risk / follow-up

`app/server.py` still contains project execution prompt wrappers and runtime pipeline copies. Later project/workflow tasks must protect hydration and remove obsolete `server.py` wrappers after runtime ownership is moved.
