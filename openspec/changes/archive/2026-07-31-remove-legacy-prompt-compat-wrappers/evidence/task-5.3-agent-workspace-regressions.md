## Task 5.3 Evidence: Agent Workspace Regressions

Status: passed

Scope covered:
- Generated bootstrap document content.
- OpenClaw agent creation writes template files.
- Communication skill install/repair behavior.
- Static prompt wrapper guardrails.

Verification:
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_agent_communication_skill.py -q`
  - `20 passed`
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/agents.py app/services/agent_workspace_documents.py tests/test_agent_communication_skill.py tests/test_prompt_formatter_static.py`
  - Passed.

Review note:
- One existing archive-manager repair test was updated to isolate `refresh_agent_maps` and `get_roster` during the test. The newer lifecycle path reads the roster list before appending the mocked archive manager, so the test now avoids accidentally observing a real local default OpenClaw workspace.
