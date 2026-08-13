# Shared Prompt Formatter Inventory

Provider-visible Agent prompts should use `services.bridge_input_output_formatting`.
Business code passes key-value or nested mappings, and the formatter renders XML,
escapes dynamic data, validates tag names, and moves `output` to the final
top-level section.

## Migrated Paths

- Bridge/provider delivery: Feishu representative dispatch, Codex, Hermes,
  Claude Code, and OpenClaw delivery prompts now use the shared formatter for
  source metadata, user messages, VO routing guidance, and final `output`.
- Formatter core: XML name validation, text/attribute escaping, custom tags,
  nested mappings, JSON data boundaries, untrusted text boundaries, and final
  `output` ordering are covered by unit tests.
- HR prompts: assessment and introduction summary prompts render Agent reports,
  prior introductions, and evidence through formatter data boundaries.
- MCP guide organization: MCP server/tool/reference material is passed as
  formatter-managed source data with final `output`.
- Skill library organization: existing category data and untrusted skill data
  are rendered through the formatter while preserving the custom
  `untrusted_skill_data` tag.
- Meeting structured prompts: busy advisory, participant turn, and result
  prompts now render through the shared formatter while preserving expected
  context labels and JSON output contracts.
- Project structured prompts: execution, review, rework, task final-result
  subblocks, checklist planning, archive context, artifact run,
  unfinished-checklist, and meeting-action prompts now render through the shared
  formatter. Project execution uses `output` as the final contract section while
  preserving the legacy `final_response` schema as an `output` child.
- Legacy workflow prompts: task execution, self-review, rework, project context,
  acceptance checklist, previous-work log, review statuses, and checklist update
  requirements now render through the shared formatter.
- Archive structured prompts use final `output` sections instead of the old
  output-contract tag.

## Mapping Guidance

- Static instructions should be passed as trusted text fields such as `role`,
  `task`, `rules`, or `security`.
- User, provider, file, tool, transcript, or business record content should be
  passed as `untrusted_text(...)` or `json_data(...)`.
- Custom XML tags are simply mapping keys or `section(name, value, attrs=...)`.
  Invalid tag or attribute names are rejected before a prompt can be sent.
- Output requirements belong under the `output` key. Do not prepend a separate
  output-contract block.

## Source index

| Prompt family | Owning source | Main callers |
|---|---|---|
| Provider/Agent delivery and conversation recovery | `app/services/agent_platform_prompt_formatting.py` | `app/server.py`, `vo_agent_communication.py`, `provider_conversations.py` |
| Generic business XML envelope | `app/services/business_prompt_bridge.py` and `bridge_input_output_formatting.py` | All business prompt modules below |
| Meeting advisory, participant/targeted turn, moderator result | `app/services/meeting_prompt_documents.py` | Meeting lifecycle handlers in `app/server.py` |
| Project execution, review, rework, checklist | `app/services/project_execution_prompt_formatting.py` | `execution_lifecycle.py`, review and project execution services |
| Legacy workflow task/review/rework | `app/services/workflow_prompt_formatting.py` | `app/server_services/workflow.py` and workflow entrypoints |
| Project completion report | `app/services/project_completion_report_prompt.py` | `project_completion_report_generation.py` |
| Archive refinement/context | `app/services/archive_prompt_documents.py` | Archive services and `app/server.py` |
| HR assessment/introduction/repair | `app/services/hr_prompt_documents.py`, `hr_assessments.py`, `hr_directory.py` | HR services |
| MCP and skill-library organization | `app/services/mcp_usage_guide_organization.py`, `skill_library_organization.py` | Organization run workers |
| Feishu topic context | `app/services/feishu_notification_topics.py` | Notification-topic dispatch |
| Human-decision continuation | `human_decision_chat_continuation.py`, `human_decision_meeting_continuation.py` | Continuation dispatcher |
| Workspace document instructions | `app/services/agent_workspace_documents.py` | Agent workspace operations |

Search for provider-visible construction with:

```bash
rg -n 'render_business_prompt|render_.*prompt|build_.*prompt|def .*_prompt' app --glob '*.py'
```

Every new or touched provider-visible prompt must have one XML root, put dynamic material in formatter-owned untrusted/JSON boundaries, and keep `output` last. Do not concatenate independently rendered XML prompt documents. Meeting targeted questions previously did this; they now render as a section of the single `meeting_turn_prompt`, reducing duplicated envelope/schema/context tokens.

## Optimization checklist

- Prefer incremental context or a bounded recent window over replaying a full transcript.
- Include one output schema and one output instruction; avoid restating the same contract in prose.
- Pass only fields used by the decision. In particular, avoid full project, task, provider, or Meeting records when an allowlisted projection is enough.
- Truncate before rendering so escaped output cannot exceed the provider budget unexpectedly.
- Keep static rules trusted and cacheable; keep user, transcript, tool, file, and provider data explicitly untrusted.
- Add a test for root count, escaping, required sections, output-last ordering, and the configured prompt-character budget.

## Verification Notes

- Python core prompt suite: `179 passed` across formatter, static prompt checks,
  provider bridge delivery, archive, meeting, HR/MCP/skill organization, project
  execution, project final result, and legacy workflow prompt coverage.
- Additional Feishu/VO Agent coverage: `31 passed` for VO Agent communication,
  Feishu representative command/presence/OpenClaw boundaries, and native
  provider source metadata; `6 passed` for Agent communication routing.
- JavaScript/static checks passed for server/frontend module split, Codex runs
  bridge, project execution chat polling, project workflow chat stability,
  stage workflow active fallback, and project reset board rerendering.
- Known unrelated JS/static gap: `tests/check_project_marked_frontend_legacy_fields.mjs`
  currently fails because `app/projects.js` does not hydrate marked-project
  workflow active state from active task ids. That file had pre-existing
  unrelated worktree changes and was not changed by this formatter migration.
