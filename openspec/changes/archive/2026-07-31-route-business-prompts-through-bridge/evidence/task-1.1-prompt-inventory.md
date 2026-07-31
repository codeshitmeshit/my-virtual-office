# Task 1.1 Provider-Visible Business Prompt Inventory

Date: 2026-07-31

This inventory classifies current low-level formatter usage before migrating
business prompt construction behind the common business prompt bridge facade.
It is intentionally file-oriented: later static checks can use the same file
families to distinguish bridge internals, migrated business prompts, tests/docs,
and temporary exceptions.

## Scan Commands

- `rg "bridge_input_output_formatting|render_document\(" app -g '*.py' -l`
- `rg "prompt_formatter\.render_document|prompt_format\.render_document|bridge_prompt_formatter\.render_document|render_document\(" app/server.py app/server_services app/services app/providers -g '*.py' -n`
- `rg "bridge_input_output_formatting" tests docs openspec -g '*.py' -g '*.md' -n`

## Classification Summary

| Classification | Meaning | Current action |
| --- | --- | --- |
| Bridge internal | Low-level XML formatter implementation or bridge/platform prompt promotion code. | Allowed to call `bridge_input_output_formatting` directly. |
| Business prompt temporary exception | Provider-visible business prompt still directly renders XML through the low-level formatter. | Must migrate to the common business prompt bridge in the task listed below. |
| Support/profile document temporary exception | System-authored profile/bootstrap/repair documents rendered with XML but not the main runtime business prompt facade yet. | Keep visible and either migrate or explicitly exempt in final coverage. |
| Tests/docs/OpenSpec | Verification or planning artifacts. | Allowed; static checks should not fail them. |

## Inventory

