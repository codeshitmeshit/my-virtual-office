## Task 2.4 Provider Regressions

Date: 2026-07-31

### Covered behavior

The focused provider regression suite covered:

- Feishu group speaker metadata preservation and prompt boundary assertions.
- VO routing guidance text and idempotency through the authoritative platform prompt formatter.
- Provider dispatch payload compatibility for Hermes, Codex, Claude Code, and OpenClaw representative dispatch paths.
- Static guardrails for removed provider prompt wrappers.
- Provider service boundary checks around provider bridge ownership.

### Verification commands

- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_provider_service_boundaries.py -q`
  - Result: `123 passed`.
- `rg "_bridge_provider_delivery_prompt|_feishu_group_provider_message|_with_vo_provider_guidance" app tests -g '*.py' -n`
  - Result: only static guardrail declarations remain.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.

### Residual risk

No provider prompt wrappers were retained. Later final validation should include this suite again after the non-provider wrapper groups are migrated.
