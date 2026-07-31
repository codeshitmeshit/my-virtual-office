## Task 6.2 Evidence: Focused Regression Suite

Status: passed

Focused regression suite:
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_provider_service_boundaries.py tests/test_archive_prompt_documents.py tests/test_archive_room_phase_6.py tests/test_project_execution_prompt_formatting.py tests/test_workflow_prompt_formatting.py tests/test_agent_communication_skill.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q`
  - `154 passed in 46.12s`

Compile check:
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/agent_bridges.py app/server_services/agents.py app/server_services/archive_room.py app/server_services/projects.py app/server_services/workflow.py app/services/agent_platform_prompt_formatting.py app/services/agent_workspace_documents.py app/services/project_execution_prompt_formatting.py app/services/workflow_prompt_formatting.py tests/test_prompt_formatter_static.py`
  - Passed.

OpenSpec validation:
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Passed.
