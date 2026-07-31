## Task 1.1 Wrapper Inventory

Date: 2026-07-31

### Scan command

```bash
rg "_bridge_provider_delivery_prompt\\(|_feishu_group_provider_message\\(|_with_vo_provider_guidance\\(|_archive_context_prompt_block\\(|_project_execution_build_prompt\\(|_project_execution_build_review_prompt\\(|_wf_build_project_context\\(|_wf_build_task_prompt\\(|_wf_build_review_prompt\\(|_wf_build_rework_prompt\\(|_agent_template_files\\(" app tests -g '*.py' -n
```

### Classification summary

| Wrapper / helper name | Current definitions | Runtime callers | Prompt-only test callers | Integration-style test callers | Classification | Target owner / action |
| --- | --- | --- | --- | --- | --- | --- |
| `_bridge_provider_delivery_prompt` | `app/server.py`, `app/server_services/agent_bridges.py` | `app/server.py` provider paths; `app/server_services/agent_bridges.py` provider paths | none | indirectly through provider tests | Active runtime wrapper | Extract/route provider delivery ownership to `server_services.agent_bridges` or `services.agent_platform_prompt_formatting`; remove `server.py` duplicate if runtime callers can be moved. |
| `_feishu_group_provider_message` | `app/server.py` | none found outside `server.py` definition | `tests/test_feishu_notifications.py` calls it only to inspect prompt text | same test also covers representative dispatch integration | Test-only legacy prompt wrapper | Move prompt text assertions to `services.agent_platform_prompt_formatting.render_feishu_group_message_prompt`; remove wrapper after integration path no longer needs direct call. |
| `_with_vo_provider_guidance` | `app/server.py` | none found outside direct tests | `tests/test_codex_server.py` checks guidance idempotency/text | none | Test-only legacy prompt wrapper | Move prompt-only assertions to `services.agent_platform_prompt_formatting.with_vo_provider_guidance`; remove wrapper if no server integration caller remains. |
| `_archive_context_prompt_block` | `app/server.py`, `app/server_services/archive_room.py` | `server.py` project prompt builder; `server_services.projects` project prompt builder calls a same-name helper through module globals/hydration | `tests/test_archive_room_phase_6.py` directly inspects server prompt block | archive room context derivation is partly integration-like because it uses project/archive state | Active runtime + prompt test wrapper | Prefer `server_services.archive_room._archive_context_prompt_block` for context derivation and `services.archive_prompt_documents` for rendering assertions; remove `server.py` duplicate after project runtime is moved or hydration is protected. |
| `_project_execution_build_prompt` | `app/server.py`, `app/server_services/projects.py` | `server_services.projects._project_execution_run_attempt`; `server.py` legacy project execution flow | `tests/test_project_execution.py` prompt shape cases call `server._project_execution_build_prompt` | some project execution tests are orchestration/integration-style | Active runtime + prompt test wrapper | Make `server_services.projects` authoritative, protect prompt helpers from hydration overwrite, migrate prompt-only assertions to `services.project_execution_prompt_formatting` or `server_services.projects`. |
| `_project_execution_build_review_prompt` | `app/server.py`, `app/server_services/projects.py` | `server_services.projects._project_execution_run_review`; `server.py` legacy project execution flow | `tests/test_project_execution.py` prompt shape case calls `server._project_execution_build_review_prompt` | some project execution tests are orchestration/integration-style | Active runtime + prompt test wrapper | Same as project execution build prompt; remove `server.py` duplicate when call sites/hydration no longer require it. |
| `_wf_build_project_context` | `app/server.py`, `app/server_services/workflow.py` | no direct caller found for this helper name; workflow prompt builders use it internally where present | none found | none found | Candidate unused compatibility helper | Remove if no runtime dependency remains after workflow ownership migration, or keep only inside `server_services.workflow` if useful for local composition. |
| `_wf_build_task_prompt` | `app/server.py`, `app/server_services/workflow.py` | `server.py` workflow pipeline; `server_services.workflow` workflow pipeline | none found | workflow tests may reach it indirectly through pipeline behavior | Active runtime wrapper | Make `server_services.workflow` authoritative or call `services.workflow_prompt_formatting.render_workflow_task_prompt` directly; remove `server.py` duplicate when legacy pipeline call sites move. |
| `_wf_build_review_prompt` | `app/server.py`, `app/server_services/workflow.py` | `server.py` workflow pipeline; `server_services.workflow` workflow pipeline | none found | workflow tests may reach it indirectly through pipeline behavior | Active runtime wrapper | Same as workflow task prompt. |
| `_wf_build_rework_prompt` | `app/server.py`, `app/server_services/workflow.py` | `server.py` workflow pipeline; `server_services.workflow` workflow pipeline | none found | workflow tests may reach it indirectly through pipeline behavior | Active runtime wrapper | Same as workflow task prompt. |
| `_agent_template_files` | `app/server.py`, `app/server_services/agents.py` | `server.py` agent creation; `server_services.agents` agent creation | `tests/test_agent_communication_skill.py` directly inspects generated `AGENTS.md` | agent creation behavior is covered elsewhere through server/service routes | Active runtime + prompt test wrapper | Move prompt-only test to `services.agent_workspace_documents.agent_template_files`; move runtime caller to direct service import; remove `server.py` duplicate if no integration boundary requires it. |

