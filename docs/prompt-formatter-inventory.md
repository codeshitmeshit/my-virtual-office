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
