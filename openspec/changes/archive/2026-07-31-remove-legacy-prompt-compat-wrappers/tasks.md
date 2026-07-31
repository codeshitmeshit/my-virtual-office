## 1. Inventory and Guardrails

- [x] 1.1 Inventory legacy prompt compatibility wrappers and classify each caller as runtime, prompt-only test, integration test, or unused.
- [x] 1.2 Add or tighten static guardrails so prompt-only tests cannot keep depending on removed `server._*` private prompt wrappers, while integration tests may still exercise public/server paths.

## 2. Provider and Agent Platform Entry Points

- [x] 2.1 Move Feishu group prompt and VO guidance prompt-only tests to `services.agent_platform_prompt_formatting` main functions.
- [x] 2.2 Replace runtime provider delivery wrapper call sites with direct platform bridge/service calls, or extract wrapper-adjacent provider prompt ownership from `server.py` into a focused module when needed.
- [x] 2.3 Remove obsolete provider prompt wrappers from `server.py`, or record any retained thin delegates with caller, reason, risk, and removal condition.
- [x] 2.4 Run focused provider delivery regressions covering Feishu group metadata, VO guidance idempotency, provider payload compatibility, and prompt escaping.

## 3. Archive Prompt Entry Points

- [x] 3.1 Move archive prompt-only tests from `server._archive_context_prompt_block` to `services.archive_prompt_documents` or `server_services.archive_room` depending on whether the test verifies rendering or context derivation.
- [x] 3.2 Replace archive runtime prompt wrapper call sites with direct archive service/prompt module calls, extracting wrapper-adjacent context ownership from `server.py` when scoped and behavior-preserving.
- [x] 3.3 Remove obsolete archive prompt wrappers from `server.py`, or record any retained thin delegates with caller, reason, risk, and removal condition.
- [x] 3.4 Run focused archive regressions covering archive context/refine prompt shape, unavailable context handling, and public archive behavior touched by the migration.

## 4. Project Execution and Workflow Entry Points

- [x] 4.1 Move project execution prompt-only tests from `server._project_execution_build_prompt` / `server._project_execution_build_review_prompt` to `services.project_execution_prompt_formatting` or `server_services.projects` main functions.
- [x] 4.2 Move workflow prompt-only tests from `server._wf_*` private wrappers to `services.workflow_prompt_formatting` or `server_services.workflow` main functions.
- [x] 4.3 Adjust split-service hydration so authoritative project/workflow prompt helpers cannot be overwritten by legacy `server.py` wrapper names.
- [x] 4.4 Remove obsolete project/workflow prompt wrappers from `server.py`, or record any retained thin delegates with caller, reason, risk, and removal condition.
- [x] 4.5 Run focused project/workflow regressions covering project execution prompt shape, review prompt shape, workflow task/review/rework prompts, checklist output expectations, and hydration compatibility.

## 5. Agent Workspace Entry Points

- [x] 5.1 Move agent template prompt-only tests from `server._agent_template_files` to `services.agent_workspace_documents.agent_template_files`.
- [x] 5.2 Replace agent workspace runtime call sites with direct `agent_template_files` service calls and remove obsolete `server.py` template wrapper if no integration path still requires it.
- [x] 5.3 Run focused agent workspace regressions covering generated bootstrap documents and existing agent creation behavior.

## 6. Final Coverage and Evidence

- [x] 6.1 Run static scans proving business/support prompt modules do not call the low-level XML formatter and prompt-only tests do not call removed `server._*` wrappers.
- [x] 6.2 Run the focused regression suite for provider delivery, archive, project execution, workflow, agent workspace, prompt formatter static coverage, and OpenSpec validation.
- [x] 6.3 Record final wrapper inventory, removed wrappers, retained delegates with removal conditions, changed files, verification commands, known risks, and any unverified integration paths.
