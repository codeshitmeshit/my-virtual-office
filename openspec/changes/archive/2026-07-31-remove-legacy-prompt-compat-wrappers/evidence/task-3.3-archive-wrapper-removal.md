## Task 3.3 Archive Wrapper Removal

Date: 2026-07-31

### Change summary

Removed obsolete `app/server.py::_archive_context_prompt_block(...)`.

Runtime archive context prompt ownership now lives in `server_services.archive_room._archive_context_prompt_block(...)`, with callers explicitly using that service function:

- `app/server.py::_project_execution_build_prompt(...)`
- `app/server_services/projects.py::_project_execution_build_prompt(...)`
- `tests/test_archive_room_phase_6.py`

Updated `tests/test_prompt_formatter_static.py` so `_archive_context_prompt_block` is listed in `REMOVED_SERVER_PRIVATE_PROMPT_WRAPPERS`.

### Verification commands

- `rg "server\\._archive_context_prompt_block|def _archive_context_prompt_block" app/server.py tests -g '*.py' -n`
  - Result: no matches.
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/projects.py app/server_services/archive_room.py tests/test_prompt_formatter_static.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_archive_prompt_documents.py tests/test_archive_room_phase_6.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus -q`
  - Result: `14 passed`.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.

### Retained delegates

None for the `server.py` archive context wrapper.
