## Task 6.1 Evidence: Static Scans

Status: passed

Static scans:
- `rg "server\\._(agent_template_files|archive_context_prompt_block|bridge_provider_delivery_prompt|feishu_group_provider_message|project_execution_build_prompt|project_execution_build_review_prompt|wf_build_project_context|wf_build_task_prompt|wf_build_review_prompt|wf_build_rework_prompt|with_vo_provider_guidance)" tests app -g '*.py' -n`
  - No matches.
- `rg "def _(agent_template_files|archive_context_prompt_block|bridge_provider_delivery_prompt|feishu_group_provider_message|project_execution_build_prompt|project_execution_build_review_prompt|wf_build_project_context|wf_build_task_prompt|wf_build_review_prompt|wf_build_rework_prompt|with_vo_provider_guidance)" app/server.py app/server_services -n`
  - No removed definitions remain in `app/server.py`.
  - Authoritative prompt helper definitions remain only in focused service modules:
    - `app/server_services/archive_room.py`
    - `app/server_services/projects.py`
    - `app/server_services/workflow.py`
- `rg "bridge_input_output_formatting|render_document\\(" app/server.py app/server_services app/services -g '*.py' -n`
  - Direct low-level XML formatter usage is limited to:
    - `app/services/agent_platform_prompt_formatting.py`
    - `app/services/business_prompt_bridge.py`
    - `app/services/bridge_input_output_formatting.py`

Automated guardrail:
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py -q`
  - `6 passed`
