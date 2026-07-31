## Task 5.1 Evidence: Agent Template Tests

Status: passed

Changed files:
- `tests/test_agent_communication_skill.py`
- `tests/test_prompt_formatter_static.py`

What changed:
- Moved the agent template prompt-only assertion from `server._agent_template_files` to `services.agent_workspace_documents.agent_template_files`.
- Preserved the legacy communication profile in the migrated assertion because the tested OpenClaw bootstrap content intentionally verifies legacy VO routing guardrails.
- Removed the temporary registered test-reference exception for `server._agent_template_files`.

Verification:
- `rg "server\\._agent_template_files|def _agent_template_files|_agent_template_files\\(" app tests -n`
  - No matches.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_agent_communication_skill.py -q`
  - `20 passed`
