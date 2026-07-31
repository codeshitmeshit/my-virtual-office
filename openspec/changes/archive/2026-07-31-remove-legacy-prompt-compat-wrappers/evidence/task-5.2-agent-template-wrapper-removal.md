## Task 5.2 Evidence: Agent Template Wrapper Removal

Status: passed

Changed files:
- `app/server.py`
- `app/server_services/agents.py`
- `tests/test_prompt_formatter_static.py`

What changed:
- Removed obsolete `_agent_template_files` thin wrappers from both `server.py` and `server_services/agents.py`.
- Replaced agent creation runtime calls with direct `agent_template_files(...)` calls.
- Preserved existing runtime behavior:
  - `server.py` uses `communication_profile="legacy"`.
  - `server_services/agents.py` uses `communication_profile="service"`.
- Removed `_agent_template_files` from `server_services.agents.__all__`.
- Added `_agent_template_files` to the removed-wrapper static guardrail.

Verification:
- `rg "server\\._agent_template_files|def _agent_template_files|_agent_template_files\\(" app tests -n`
  - No matches.
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/agents.py app/services/agent_workspace_documents.py tests/test_agent_communication_skill.py tests/test_prompt_formatter_static.py`
  - Passed.
