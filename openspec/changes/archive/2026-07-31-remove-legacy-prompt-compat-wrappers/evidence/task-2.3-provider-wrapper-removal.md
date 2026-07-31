## Task 2.3 Provider Wrapper Removal

Date: 2026-07-31

### Change summary

Removed obsolete provider prompt compatibility wrappers:

- Removed `app/server.py::_feishu_group_provider_message`.
- Removed `app/server.py::_bridge_provider_delivery_prompt`.
- Removed `app/server.py::_with_vo_provider_guidance`.
- Removed `app/server_services/agent_bridges.py::_bridge_provider_delivery_prompt`.

Updated remaining callers:

- `app/server.py` now passes `services.agent_platform_prompt_formatting.with_vo_provider_guidance` directly to `VOAgentCommunicationPorts`.
- `tests/codex_chat_fast_path_performance.py` no longer stores or monkeypatches the removed `server._with_vo_provider_guidance` wrapper.
- `tests/test_prompt_formatter_static.py` now lists the removed provider wrappers in `REMOVED_SERVER_PRIVATE_PROMPT_WRAPPERS`.

### Verification commands

- `rg "_bridge_provider_delivery_prompt|_feishu_group_provider_message|_with_vo_provider_guidance" app tests -g '*.py' -n`
  - Result: only static guardrail declarations remain.
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/agent_bridges.py tests/codex_chat_fast_path_performance.py tests/test_prompt_formatter_static.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_provider_service_boundaries.py -q`
  - Result: `123 passed`.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.
- `git diff --check -- app/server.py app/server_services/agent_bridges.py tests/codex_chat_fast_path_performance.py tests/test_prompt_formatter_static.py`
  - Result: passed.

### Retained delegates

None for the provider prompt wrapper group.

### Risk / follow-up

Provider delivery runtime ownership now points at `services.agent_platform_prompt_formatting.render_provider_delivery_prompt(...)`. Later final coverage should re-run the broader focused provider regression suite after archive/project/workflow/agent template wrapper cleanup.
