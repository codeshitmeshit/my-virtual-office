## Final Acceptance: zero business formatter exceptions

Date: 2026-07-31

### OpenSpec status

- `openspec list`
  - `route-business-prompts-through-bridge` reported `✓ Complete`.
- `openspec validate route-business-prompts-through-bridge --strict`
  - Result: `Change 'route-business-prompts-through-bridge' is valid`.

### Additional prompt coverage tightening

After the original completion evidence, the remaining temporary direct-formatter exceptions were migrated:

- `app/server.py` no longer imports or calls `bridge_input_output_formatting` / `bridge_prompt_formatter` / `render_document(...)` for provider-visible prompt construction.
- `app/services/agent_workspace_documents.py` now renders bootstrap documents through `business_prompt_bridge.render_business_prompt(...)`.
- `app/services/hermes_profile_documents.py` now renders bootstrap documents through `business_prompt_bridge.render_business_prompt(...)`.
- `tests/test_prompt_formatter_static.py` now has empty temporary business/support exception sets, so new business direct low-level formatter calls fail static coverage.

Remaining low-level XML formatter usage is limited to bridge/platform internals:

- `app/services/bridge_input_output_formatting.py`
- `app/services/business_prompt_bridge.py`
- `app/services/agent_platform_prompt_formatting.py`

### Verification commands

- `PYTHONPATH=app .venv/bin/python -m py_compile app/services/agent_workspace_documents.py app/services/hermes_profile_documents.py app/services/agent_platform_prompt_formatting.py app/services/project_execution_prompt_formatting.py app/server.py tests/test_prompt_formatter_static.py tests/test_feishu_notifications.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_business_prompt_bridge.py tests/test_bridge_input_output_formatting.py tests/test_project_execution_prompt_formatting.py tests/test_archive_prompt_documents.py tests/test_workflow_prompt_formatting.py tests/test_feishu_notifications.py tests/test_codex_server.py -q`
  - Result: `128 passed`.
- `rg "bridge_input_output_formatting|bridge_prompt_formatter|render_document\\(" app/server.py app/server_services app/services tests/test_prompt_formatter_static.py -g '*.py' -n`
  - Result: only bridge/platform internals and the static test itself remain.
- `rg "return\\s+f?[\\\"']<|<output_contract|<agent_output_contract|<project_task_prompt|<project_review_prompt|<project_rework_prompt|<meeting_.*prompt|<hr_.*prompt|<archive_.*prompt" app/server.py app/server_services app/services -g '*.py' -n`
  - Result: only the low-level formatter's own XML rendering implementation remains.
- `git diff --check`
  - Result: passed.

### Acceptance note

This validates the previous change's intended prompt-construction boundary: migrated business and support prompt builders no longer directly assemble provider-visible XML through the low-level formatter. A follow-up change should remove or redirect legacy private compatibility wrapper names so call sites invoke the authoritative bridge-backed service functions directly.
