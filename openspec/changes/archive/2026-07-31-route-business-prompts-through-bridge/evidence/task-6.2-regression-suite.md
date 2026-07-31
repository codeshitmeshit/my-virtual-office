# Task 6.2 Focused Regression Suite

Date: 2026-07-31

Command:

```bash
PYTHONPATH=app .venv/bin/python -m pytest tests/test_business_prompt_bridge.py tests/test_prompt_formatter_static.py tests/test_hr_daily_report_collection.py tests/test_hr_information_completion.py tests/test_hr_assessment_orchestration.py tests/test_hr_assessment_parser.py tests/test_hr_introduction_summarizer.py tests/test_hr_manual_daily_sync.py tests/test_hr_automatic_reporting.py tests/test_meeting_prompt_documents.py tests/test_meeting_lifecycle_service.py tests/test_meeting_for_ai_phase1.py tests/test_project_execution_prompt_formatting.py tests/test_project_task_final_result.py tests/test_workflow_prompt_formatting.py tests/test_execution_lifecycle.py tests/test_project_workflow_timeline_boundary.py tests/test_server_routes_module_split.py tests/test_archive_prompt_documents.py tests/test_archive_room_ai_refine.py tests/test_archive_room_phase_6.py tests/test_archive_room_phase_8.py tests/test_mcp_usage_guide_organization.py tests/test_skill_library_organization_contract.py tests/test_skill_library_organization_runs.py tests/test_provider_skill_sync.py tests/test_vo_agent_communication_service.py tests/test_codex_server.py tests/test_claude_code_server.py -q
```

Result:

```text
308 passed in 44.26s
```

Coverage:

- Common business bridge facade and static direct-formatter guardrails.
- HR daily report, introduction completion, assessment parsing/orchestration,
  manual sync, automatic reporting, malformed output handling, and Chinese
  assessment wording.
- Meeting advisory/turn/result/targeted-question prompt shape and lifecycle
  compatibility.
- Project execution prompt shape, checklist planning/lifecycle, final-result
  and prior-stage handoff blocks, workflow task/review/rework prompts, and
  route split compatibility.
- Archive refine/context prompts, MCP guide organization, skill classification,
  provider skill sync prompt injection.
- VO Agent communication, Codex server delivery, and Claude Code server
  delivery boundaries.
