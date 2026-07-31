## Task 3.2 Archive Runtime Entry Points

Date: 2026-07-31

### Change summary

Moved archive context runtime ownership to `server_services.archive_room`:

- `app/server.py::_project_execution_build_prompt(...)`
  - Replaced local `_archive_context_prompt_block(...)` call with `server_services.archive_room._archive_context_prompt_block(...)` after service hydration.
- `app/server_services/projects.py::_project_execution_build_prompt(...)`
  - Replaced unqualified `_archive_context_prompt_block(...)` call with explicit `server_services.archive_room._archive_context_prompt_block(...)` after service hydration.

This avoids relying on same-name `server.py` archive prompt wrappers or broad hydration to resolve archive context prompt ownership.

### Verification commands

- `rg "_archive_context_prompt_block\\(" app/server.py app/server_services/projects.py app/server_services/archive_room.py tests/test_archive_room_phase_6.py -n`
  - Result: runtime callers now explicitly use `archive_room_service._archive_context_prompt_block(...)`; `app/server.py` still has an obsolete definition for Task 3.3.
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/projects.py app/server_services/archive_room.py tests/test_archive_room_phase_6.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_archive_prompt_documents.py tests/test_archive_room_phase_6.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus -q`
  - Result: `9 passed`.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.
- `git diff --check -- app/server.py app/server_services/projects.py tests/test_archive_room_phase_6.py tests/test_prompt_formatter_static.py`
  - Result: passed.

### Out-of-scope observation

A broader `tests/test_project_execution.py` run currently has unrelated failures around marked project execution start gates and an existing review-prompt wording assertion. Those failures are outside this archive ownership task and should be handled by the project/workflow task group if still present in the focused project validation.
 
### Risk / follow-up

`app/server.py::_archive_context_prompt_block(...)` is now obsolete and should be removed in Task 3.3.
