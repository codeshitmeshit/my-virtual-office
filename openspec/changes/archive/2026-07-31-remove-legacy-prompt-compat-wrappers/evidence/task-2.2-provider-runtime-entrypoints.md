## Task 2.2 Provider Runtime Entry Points

Date: 2026-07-31

### Change summary

Added `services.agent_platform_prompt_formatting.render_provider_delivery_prompt(...)` as the authoritative provider delivery prompt entry point. It reuses the existing `promote_provider_delivery_prompt(...)` preprocessing path and `render_promoted_agent_platform_message_prompt(...)` rendering path, preserving Feishu group metadata, VO guidance, provider output requirements, and attachment context behavior.

Runtime provider delivery call sites now call `render_provider_delivery_prompt(...)` directly:

- `app/server.py`
  - Hermes delivery setup.
  - Hermes chat handling.
  - Codex chat handling.
  - Claude Code chat handling.
  - Representative agent dispatch.
- `app/server_services/agent_bridges.py`
  - Hermes delivery setup.
  - Hermes chat handling.
  - Codex provider send.
  - Claude Code provider send.

The historical `_bridge_provider_delivery_prompt(...)` definitions remain only as compatibility delegates and are handled by Task 2.3.

### Verification commands

- `rg "_bridge_provider_delivery_prompt\\(" app/server.py app/server_services/agent_bridges.py -n`
  - Result: only compatibility definitions remain.
- `PYTHONPATH=app .venv/bin/python -m py_compile app/services/agent_platform_prompt_formatting.py app/server.py app/server_services/agent_bridges.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_provider_service_boundaries.py -q`
  - Result: `123 passed`.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.
- `git diff --check -- app/services/agent_platform_prompt_formatting.py app/server.py app/server_services/agent_bridges.py tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_prompt_formatter_static.py`
  - Result: passed.

### Risk / follow-up

Provider wrapper definitions still exist after this task, but runtime call sites no longer depend on them. Task 2.3 should remove the obsolete provider prompt wrappers or record any retained thin delegates with removal conditions.
