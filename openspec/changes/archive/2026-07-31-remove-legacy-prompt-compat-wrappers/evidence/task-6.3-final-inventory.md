## Task 6.3 Evidence: Final Inventory

Status: passed

Removed legacy `server.py` prompt wrappers:
- `_agent_template_files`
- `_archive_context_prompt_block`
- `_bridge_provider_delivery_prompt`
- `_feishu_group_provider_message`
- `_project_execution_build_prompt`
- `_project_execution_build_review_prompt`
- `_wf_build_project_context`
- `_wf_build_task_prompt`
- `_wf_build_review_prompt`
- `_wf_build_rework_prompt`
- `_with_vo_provider_guidance`

Authoritative prompt entry points after migration:
- Provider and platform prompts:
  - `services.agent_platform_prompt_formatting.render_provider_delivery_prompt`
  - `services.agent_platform_prompt_formatting.render_feishu_group_message_prompt`
  - `services.agent_platform_prompt_formatting.with_vo_provider_guidance`
- Agent workspace documents:
  - `services.agent_workspace_documents.agent_template_files`
- Archive prompts:
  - `services.archive_prompt_documents`
  - `server_services.archive_room._archive_context_prompt_block`
- Project execution prompts:
  - `services.project_execution_prompt_formatting`
  - `server_services.projects._project_execution_build_prompt`
  - `server_services.projects._project_execution_build_review_prompt`
- Workflow prompts:
  - `services.workflow_prompt_formatting`
  - `server_services.workflow._wf_build_task_prompt`
  - `server_services.workflow._wf_build_review_prompt`
  - `server_services.workflow._wf_build_rework_prompt`

Retained prompt compatibility delegates:
- None in `app/server.py`.

Retained non-prompt delegates:
- Some lifecycle/route compatibility delegates remain in `app/server.py`, but they do not construct provider-visible prompts and were outside this change's wrapper-removal scope.

Changed files in this change area:
- `app/server.py`
- `app/server_services/agent_bridges.py`
- `app/server_services/agents.py`
- `app/server_services/archive_room.py`
- `app/server_services/projects.py`
- `app/server_services/workflow.py`
- `app/services/agent_platform_prompt_formatting.py`
- `app/services/agent_workspace_documents.py`
- `app/services/archive_prompt_documents.py`
- `app/services/bridge_input_output_formatting.py`
- `app/services/bridge_prompt_preprocessing.py`
- `app/services/business_prompt_bridge.py`
- `app/services/project_execution_prompt_formatting.py`
- `app/services/workflow_prompt_formatting.py`
- `tests/test_agent_communication_skill.py`
- `tests/test_archive_prompt_documents.py`
- `tests/test_archive_room_phase_6.py`
- `tests/test_codex_server.py`
- `tests/test_feishu_notifications.py`
- `tests/test_project_execution.py`
- `tests/test_project_execution_prompt_formatting.py`
- `tests/test_prompt_formatter_static.py`
- `tests/test_workflow_prompt_formatting.py`
- `tests/codex_chat_fast_path_performance.py`
- `openspec/changes/remove-legacy-prompt-compat-wrappers/*`

Final verification:
- `git diff --check`
  - Passed.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_codex_server.py tests/test_feishu_notifications.py tests/test_provider_service_boundaries.py tests/test_archive_prompt_documents.py tests/test_archive_room_phase_6.py tests/test_project_execution_prompt_formatting.py tests/test_workflow_prompt_formatting.py tests/test_agent_communication_skill.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus tests/test_project_execution.py::test_reviewer_provider_matrix_receives_read_only_evidence_packet -q`
  - `154 passed in 46.12s`
- `PYTHONPATH=app .venv/bin/python -m py_compile app/server.py app/server_services/agent_bridges.py app/server_services/agents.py app/server_services/archive_room.py app/server_services/projects.py app/server_services/workflow.py app/services/agent_platform_prompt_formatting.py app/services/agent_workspace_documents.py app/services/project_execution_prompt_formatting.py app/services/workflow_prompt_formatting.py tests/test_prompt_formatter_static.py`
  - Passed.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Passed.

Known risks and unverified paths:
- The full repository test suite was not run in this final pass; the focused regression set covers the prompt-wrapper migration surface.
- The repository worktree contains many pre-existing unrelated modified files. This evidence only claims the prompt-wrapper migration scope.
