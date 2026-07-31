## Task 2.1 Provider Prompt Test Migration

Date: 2026-07-31

### Change summary

Moved provider/Agent-platform prompt-only assertions from `server.py` private wrappers to the authoritative prompt formatting module:

- `tests/test_codex_server.py`
  - Replaced `server._with_vo_provider_guidance(...)` with `services.agent_platform_prompt_formatting.with_vo_provider_guidance(...)`.
- `tests/test_feishu_notifications.py`
  - Replaced direct `server._feishu_group_provider_message(...)` prompt rendering assertion with `services.agent_platform_prompt_formatting.render_feishu_group_message_prompt(...)`.
  - Kept the representative agent dispatch integration path at the server level.
- `tests/test_prompt_formatter_static.py`
  - Removed the migrated direct wrapper references from the registered test-reference inventory.

### Verification commands

- `rg "server\\._(feishu_group_provider_message|with_vo_provider_guidance)" tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_prompt_formatter_static.py -n`
  - Result: no matches.
- `PYTHONPATH=app .venv/bin/python -m py_compile tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_prompt_formatter_static.py`
  - Result: passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_feishu_notifications.py -q`
  - Result: `111 passed`.

### Risk / follow-up

This task intentionally migrates tests only. Runtime provider delivery call sites still use `server._bridge_provider_delivery_prompt(...)` and are handled by later provider wrapper ownership tasks.
