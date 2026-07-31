## Task 1.2 Static Guardrails

Date: 2026-07-31

### Change summary

Updated `tests/test_prompt_formatter_static.py` with two guardrails for legacy prompt compatibility wrappers:

- `test_server_private_prompt_wrapper_test_references_are_registered`
  - Scans Python tests for direct `server._*` private prompt wrapper references.
  - Fails on any unregistered new reference.
  - Keeps existing references visible with migration notes while later tasks move them to service main functions.
- `test_removed_server_private_prompt_wrappers_are_not_used_by_tests`
  - Fails if tests reference a wrapper listed in `REMOVED_SERVER_PRIVATE_PROMPT_WRAPPERS`.
  - Later wrapper-removal tasks can move a wrapper into this set after migrating its tests.

This creates a ratchet: current references are explicitly inventoried, new private prompt-wrapper test dependencies fail, and removed wrappers cannot be reintroduced into tests.

### Current registered references

- `tests/test_agent_communication_skill.py` -> `_agent_template_files`
- `tests/test_archive_room_phase_6.py` -> `_archive_context_prompt_block`
- `tests/test_codex_server.py` -> `_with_vo_provider_guidance`
- `tests/test_feishu_notifications.py` -> `_feishu_group_provider_message`
- `tests/test_project_execution.py` -> `_project_execution_build_prompt`
- `tests/test_project_execution.py` -> `_project_execution_build_review_prompt`
- `tests/codex_chat_fast_path_performance.py` -> `_with_vo_provider_guidance`

### Verification commands

- `PYTHONPATH=app .venv/bin/python -m py_compile tests/test_prompt_formatter_static.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py -q`
  - Result: `5 passed`.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.
- `git diff --check -- tests/test_prompt_formatter_static.py`
  - Result: passed.

### Risk / follow-up

The guardrail intentionally allows the currently inventoried references so this change can migrate them task-by-task. Each later wrapper-removal task should remove or update the relevant registry entries and, when a wrapper is deleted, add it to `REMOVED_SERVER_PRIVATE_PROMPT_WRAPPERS`.
