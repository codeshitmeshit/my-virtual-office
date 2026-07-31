## Context

`route-business-prompts-through-bridge` moved prompt construction to bridge-backed helpers and tightened static coverage so business/support modules no longer call the low-level XML formatter directly. The remaining cleanup is ownership: several historical `server.py` private functions still exist as prompt wrappers, and some tests still import those private names directly.

This change removes the unnecessary compatibility layer after call sites and tests are moved to the authoritative prompt/service functions.

## Goals / Non-Goals

**Goals:**

- Make runtime prompt construction call the owning bridge-backed module directly.
- Move prompt-rendering tests from `server._*` private wrappers to the new main functions.
- Remove obsolete private compatibility wrappers once runtime and prompt tests no longer use them.
- Extract prompt-wrapper-adjacent runtime ownership from `server.py` into focused modules when that is the safe way to remove wrappers without keeping orchestration in the monolith.
- Keep any unavoidable compatibility wrapper as a thin delegate with a recorded removal condition.
- Prevent split-service hydration from overriding authoritative prompt helpers with legacy `server.py` implementations.
- Preserve public HTTP, provider, parsing, persistence, and UI behavior.

**Non-Goals:**

- Change prompt semantics, output schemas, provider payload contracts, or parser behavior.
- Redesign provider transport or project/workflow orchestration.
- Archive the previous prompt bridge change.
- Refactor unrelated `server.py` business logic outside wrapper ownership cleanup.
- Perform a broad `server.py` decomposition unrelated to prompt wrapper ownership.

## Current Wrapper Groups

The known wrapper/call-site groups are:

- Provider/platform delivery:
  - `server._bridge_provider_delivery_prompt`
  - `server._feishu_group_provider_message`
  - `server._with_vo_provider_guidance`
  - Authoritative owner: `services.agent_platform_prompt_formatting` plus `services.bridge_prompt_preprocessing`.
- Archive prompt helpers:
  - `server._archive_context_prompt_block`
  - Archive refine prompt compatibility around archive manager code.
  - Authoritative owner: `services.archive_prompt_documents` and `server_services.archive_room`.
- Project execution prompt helpers:
  - `server._project_execution_build_prompt`
  - `server._project_execution_build_review_prompt`
  - Authoritative owner: `services.project_execution_prompt_formatting` and `server_services.projects`.
- Workflow prompt helpers:
  - `server._wf_build_project_context`
  - `server._wf_build_task_prompt`
  - `server._wf_build_review_prompt`
  - `server._wf_build_rework_prompt`
  - Authoritative owner: `services.workflow_prompt_formatting` and `server_services.workflow`.
- Agent workspace documents:
  - `server._agent_template_files`
  - Authoritative owner: `services.agent_workspace_documents`.

## Decisions

### 1. Migrate tests before deleting wrappers

Prompt-only tests should stop importing `server._*` private wrappers and should instead import the owning service function. This makes test failures point at the intended ownership boundary and allows obsolete wrappers to be deleted safely.

Integration tests that verify public routes, provider dispatch, or server-level orchestration may continue importing `server`, but they should assert behavior through the public/integration path, not by calling private prompt wrappers as test fixtures.

### 2. Prefer deleting wrappers over keeping delegates

If a wrapper has no runtime callers after call-site migration, remove it. Keeping a thin delegate is allowed only when a current runtime boundary still needs the historical name and moving it would widen the task beyond this change. Every retained wrapper must have no prompt assembly logic and must be recorded as an explicit remaining compatibility point.

### 3. Make split services own their prompt helpers

For project/workflow/archive paths, the split service modules should use their imported prompt modules directly. Hydration should not replace these prompt helpers with `server.py` definitions. If needed, exclude migrated prompt helper names from hydration or remove the corresponding `server.py` wrapper so there is nothing stale to hydrate.

### 4. Extract from `server.py` when wrapper cleanup exposes ownership

If a compatibility wrapper is still tied to active runtime orchestration, prefer moving that small ownership slice into an existing focused service module or a new focused module. This is especially appropriate for provider delivery helpers, agent template generation, archive prompt context assembly, and project/workflow prompt assembly that already have service homes.

Extraction is not a license for a broad `server.py` rewrite. If the required move crosses route dispatch, persistence, provider lifecycle, or unrelated UI/API concerns, keep a thin delegate and record the later extraction condition.

### 5. Keep behavior compatibility as the acceptance line

The implementation should be mostly call-site and test ownership movement. Prompt text should remain bridge-backed and parser-compatible. Any intentional prompt wording or XML-shape difference must be documented and tested.

## Implementation Plan

1. Inventory wrapper call sites and classify each as runtime, prompt-only test, integration test, or unused.
2. Move prompt-only tests to the owning prompt/service modules:
   - Feishu group prompt tests -> `services.agent_platform_prompt_formatting`.
   - VO guidance tests -> `services.agent_platform_prompt_formatting`.
   - Archive context prompt tests -> `services.archive_prompt_documents` or `server_services.archive_room` when context derivation is under test.
   - Project execution prompt tests -> `services.project_execution_prompt_formatting` or `server_services.projects` when orchestration-specific context is required.
3. Replace runtime calls to `server.py` private prompt wrappers with direct calls to the owning module or split service.
4. Extract wrapper-adjacent runtime ownership from `server.py` into focused modules when doing so is scoped and behavior-preserving.
5. Remove wrappers from `server.py` when no runtime/integration caller remains.
6. Adjust split-service hydration so authoritative prompt functions are not overwritten by legacy `server.py` names.
7. Tighten or add static tests:
   - No prompt-only tests call removed `server._*` wrappers.
   - No business/support prompt module calls the low-level XML formatter.
   - Remaining wrapper inventory, if any, is explicit.
8. Run focused regression tests for provider delivery, archive, project execution, workflow prompt formatting, and static coverage.

## Risks / Trade-offs

- **Runtime coupling:** `server.py` and split services still share globals through hydration. Mitigation: migrate in wrapper groups and verify the runtime owner after each group.
- **Test churn:** Some existing tests mix prompt assertions with server orchestration setup. Mitigation: split prompt-specific assertions into service-level tests and leave server-level tests for integration behavior.
- **Prompt shape drift:** Directly calling a new main function may reveal small wrapper-added differences. Mitigation: preserve expected prompt shape in the authoritative helper before deleting wrappers.
- **Over-deletion:** Removing a private function still used by dynamic test or route code would break compatibility. Mitigation: static search plus focused test suites before removal.
- **Extraction creep:** `server.py` is large, but this change should not become an unrelated decomposition project. Mitigation: extract only wrapper-adjacent ownership needed to remove direct compatibility calls safely.

## Verification Plan

- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
- Static search proving prompt-only tests no longer call removed `server._*` wrappers.
- Static prompt formatter guardrail test.
- Focused tests:
  - `tests/test_feishu_notifications.py` or moved prompt-specific equivalent.
  - `tests/test_codex_server.py` for integration-level VO guidance behavior, if still relevant.
  - `tests/test_archive_prompt_documents.py`
  - `tests/test_project_execution_prompt_formatting.py`
  - `tests/test_project_execution.py` focused cases that rely on orchestration context.
  - `tests/test_workflow_prompt_formatting.py`
- `git diff --check`

## Open Questions

None blocking. The implementation may discover a wrapper that remains required by runtime hydration; if so, the task should retain it only as a thin delegate and record the caller and removal condition.