### Runtime classification details

#### Provider/platform delivery

`app/server.py` still uses `_bridge_provider_delivery_prompt(...)` in multiple provider paths:

- Hermes delivery setup.
- Hermes chat handling.
- Codex chat handling.
- Claude Code chat handling.
- Representative agent dispatch.

`app/server_services/agent_bridges.py` also defines and uses `_bridge_provider_delivery_prompt(...)` internally. This service copy is closer to the intended owner than `server.py`, but both currently exist.

#### Archive

`app/server_services/archive_room.py` has the focused archive context prompt helper and already delegates rendering to `services.archive_prompt_documents`. `app/server.py` still has a duplicate `_archive_context_prompt_block(...)` used by its local project execution prompt wrapper.

#### Project execution

`app/server_services/projects.py` defines `_project_execution_build_prompt(...)` and `_project_execution_build_review_prompt(...)`, and its runtime review/attempt flows call those local names. Because `server_services.projects._hydrate()` copies server globals broadly, later tasks must ensure these prompt helper names cannot be replaced by `server.py` duplicates.

#### Workflow

`app/server_services/workflow.py` defines workflow prompt helpers and its pipeline calls local names. `app/server.py` still carries parallel workflow prompt helpers and pipeline call sites. Later tasks should prefer focused workflow service ownership rather than preserving both copies.

#### Agent workspace documents

Both `app/server.py` and `app/server_services/agents.py` define `_agent_template_files(...)`, but the authoritative rendering owner is now `services.agent_workspace_documents.agent_template_files`.

### Test classification details

Prompt-only tests that should move to service main functions:

- `tests/test_codex_server.py`
  - `server._with_vo_provider_guidance(...)` assertions are prompt text/idempotency checks.
- `tests/test_feishu_notifications.py`
  - direct `server._feishu_group_provider_message(...)` assertions are prompt text/boundary checks.
- `tests/test_agent_communication_skill.py`
  - `server._agent_template_files(...)["AGENTS.md"]` is bootstrap document rendering.

Mixed prompt/integration tests that need careful split or service-level setup:

- `tests/test_archive_room_phase_6.py`
  - direct `server._archive_context_prompt_block(...)` checks context derivation plus prompt rendering.
- `tests/test_project_execution.py`
  - direct `server._project_execution_build_prompt(...)` and `_project_execution_build_review_prompt(...)` checks include prompt shape, archive context, artifact run instructions, and orchestration-derived fields.

### Removal order recommendation

1. Move prompt-only tests to service functions first.
2. Add static guardrail for prompt-only test references to removed wrappers.
3. Migrate provider/platform wrappers because `_feishu_group_provider_message` and `_with_vo_provider_guidance` are currently test-only direct wrappers.
4. Migrate agent template wrapper.
5. Migrate archive/project/workflow wrappers after hydration protection is in place.

### Current risks

- Broad hydration in `server_services.projects` and `server_services.workflow` may preserve legacy ownership unless explicitly guarded.
- Some tests use `server.py` as a convenient fixture even when they only inspect prompt text; these tests will keep wrappers alive unless moved.
- `server.py` remains large, so extraction must stay wrapper-adjacent to avoid turning this change into a broad monolith rewrite.
