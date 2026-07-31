## Task 3.1 Archive Prompt Test Migration

Date: 2026-07-31

### Change summary

Moved archive context prompt test coverage away from the `server.py` private wrapper:

- `tests/test_archive_room_phase_6.py`
  - Replaced `server._archive_context_prompt_block(...)` with `server_services.archive_room._archive_context_prompt_block(...)`.
  - Calls `archive_room_service._hydrate()` before the assertion so the service uses the test's active server-backed archive/project state.
- `tests/test_prompt_formatter_static.py`
  - Removed the migrated `server._archive_context_prompt_block` test-reference registration.

The existing test remains a context-derivation check rather than a pure XML rendering check, so `server_services.archive_room` is the correct authoritative target.

### Verification commands

- `rg "server\\._archive_context_prompt_block" tests/test_archive_room_phase_6.py tests/test_prompt_formatter_static.py -n`
  - Result: no matches.
- `PYTHONPATH=app .venv/bin/python -m py_compile tests/test_archive_room_phase_6.py tests/test_prompt_formatter_static.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_archive_prompt_documents.py tests/test_archive_room_phase_6.py -q`
  - Result: `12 passed`.

### Risk / follow-up

`app/server.py` still contains an archive context prompt wrapper and a local project prompt builder that can call it. Runtime archive/project ownership is handled in Task 3.2 and later project/workflow tasks.