| File | Area | Direct formatter usage | Classification | Owner | Reason and risk | Migration condition |
| --- | --- | --- | --- | --- | --- | --- |
| `app/services/bridge_input_output_formatting.py` | Formatter primitive | Defines `render_document` and XML helpers. | Bridge internal | Bridge/platform | It is the low-level primitive. Risk is limited to formatter correctness, already covered separately. | Always allowed as bridge internal. |
| `app/services/agent_platform_prompt_formatting.py` | Agent/platform delivery | Renders promoted provider delivery and communication prompts. | Bridge internal | Bridge/platform | This is the existing promote -> render path for generic bridge delivery, not a business prompt bypass. | Keep as bridge internal; business facade may reuse the pattern. |
| `app/server.py:5410`, `app/server.py:5440` | Legacy platform delivery | Feishu group provider envelope and VO routing guidance. | Bridge internal / legacy compatibility | Bridge/platform | These are provider delivery guidance documents. Risk is legacy duplication with split services. | Keep only as bridge/platform compatibility or delegate to split bridge modules when touched. |
| `app/services/hr_prompt_documents.py` | HR daily report and introduction request | Directly renders `hr_daily_report_request` and `hr_agent_introduction_request`. | Business prompt temporary exception | HR | User-visible HR prompt path. Risk: HR prompt envelope/output policy still owned by HR module instead of bridge. | Migrate in task 2.1. |
| `app/services/hr_assessments.py:451` | HR assessment | Directly renders `hr_assessment_prompt`. | Business prompt temporary exception | HR | Important scoring prompt. Risk: locale, evidence policy, and JSON output validation are not bridge-owned. | Migrate in task 2.2. |
| `app/services/hr_directory.py:576` | HR introduction summary | Directly renders `hr_introduction_summary_prompt`. | Business prompt temporary exception | HR | Summarizes Agent self-introduction. Risk: repair/summary output policy remains split. | Migrate with HR assessment/summary work in task 2.2. |
| `app/services/hr_structured_output.py:92` | HR structured repair | Directly renders `hr_introduction_summary_repair_prompt`. | Support/profile document temporary exception | HR | Repair prompt is provider-visible but auxiliary to HR summary parsing. Risk: malformed-output recovery policy remains outside bridge. | Migrate or explicitly classify during task 2.2/2.3. |
| `app/server_services/meetings.py:1067`, `:2508`, `:2788`, `:3053` | Meetings | Advisory, targeted question, result, and turn prompts. | Business prompt temporary exception | Meetings | Runtime meeting prompts currently own their JSON schemas and output rules directly. | Migrate in task 3.1. |
| `app/server.py:15461`, `:16443`, `:16687`, `:16893` | Legacy meetings | Legacy mirror of meeting prompt rendering. | Business prompt temporary exception | Meetings | Compatibility path can drift from split meeting service. | Migrate or delegate with authoritative meeting service in task 3.1. |
| `app/services/project_execution_prompt_formatting.py:29` | Project execution | Directly renders `project_execution_prompt`. | Business prompt temporary exception | Projects | Main task execution prompt still owns bridge envelope and final output contract. | Migrate in task 4.1. |
| `app/services/execution_lifecycle.py:184` | Project checklist planning | Directly renders `checklist_planning_prompt`. | Business prompt temporary exception | Projects | Planning prompt is provider-visible and currently bypasses the business bridge. | Migrate with project execution in task 4.1. |
| `app/server_services/projects.py:3657`, `:3674`, `:3697`, `:3804` | Project execution subblocks | Artifact run, final result, meeting action, and archive/context prompt blocks. | Business prompt temporary exception | Projects | Raw XML subblocks are assembled into provider-visible execution prompts. Risk: bridge cannot uniformly own output order or trust boundaries. | Migrate in tasks 4.1 and 4.3. |
| `app/server.py:23876`, `:23895`, `:23910`, `:23933`, `:24045` | Legacy project execution subblocks | Legacy mirror of project execution prompt blocks. | Business prompt temporary exception | Projects | Same drift risk as split project service. | Migrate or delegate in tasks 4.1 and 4.3. |
| `app/services/workflow_prompt_formatting.py:139`, `:182`, `:215` | Workflow task/review/rework | Directly renders project workflow prompts. | Business prompt temporary exception | Workflow | Workflow prompts own review status and checklist output contracts directly. | Migrate in task 4.2. |
| `app/server_services/workflow.py:1171` | Workflow compatibility | Directly renders a workflow prompt in split workflow service. | Business prompt temporary exception | Workflow | Runtime path can bypass the new facade unless moved with workflow prompt helpers. | Migrate in task 4.2. |
| `app/services/project_task_final_result.py:200`, `:215` | Task final result handoff | Directly renders prior-stage result index and final-result instructions. | Business prompt temporary exception | Projects | Provider-visible subblocks affect later-stage task context and output semantics. | Migrate in task 4.3. |
| `app/server_services/archive_room.py:1256`, `:2309`, `:2353` | Archive room | AI refine and archive context prompt blocks. | Business prompt temporary exception | Archive | Archive prompts own JSON boundaries and context policy directly. | Migrate in task 5.1. |
| `app/server.py:22333`, `:23403`, `:23447` | Legacy archive | Legacy mirror of archive refine/context prompt blocks. | Business prompt temporary exception | Archive | Compatibility path can diverge from archive service. | Migrate or delegate in task 5.1. |
| `app/services/mcp_usage_guide_organization.py:172` | MCP guide generation | Directly renders MCP guide organization prompt. | Business prompt temporary exception | MCP/docs | Provider-visible support prompt. Risk: source material security and JSON output rules remain outside bridge. | Migrate in task 5.2. |
| `app/services/skill_library_organization.py:240` | Skill classification | Directly renders skill classification prompt. | Business prompt temporary exception | Skills | Provider-visible support prompt. Risk: untrusted skill data and strict output rules remain outside bridge. | Migrate in task 5.2. |
| `app/services/provider_skill_sync.py:165` | Provider skill sync | Directly renders synced skill prompt. | Support/profile document temporary exception | Provider skills | System-authored prompt used to keep provider skill state current. Risk: support prompt may escape static guardrails if not classified. | Decide migrate or final explicit exception in task 5.2/6.1. |
| `app/services/agent_workspace_documents.py` | Workspace bootstrap docs | Renders Agent workspace XML documents. | Support/profile document temporary exception | Agent workspace | Bootstrap/profile documents are provider-visible inputs but not a runtime business operation prompt. | Decide final exemption or bridge support-document adapter in task 6.1. |
| `app/services/hermes_profile_documents.py` | Hermes profile docs | Renders Hermes profile XML documents. | Support/profile document temporary exception | Agent workspace | Same support-document class as workspace bootstrap. | Decide final exemption or bridge support-document adapter in task 6.1. |
| `docs/prompt-formatter-inventory.md` | Docs | Documents prior formatter migration. | Tests/docs/OpenSpec | Docs | Not provider-visible runtime prompt construction. | Allowed outside static runtime checks. |
| `tests/test_bridge_input_output_formatting.py` and prompt static tests | Tests | Import formatter for assertions. | Tests/docs/OpenSpec | Tests | Tests must be able to exercise formatter behavior directly. | Allowed outside static runtime checks. |
| `openspec/changes/*` | OpenSpec | Mentions formatter and migration design. | Tests/docs/OpenSpec | OpenSpec | Planning/evidence only. | Allowed outside static runtime checks. |

## Static Coverage Implications

The first static guard should allow direct low-level formatter calls only in:

- Bridge internals: `app/services/bridge_input_output_formatting.py`,
  `app/services/agent_platform_prompt_formatting.py`, and explicitly named
  bridge facade modules added by this change.
- Tests, docs, and OpenSpec artifacts.
- Temporary exceptions listed in this file until their owning task migrates them.

After each migration task, that file family should be removed from the
temporary exception list and covered by tests that prove the public helper now
delegates through the common business prompt bridge.
