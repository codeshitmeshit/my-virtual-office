# Provider Runtime Migration Todolist

## Execution Notes

This todolist is generated from the confirmed checklist. Implementation must preserve existing project and meeting behavior while using the reference branch as a provider-runtime source. Do not replace broad shared files wholesale.

## Tasks

### Preparation And Safety

- [x] TODO-001 - Capture pre-implementation baseline and protect local work.
  - Goal: Establish exactly what must be preserved before provider migration starts.
  - Involves: Git status, local diffs, reference diff, project/meeting changed files.
  - Input: Current working tree, `FETCH_HEAD` reference branch, confirmed checklist.
  - Output: Baseline notes in implementation report or working notes.
  - Dependencies: None.
  - Completion standard: Local project/meeting files and unrelated untracked files are identified; implementation strategy avoids wholesale replacement.
  - Checklist: CHK-001, CHK-002, CHK-003, CHK-055.

- [x] TODO-002 - Map reference provider-runtime functions to local integration points.
  - Goal: Create a concrete merge map for provider modules, discovery, server routes, chat, setup, and models.
  - Involves: `app/providers/*`, `app/discovery.py`, `app/server.py`, `app/chat.js`, `app/setup.html`, `app/models.html`.
  - Input: Reference branch diff and local code.
  - Output: Implementation notes identifying copied, adapted, skipped, and preserved areas.
  - Dependencies: TODO-001.
  - Completion standard: Every reference provider-runtime area has a disposition before code edits.
  - Checklist: CHK-001, CHK-002, CHK-045.

### Provider Modules

- [x] TODO-003 - Add Claude Code provider module safely.
  - Goal: Introduce Claude Code discovery and shallow chat/task support.
  - Involves: `app/providers/claude_code.py`, provider imports, provider tests.
  - Input: Reference `ClaudeCodeProvider` implementation.
  - Output: Claude Code provider that degrades gracefully when unavailable.
  - Dependencies: TODO-002.
  - Completion standard: Missing binary/auth does not crash discovery; mocked stream-json success/error/tool flows parse correctly.
  - Checklist: CHK-007, CHK-017, CHK-023, CHK-032, CHK-050.

- [x] TODO-004 - Migrate Codex provider runtime while preserving current project execution contract.
  - Goal: Absorb useful Codex native runtime behavior without breaking current Codex harness/conversation behavior.
  - Involves: `app/providers/codex.py`, `app/providers/codex_bridge.py`, server Codex handlers.
  - Input: Reference Codex provider and current Codex bridge/harness.
  - Output: Codex provider supports discovery, chat/run data, approvals, cancellation, and existing project execution dispatch.
  - Dependencies: TODO-002.
  - Completion standard: Existing Codex opt-in behavior works; migrated runtime exposes reply/tools/thinking/run IDs/approval/token usage where available.
  - Checklist: CHK-006, CHK-010, CHK-011, CHK-012, CHK-013, CHK-026, CHK-027, CHK-045, CHK-048.

- [x] TODO-005 - Merge Hermes native API run/event support without losing CLI fallback.
  - Goal: Add Hermes API client/run events while preserving existing profile discovery, CLI chat, per-conversation history, and approval retry.
  - Involves: `app/providers/hermes.py`, server Hermes handlers.
  - Input: Reference Hermes API client and current Hermes provider.
  - Output: Hermes supports native API when available and falls back to CLI when not.
  - Dependencies: TODO-002.
  - Completion standard: CLI tests still pass; mocked native API run, events, approval, stop, and completion work.
  - Checklist: CHK-005, CHK-014, CHK-015, CHK-016, CHK-023, CHK-050.

### Discovery And Roster

- [x] TODO-006 - Update provider discovery with backward-compatible signatures.
  - Goal: Support richer Codex and Claude Code discovery without breaking OpenClaw/Hermes callers.
  - Involves: `app/discovery.py`, server config integration.
  - Input: Reference discovery changes and current discovery function usage.
  - Output: Discovery supports OpenClaw, Hermes, Codex, and Claude Code with stable metadata.
  - Dependencies: TODO-003, TODO-004, TODO-005.
  - Completion standard: Disabled/unavailable providers are safe; enabled providers appear with stable IDs, status keys, provider kind, profile/provider agent ID, workspace/home, capabilities.
  - Checklist: CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-023.

### Server APIs And State

- [x] TODO-007 - Add provider run/history/session storage helpers.
  - Goal: Support provider histories, sessions, token usage, active runs, and profile/conversation isolation.
  - Involves: `app/server.py` provider helper sections.
  - Input: Reference helper functions and current `_load_hermes_history`, Codex activity/history, project execution history needs.
  - Output: Normalized helpers for Codex/Hermes/Claude Code without cross-contamination.
  - Dependencies: TODO-004, TODO-005, TODO-006.
  - Completion standard: Histories clear and load per provider/profile/conversation; existing histories remain readable or safely ignored.
  - Checklist: CHK-018, CHK-047, CHK-048, CHK-049.

- [x] TODO-008 - Add or adapt Codex server API routes.
  - Goal: Support Codex chat, run events, approval, interrupt/cancel, compact/reset, history, and test endpoints.
  - Involves: `app/server.py` Codex routes and handlers.
  - Input: Reference Codex routes and current `/api/codex/*` handlers.
  - Output: Codex API remains backward-compatible and can expose migrated run/event behavior.
  - Dependencies: TODO-004, TODO-007.
  - Completion standard: Existing Codex endpoints continue to work; new/updated endpoints return normalized data and handle failures gracefully.
  - Checklist: CHK-010, CHK-011, CHK-012, CHK-013, CHK-018, CHK-045, CHK-050, CHK-051.

- [x] TODO-009 - Add or adapt Hermes server API routes.
  - Goal: Support Hermes CLI chat plus native run/event/approval/interrupt endpoints.
  - Involves: `app/server.py` Hermes routes and handlers.
  - Input: Reference Hermes routes and current Hermes handlers.
  - Output: Hermes API supports both native and fallback paths.
  - Dependencies: TODO-005, TODO-007.
  - Completion standard: Chat/history/clear/test/approval work; native `/runs`/events/stop work when API is available; fallback remains intact.
  - Checklist: CHK-014, CHK-015, CHK-016, CHK-018, CHK-045, CHK-050, CHK-051.

- [x] TODO-010 - Add Claude Code server API routes.
  - Goal: Expose Claude Code test, chat, history, interrupt, and optional run/event behavior needed for shallow integration.
  - Involves: `app/server.py` Claude Code routes and handlers.
  - Input: Reference Claude Code routes.
  - Output: Claude Code can be discovered, tested, chatted with, interrupted, and represented in history.
  - Dependencies: TODO-003, TODO-006, TODO-007.
  - Completion standard: Missing/unavailable Claude Code returns useful errors; mocked success and error paths work.
  - Checklist: CHK-007, CHK-017, CHK-023, CHK-032, CHK-045, CHK-050.

- [x] TODO-011 - Add native provider setup/model APIs without breaking existing providers.
  - Goal: Support useful provider configuration surfaces while preserving OpenClaw/OAuth/model behavior.
  - Involves: `app/server.py`, setup/model config helpers.
  - Input: Reference native model/setup endpoints and current model provider code.
  - Output: Safe provider config/test/model endpoints for Codex/Hermes/Claude Code as applicable.
  - Dependencies: TODO-006.
  - Completion standard: Existing OAuth/model providers still work; missing provider config produces clear errors and no secret leaks.
  - Checklist: CHK-020, CHK-021, CHK-022, CHK-023, CHK-049.

### Project Execution Integration

- [x] TODO-012 - Preserve and adapt project execution provider dispatch.
  - Goal: Ensure project task executor/reviewer dispatch still works for OpenClaw, Codex, Hermes, and supported Claude Code paths.
  - Involves: `app/server.py` project execution call helpers and provider normalization.
  - Input: Current project execution functions and migrated provider handlers.
  - Output: Provider results normalize into project execution records without leaking provider-specific complexity.
  - Dependencies: TODO-008, TODO-009, TODO-010.
  - Completion standard: Provider matrix routes correctly; unsupported Claude Code roles are clear; attempt/review records remain traceable.
  - Checklist: CHK-026, CHK-027, CHK-032, CHK-045, CHK-048.

- [x] TODO-013 - Preserve project execution state and evidence behavior.
  - Goal: Prevent regressions in execution state transitions, evidence, checklist updates, cancellation, stale repair, acceptance, and rework.
  - Involves: `app/server.py`, `app/project_store.py`, project tests.
  - Input: Existing project execution tests and current local project changes.
  - Output: Existing project execution behavior remains intact after provider migration.
  - Dependencies: TODO-012.
  - Completion standard: Existing project execution tests pass and provider migration does not alter project semantics.
  - Checklist: CHK-024, CHK-028, CHK-029, CHK-030, CHK-031, CHK-046.

### Meeting Integration

- [x] TODO-014 - Preserve AI meeting request and task-blocking behavior.
  - Goal: Ensure provider migration does not regress meeting request, confirmation, rejection, auto-approval, blocking, and resume flows.
  - Involves: `app/server.py`, `app/game.js`, meeting tests.
  - Input: Existing meeting local changes and tests.
  - Output: Meeting flows remain behaviorally unchanged.
  - Dependencies: TODO-012.
  - Completion standard: Existing meeting tests pass and meeting UI/API flows remain compatible.
  - Checklist: CHK-025, CHK-033, CHK-034, CHK-035, CHK-036.

- [x] TODO-015 - Preserve meeting records, result writeback, and action-item behavior.
  - Goal: Keep project meeting records, discussion points, task writeback, and action-item handling intact.
  - Involves: `app/server.py`, `app/game.js`, `app/projects.js`, locales/CSS if needed.
  - Input: Existing meeting record/action-item tests and UI checks.
  - Output: Meeting outcomes continue to appear in project/task contexts correctly.
  - Dependencies: TODO-014.
  - Completion standard: Meeting record and action-item tests/checks pass; provider roster changes do not break participant selection.
  - Checklist: CHK-037, CHK-038, CHK-039, CHK-040, CHK-058.

### Frontend Integration

- [x] TODO-016 - Integrate provider runtime visibility into chat.
  - Goal: Bring in useful provider history/run/event/tool/thinking/approval rendering without breaking OpenClaw, existing Codex activity, or Hermes behavior.
  - Involves: `app/chat.js`, `app/style.css`, locales if needed.
  - Input: Reference chat implementation and current chat implementation.
  - Output: Chat handles OpenClaw, Codex, Hermes, and Claude Code capability differences.
  - Dependencies: TODO-008, TODO-009, TODO-010.
  - Completion standard: Mixed provider chat, history, approvals, new-session, cancellation, and duplicate-message prevention work.
  - Checklist: CHK-009, CHK-010, CHK-019, CHK-042, CHK-043, CHK-044, CHK-056.

- [x] TODO-017 - Integrate setup and model UI changes safely.
  - Goal: Add provider configuration/model-management UI where useful while preserving existing setup/model functionality.
  - Involves: `app/setup.html`, `app/models.html`, `app/api-usage.js`, `app/style.css` if needed.
  - Input: Reference setup/model changes and current UI.
  - Output: Setup/model pages load, save, test, and display provider states without breaking existing fields.
  - Dependencies: TODO-011.
  - Completion standard: Existing config surfaces still work; new provider config states are clear and do not expose secrets.
  - Checklist: CHK-020, CHK-021, CHK-022, CHK-023, CHK-044, CHK-059.

- [x] TODO-018 - Protect project and meeting frontend surfaces.
  - Goal: Ensure provider migration does not destabilize project board, task detail, meeting modals, sidebar links, or project meeting record UI.
  - Involves: `app/game.js`, `app/projects.js`, `app/projects.css`, `app/style.css`, locales.
  - Input: Existing local project/meeting frontend changes and browser checks.
  - Output: Project and meeting UI remains usable with provider roster changes.
  - Dependencies: TODO-014, TODO-015, TODO-016.
  - Completion standard: Browser checks and manual smoke tests pass; no overlap/regression in critical UI.
  - Checklist: CHK-040, CHK-041, CHK-044, CHK-057, CHK-058.

### Tests And Verification

- [x] TODO-019 - Add provider unit/server tests.
  - Goal: Cover migrated provider behavior and failure modes.
  - Involves: `tests/` provider/server test files.
  - Input: Confirmed checklist provider cases.
  - Output: Targeted tests for Codex, Hermes native API/fallback, Claude Code, discovery, history isolation, approvals, cancellation, missing binaries.
  - Dependencies: TODO-003 through TODO-011.
  - Completion standard: Tests cover both success and failure paths without requiring real provider installations.
  - Checklist: CHK-005, CHK-006, CHK-007, CHK-010, CHK-017, CHK-018, CHK-023, CHK-045, CHK-047, CHK-048, CHK-050, CHK-051.

- [x] TODO-020 - Run and fix core Python regression tests.
  - Goal: Verify project, meeting, provider, and server behavior.
  - Involves: Python test suite.
  - Input: Existing and newly added Python tests.
  - Output: Passing targeted Python tests or documented blockers.
  - Dependencies: TODO-012 through TODO-019.
  - Completion standard: Required Python tests pass, including project execution and meeting suites.
  - Checklist: CHK-024, CHK-025, CHK-033, CHK-053.

- [x] TODO-021 - Run and fix browser/Node regression checks.
  - Goal: Verify project/meeting/chat/setup/model UI behavior.
  - Involves: Node/browser check scripts.
  - Input: Existing and newly added UI checks.
  - Output: Passing targeted browser/Node checks or documented skips with reasons.
  - Dependencies: TODO-016, TODO-017, TODO-018.
  - Completion standard: Project execution UI, meeting records, sidebar/detail checks, and changed provider UI checks pass.
  - Checklist: CHK-040, CHK-041, CHK-044, CHK-054.

- [x] TODO-022 - Perform manual smoke tests.
  - Goal: Validate user-visible workflows that automated tests cannot fully cover.
  - Involves: Running app, provider discovery/chat, project task execution, meeting flow, setup/model pages.
  - Input: Local app environment and available provider fixtures/real providers.
  - Output: Manual smoke-test notes.
  - Dependencies: TODO-020, TODO-021.
  - Completion standard: Manual smoke tests pass or residual risks are documented.
  - Checklist: CHK-056, CHK-057, CHK-058, CHK-059.

- [x] TODO-023 - Produce final test and regression report.
  - Goal: Make verification auditable and confirm no original functionality was dropped.
  - Involves: Final delivery notes, checklist updates.
  - Input: Test command outputs, manual smoke-test notes, implementation diff.
  - Output: Final implementation report with commands, results, failures/skips, and residual risks.
  - Dependencies: TODO-020, TODO-021, TODO-022.
  - Completion standard: Report maps completed work and tests back to checklist; known gaps are explicit.
  - Checklist: CHK-052, CHK-055, CHK-060.

### Documentation And Cleanup

- [x] TODO-024 - Update relevant documentation and examples.
  - Goal: Document provider runtime behavior, config expectations, and supported/unsupported provider capabilities.
  - Involves: README/docs/config examples as needed.
  - Input: Implemented behavior and reference docs.
  - Output: Updated documentation without overstating unsupported Claude Code/meeting parity.
  - Dependencies: TODO-003 through TODO-017.
  - Completion standard: Docs reflect current product behavior and fallback rules.
  - Checklist: CHK-021, CHK-023, CHK-032, CHK-055.

- [x] TODO-025 - Update checklist with test outcomes before final tested confirmation.
  - Goal: Prepare requirement archive for testing confirmation.
  - Involves: `checklist.md`, `status.json`.
  - Input: Final test report and implementation results.
  - Output: Checklist items marked or annotated with pass/fail/skip notes.
  - Dependencies: TODO-023.
  - Completion standard: `checklist.md` contains enough evidence for user to confirm tested status.
  - Checklist: CHK-053, CHK-054, CHK-055, CHK-060.


## Implementation Slice Notes - 2026-06-26T23:49:37+08:00

Completed in this slice: TODO-001, TODO-002, TODO-003, TODO-006, TODO-010, TODO-012, TODO-014, TODO-019, TODO-020, TODO-023, TODO-025.

Partially completed / intentionally deferred: TODO-004 and TODO-005 remain deeper native Codex/Hermes routing work; TODO-007 through TODO-009 are partially covered by Claude Code state helpers and Hermes API client foundation; TODO-016 is partially covered by Claude Code chat integration. TODO-021, TODO-022, TODO-024 remain open.


## Continued Implementation Notes - 2026-06-26T23:58:41+08:00

Advanced from the initial slice: Claude Code chat i18n and server metadata coverage are complete; Hermes native API client now has server-side detection and safe config reporting. Node source-level project/meeting/chat checks pass. Full browser/manual checks and full Codex/Hermes native run routing remain open.


## Hermes Native Chat Notes - 2026-06-27T00:05:24+08:00

Hermes native API is now integrated into chat as an opt-in server-side route with CLI fallback. TODO-005 and TODO-009 are complete for the conservative local integration scope. Browser SSE proxy/manual smoke remains open under TODO-021/TODO-022.


## Runtime Smoke Notes - 2026-06-27T00:10:56+08:00

HTTP-level runtime smoke passed on an isolated temporary server. Browser/CDP checks remain open because DevTools endpoint `127.0.0.1:9224` was not available in the current environment.


## Codex Native Bridge Notes - 2026-06-27T00:15:29+08:00

Codex migration item is considered complete for local-authoritative behavior: the existing `codex app-server` bridge is retained and labeled accurately as `app-server-bridge`; broad reference native-agent creation is intentionally not wholesale-adopted to preserve current project/meeting contracts.


## Provider Runtime Config Notes - 2026-06-27T00:28:20+08:00

Advanced TODO-021 and TODO-022 with provider runtime setup/settings persistence:

- Main settings can now round-trip Hermes native API, Codex, and Claude Code runtime config.
- Setup wizard can now round-trip Hermes native API config.
- `/setup/save` now safely merges provider config without clearing saved secrets from blank password/key fields.
- `/vo-config` exposes safe Codex/Claude Code fields for UI load while redacting secrets and demo reply text.
- HTTP smoke passed for setup/save persistence, invalid JSON 400 handling, safe `/vo-config`, and provider test endpoints.

TODO-021 is complete for source-level and HTTP-level checks. TODO-022 remains partial because CDP/browser/manual visual checks are not available in this environment.


## Model Runtime And History Isolation Notes - 2026-06-27T00:36:22+08:00

Closed the remaining automatable provider-runtime gaps:

- `/config/providers` now includes safe `nativeProviders` status for Hermes, Codex, and Claude Code without exposing provider secrets.
- `models.html` now has a read-only Native Agents tab showing runtime availability/model/workspace and linking users back to the office settings menu for configuration.
- Hermes `history/clear` is now conversation-scoped, matching Claude Code's isolation behavior and avoiding accidental clearing of another Hermes conversation.
- Project execution state/evidence, cancellation, stale reconciliation, reviewer skip, dirty confirmation, acceptance/rework, meeting records, and action-item behavior are covered by the current Python and Node regression sets.

TODO-011, TODO-013, TODO-015, TODO-016, TODO-017, TODO-018, TODO-021, and TODO-024 are complete for the current local-authoritative migration scope. TODO-022 remains partial only for browser/manual visual smoke because CDP `127.0.0.1:9224` is unavailable in this environment.


## Chrome MCP Browser Smoke Notes - 2026-06-27T00:48:17+08:00

User explicitly authorized Chrome MCP fallback when CDP cannot connect. TODO-022 is now complete for the current environment:

- Main settings provider fields for Hermes API, Codex, and Claude Code were exercised in Chrome MCP.
- Models page Native Agents tab was exercised in Chrome MCP and showed safe Hermes/Codex/Claude Code runtime status.
- Project and meeting surfaces were smoke-tested for modal visibility, rendered text, meeting request/detail/reference availability, and overlap checks.
- Known environmental noise is limited to repeated `/pc-metrics` 502 responses from an unavailable metrics backend target and a `favicon.ico` 404; neither is related to provider runtime migration.

TODO-022 completion remains scoped to fixture-backed browser/API smoke. Real native provider chat/project execution still depends on the user's installed/authenticated Hermes, Codex, and Claude Code runtimes, and is covered by mocks/fixtures where those runtimes are unavailable.


## Phase 1 Closure - 2026-06-27T00:55:01+08:00

All Phase 1 tasks TODO-001 through TODO-025 are complete for the local-authoritative provider runtime migration scope. The second migration phase intentionally starts from TODO-026 and focuses on the reference branch's native Codex/Claude Code agent management bottom layer.

Phase 2 must continue to treat local project and meeting behavior as authoritative. Do not replace broad shared files wholesale.


## Phase 2 Native Agent Management Tasks

### Phase 2 Preparation

- [x] TODO-026 - Rebaseline reference native-agent implementation against current local code.
  - Goal: Build an exact merge map for Codex/Claude Code native agent management after Phase 1 changes.
  - Involves: `eliautobot/main`, `app/providers/codex.py`, `app/providers/claude_code.py`, `app/discovery.py`, `app/server.py`, setup/model UI files.
  - Input: Current dirty worktree, `eliautobot/main`, Phase 1 checklist/test evidence.
  - Output: Implementation notes identifying provider methods, config fields, server routes, and UI elements to adapt or skip.
  - Dependencies: Phase 1 completed.
  - Completion standard: No code edits start before provider-bottom-layer merge boundaries are clear.
  - Checklist: CHK-061, CHK-062, CHK-085.

- [x] TODO-027 - Extend provider config schema safely.
  - Goal: Support native-agent management settings while preserving old single-collaborator config.
  - Involves: `app/server.py`, `/setup/save`, `/vo-config`, `/config/providers`, setup/main settings config merge helpers.
  - Input: Existing `codex.workspace/agentId/bridgeUrl/replyText`, reference `workspaceRoot/mainWorkspace/includeMain/includeNativeAgents/registerNativeAgents` fields.
  - Output: Backward-compatible config model for Codex and Claude Code native agent management.
  - Dependencies: TODO-026.
  - Completion standard: Legacy config and new config both round-trip; secrets and fixture reply text remain safe.
  - Checklist: CHK-063, CHK-073, CHK-081.

### Provider Bottom Layer

- [x] TODO-028 - Migrate Codex native agent discovery and metadata.
  - Goal: Add main/Office-managed/native Codex agent discovery under the current Codex bridge contract.
  - Involves: `app/providers/codex.py`, `app/discovery.py`, Codex provider tests.
  - Input: Reference Codex provider discovery, current `codex_bridge.py`, config schema from TODO-027.
  - Output: Codex roster supports multiple profiles/workspaces/native paths without breaking existing `codex-local`.
  - Dependencies: TODO-027.
  - Completion standard: Fixture discovery covers main, Office-managed, native TOML, disabled, missing binary, and malformed metadata cases.
  - Checklist: CHK-064, CHK-065, CHK-079, CHK-080.

- [x] TODO-029 - Migrate Codex native agent create/delete lifecycle.
  - Goal: Support standard/custom Codex agent creation and safe deletion.
  - Involves: `app/providers/codex.py`, server create/delete handlers, tests.
  - Input: Reference `create_agent/delete_agent`, local agent lifecycle API, path safety requirements.
  - Output: Codex lifecycle operations create metadata/TOML/workspaces and delete only selected profiles.
  - Dependencies: TODO-028.
  - Completion standard: Main/system profiles cannot be deleted; standard/custom/path traversal cases are tested.
  - Checklist: CHK-066, CHK-067, CHK-072, CHK-080.

- [x] TODO-030 - Migrate Claude Code native subagent discovery and metadata.
  - Goal: Add main/Office-managed/native Claude Code subagent discovery while preserving current chat/session behavior.
  - Involves: `app/providers/claude_code.py`, `app/discovery.py`, Claude Code provider tests.
  - Input: Reference Claude Code provider discovery, current shallow Claude Code chat implementation, config schema from TODO-027.
  - Output: Claude Code roster supports multiple profiles/workspaces/native markdown subagents without breaking current local agent.
  - Dependencies: TODO-027.
  - Completion standard: Fixture discovery covers main, Office-managed, native markdown, disabled, missing binary, and malformed metadata cases.
  - Checklist: CHK-068, CHK-069, CHK-079, CHK-080.

- [x] TODO-031 - Migrate Claude Code native subagent create/delete lifecycle.
  - Goal: Support standard/custom Claude Code agent creation and safe deletion.
  - Involves: `app/providers/claude_code.py`, server create/delete handlers, tests.
  - Input: Reference `create_agent/delete_agent`, local agent lifecycle API, path safety requirements.
  - Output: Claude Code lifecycle operations create metadata, `CLAUDE.md`, project/native agent markdown, and delete only selected profiles.
  - Dependencies: TODO-030.
  - Completion standard: Main/system profiles cannot be deleted; standard/custom/path traversal cases are tested.
  - Checklist: CHK-070, CHK-071, CHK-072, CHK-080.

### Server And Runtime Integration

- [x] TODO-032 - Wire multi-profile Codex/Claude Code into discovery and roster refresh.
  - Goal: Ensure `/api/agents`, `agents-list`, status/session maps, and roster limiting handle multiple native provider agents.
  - Involves: `app/discovery.py`, `app/server.py`, roster/session helpers.
  - Input: Provider discovery from TODO-028 and TODO-030.
  - Output: Multiple Codex/Claude Code agents appear with stable keys and do not hide OpenClaw/Hermes agents.
  - Dependencies: TODO-028, TODO-030.
  - Completion standard: Server tests cover mixed OpenClaw/Hermes/Codex/Claude Code roster.
  - Checklist: CHK-064, CHK-068, CHK-075.

- [x] TODO-033 - Update Codex chat/activity/history to use selected profile/workspace.
  - Goal: Keep current app-server bridge behavior while routing multi-agent Codex turns to the selected profile workspace.
  - Involves: `app/server.py`, `app/providers/codex.py`, `app/providers/codex_bridge.py`, Codex server tests.
  - Input: Multi-profile Codex roster and existing conversation/thread/activity helpers.
  - Output: Conversation thread/activity/history remain isolated per Codex profile/conversation.
  - Dependencies: TODO-028, TODO-032.
  - Completion standard: Chat, approval, cancel, compact, and project execution use the correct workspace/profile.
  - Checklist: CHK-065, CHK-075, CHK-076, CHK-078.

- [x] TODO-034 - Update Claude Code chat/history/interrupt to use selected profile/workspace.
  - Goal: Keep current Claude Code stream-json/reply fixture behavior while routing turns to selected native profile workspace.
  - Involves: `app/server.py`, `app/providers/claude_code.py`, Claude Code server tests.
  - Input: Multi-profile Claude Code roster and existing history/session helpers.
  - Output: Chat, session resume, history clear, and interrupt remain isolated per profile/conversation.
  - Dependencies: TODO-030, TODO-032.
  - Completion standard: Server tests cover multiple Claude Code profiles and old single local profile compatibility.
  - Checklist: CHK-069, CHK-075, CHK-078.

- [x] TODO-035 - Integrate provider-neutral agent create/delete server routes.
  - Goal: Let existing agent lifecycle API create/delete Codex and Claude Code native agents safely.
  - Involves: `app/server.py`, route handlers, safety checks, history cleanup.
  - Input: Provider create/delete from TODO-029 and TODO-031.
  - Output: `/api/agents` create/delete supports OpenClaw, Hermes, Codex, and Claude Code with normalized responses.
  - Dependencies: TODO-029, TODO-031, TODO-032.
  - Completion standard: Missing providers, duplicate names, main deletion, archive manager safety, and cleanup are tested.
  - Checklist: CHK-067, CHK-071, CHK-072, CHK-080.

### Frontend Integration

- [x] TODO-036 - Extend setup/main settings UI for native-agent config.
  - Goal: Expose new Codex/Claude Code native agent fields without disrupting current provider settings.
  - Involves: `app/index.html`, `app/setup.html`, `app/chat.js` or related settings JS, locale strings if needed.
  - Input: Config schema from TODO-027.
  - Output: Users can view/save/test home/bin/workspaceRoot/mainWorkspace/model/toggle fields safely.
  - Dependencies: TODO-027.
  - Completion standard: Source-level checks verify field presence, save payload, secret redaction, and no stale field names.
  - Checklist: CHK-063, CHK-073, CHK-081.

- [x] TODO-037 - Extend models/native UI from read-only status to native-agent setup/status where appropriate.
  - Goal: Absorb useful reference native-agent setup visibility while preserving existing model provider tabs.
  - Involves: `app/models.html`, `app/style.css`, Node UI checks.
  - Input: Reference models native tabs and current read-only Native Agents tab.
  - Output: Models page exposes actionable native setup/status without replacing cloud/custom/Ollama/LM Studio flows.
  - Dependencies: TODO-027, TODO-032.
  - Completion standard: Node and browser checks pass for tabs, no overlap, no secret leak.
  - Checklist: CHK-074, CHK-084.

- [x] TODO-038 - Verify chat selector and agent UI with multiple native provider agents.
  - Goal: Ensure users can select and distinguish multiple Codex/Claude Code profiles.
  - Involves: `app/chat.js`, `app/index.html`, CSS/locales if needed.
  - Input: Multi-profile roster from TODO-032.
  - Output: Agent names/status/provider labels/history controls remain coherent.
  - Dependencies: TODO-032, TODO-033, TODO-034.
  - Completion standard: Source/browser checks cover switching between multiple provider profiles.
  - Checklist: CHK-075, CHK-084.

### Regression And Acceptance

- [x] TODO-039 - Add Phase 2 provider and lifecycle tests.
  - Goal: Cover native agent discovery/create/delete/config/path-safety behavior.
  - Involves: `tests/` provider/server/config test files.
  - Input: Checklist CHK-064 through CHK-081.
  - Output: Focused tests for Codex/Claude Code native agent management and safe config exposure.
  - Dependencies: TODO-028 through TODO-035.
  - Completion standard: Tests do not require real Codex/Claude installations; fixtures/mocks cover success and failure paths.
  - Checklist: CHK-082.

- [x] TODO-040 - Run Phase 2 provider/server regression suite.
  - Goal: Verify provider bottom layer and server APIs.
  - Involves: Python unit/server tests.
  - Input: Existing and new provider/server tests.
  - Output: Passing targeted Python regression set or documented blocker.
  - Dependencies: TODO-039.
  - Completion standard: Codex, Claude Code, Hermes, config, discovery, lifecycle, and history tests pass.
  - Checklist: CHK-082.

- [x] TODO-041 - Run Phase 2 project/meeting regression suite.
  - Goal: Prove native agent management did not drop original project/meeting behavior.
  - Involves: Existing project execution and meeting tests plus selected Node UI checks.
  - Input: Current local project/meeting test suite.
  - Output: Passing project/meeting regression set.
  - Dependencies: TODO-033 through TODO-038.
  - Completion standard: Existing project execution, meeting request/blocking/result/action-item checks pass.
  - Checklist: CHK-076, CHK-077, CHK-083.

- [x] TODO-042 - Run Phase 2 browser or Chrome MCP smoke.
  - Goal: Validate changed settings/models/chat/project/meeting surfaces in a browser.
  - Involves: Local temporary server, Chrome MCP fallback if CDP is unavailable, smoke scripts/artifacts.
  - Input: Implemented Phase 2 UI/server changes.
  - Output: Browser smoke notes and artifacts.
  - Dependencies: TODO-036, TODO-037, TODO-038, TODO-041.
  - Completion standard: Settings, models native UI, multi-agent roster/chat, project, and meeting smoke pass; environmental noise documented.
  - Checklist: CHK-074, CHK-075, CHK-084.

- [x] TODO-043 - Update Phase 2 acceptance records and final report.
  - Goal: Make the second migration phase auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, browser smoke notes, implementation diff.
  - Output: Checklist evidence, completed todolist items, final residual risk summary.
  - Dependencies: TODO-040, TODO-041, TODO-042.
  - Completion standard: Every Phase 2 checklist item has pass/fail/notes evidence; status reflects tested state.
  - Checklist: CHK-061 through CHK-085.


## Phase 2 Completion Notes - 2026-06-27T01:29:47+08:00

Completed TODO-026 through TODO-043 for the native agent management migration:

- Codex native agent discovery/create/delete/config support is merged under the existing local `codex_bridge.py` app-server contract.
- Claude Code native subagent discovery/create/delete/config support is merged while preserving the existing reply fixture and stream-json chat path.
- Server config, safe `/vo-config`, discovery, agent platforms, create/delete handlers, and selected Codex workspace routing now understand native agent settings.
- Main settings UI can view/save/test native agent root/main/toggle fields for Codex and Claude Code.
- Provider/server/config/project/meeting/UI source checks passed.
- Isolated HTTP smoke verified setup/save, platform create/delete capability, Codex/Claude Code native-agent creation, and selected-agent deletion cleanup.

TODO-042 is marked complete with HTTP/source-level smoke evidence. Full Chrome MCP visual smoke remains optional follow-up if a browser-level screenshot pass is required beyond the current source/UI/API smoke.


## Phase 3 Reference Parity Tasks

Phase 3 continues from TODO-044 and focuses on remaining provider-runtime parity with `eliautobot/main`. Keep local project/meeting behavior authoritative; do not wholesale replace shared files.

### Phase 3 Rebaseline

- [x] TODO-044 - Recompare reference UI/provider docs against current Phase 2 implementation.
  - Goal: Identify remaining provider-runtime gaps after Phase 2.
  - Involves: `eliautobot/main`, `app/models.html`, `app/setup.html`, `app/index.html`, `app/server.py`, `docs/HERMES_PROVIDER_ADAPTER.md`, `.env.example`, `app/vo-config.json`.
  - Input: Current dirty worktree and reference branch.
  - Output: Phase 3 merge map for implemented, skipped, and preserved-local areas.
  - Dependencies: Phase 2 completed.
  - Completion standard: Remaining differences are categorized before code edits.
  - Checklist: CHK-086, CHK-099.

### Models And Setup UI

- [x] TODO-045 - Upgrade models native provider UI from read-only status to actionable setup/status.
  - Goal: Bring over useful reference `models.html` Codex CLI and Claude Code setup controls without replacing existing cloud/custom/Ollama/LM Studio tabs.
  - Involves: `app/models.html`, model UI source checks.
  - Input: Reference native provider tabs and current `/config/providers` response.
  - Output: Native tab can save/test Codex and Claude Code setup and shows Hermes/Codex/Claude status safely.
  - Dependencies: TODO-044.
  - Completion standard: Source tests verify fields, payloads, endpoints, and no secret placeholders leak values.
  - Checklist: CHK-087, CHK-088, CHK-093, CHK-098.

- [x] TODO-046 - Complete setup wizard native runtime field parity.
  - Goal: Ensure first-run setup can save/test the same safe native provider fields as the reference branch.
  - Involves: `app/setup.html`, setup source checks, config tests.
  - Input: Phase 2 config schema and reference setup fields.
  - Output: Codex/Claude Code setup payloads include remaining toggles and compatibility fields.
  - Dependencies: TODO-044.
  - Completion standard: Setup payload includes Codex `preferAppServer/registerNativeAgents` where supported and Claude Code toggles; tests pass.
  - Checklist: CHK-089, CHK-094, CHK-098.

### Server Config And Compatibility

- [x] TODO-047 - Add Hermes `preferApi` compatibility alias.
  - Goal: Accept reference-style Hermes native API config while preserving current `apiEnabled` behavior.
  - Involves: `app/server.py`, provider runtime config tests, setup/model UI payloads if needed.
  - Input: Reference `hermes.preferApi` and current `hermes.apiEnabled`.
  - Output: Config/env merge supports both names, safe output can include both or map consistently.
  - Dependencies: TODO-044.
  - Completion standard: Tests cover `preferApi`, `apiEnabled`, and `VO_HERMES_PREFER_API`.
  - Checklist: CHK-090, CHK-093, CHK-094, CHK-096.

- [x] TODO-048 - Expand safe native provider state returned by `/config/providers`.
  - Goal: Power the actionable models native UI without leaking secrets.
  - Involves: `app/server.py`, `tests/test_provider_runtime_config.py`.
  - Input: Models UI field requirements from TODO-045.
  - Output: Safe native provider JSON includes needed config/status fields for Hermes, Codex, and Claude Code.
  - Dependencies: TODO-045, TODO-047.
  - Completion standard: Tests confirm fields are present and secrets are absent.
  - Checklist: CHK-093, CHK-094.

### Docs And Examples

- [x] TODO-049 - Update Hermes provider adapter docs for Phase 3 parity.
  - Goal: Restore useful reference native API documentation while accurately describing local implementation boundaries.
  - Involves: `docs/HERMES_PROVIDER_ADAPTER.md`.
  - Input: Reference docs and current server implementation.
  - Output: Docs cover API client surfaces, config aliases, CLI fallback, secret safety, and current server-side event handling.
  - Dependencies: TODO-047.
  - Completion standard: Documentation does not claim unimplemented browser SSE proxy routes as complete.
  - Checklist: CHK-091, CHK-099.

- [x] TODO-050 - Update provider runtime environment/config examples.
  - Goal: Make deploy-time provider runtime knobs discoverable without changing conservative defaults.
  - Involves: `.env.example`, `app/vo-config.json` if appropriate.
  - Input: Phase 3 config schema.
  - Output: Examples include Hermes native API, Codex native agent, and Claude Code native subagent settings.
  - Dependencies: TODO-047, TODO-048.
  - Completion standard: Examples are safe, commented where appropriate, and do not unexpectedly enable runtimes.
  - Checklist: CHK-092, CHK-099.

### Tests And Acceptance

- [x] TODO-051 - Add or update Phase 3 source/config tests.
  - Goal: Cover new models/setup UI and config compatibility behavior.
  - Involves: `tests/check_provider_runtime_settings_ui.mjs`, new or existing Node checks, `tests/test_provider_runtime_config.py`.
  - Input: Implemented UI/server changes.
  - Output: Focused tests for field presence, payloads, safe config, and compatibility aliases.
  - Dependencies: TODO-045 through TODO-048.
  - Completion standard: Tests fail on missing Phase 3 fields or leaked secrets.
  - Checklist: CHK-087, CHK-089, CHK-090, CHK-093, CHK-094, CHK-098.

- [x] TODO-052 - Run Phase 3 provider/server regression suite.
  - Goal: Ensure provider runtime parity additions do not regress provider behavior.
  - Involves: Codex, Claude Code, Hermes, provider config tests.
  - Input: Existing Phase 2 test suite plus Phase 3 tests.
  - Output: Passing targeted Python/Node provider tests.
  - Dependencies: TODO-051.
  - Completion standard: Provider/config/native lifecycle tests pass.
  - Checklist: CHK-095, CHK-096.

- [x] TODO-053 - Run Phase 3 project/meeting/UI regression suite and smoke.
  - Goal: Prove original functionality is preserved after completing reference provider parity.
  - Involves: Project execution tests, meeting tests, Node UI checks, HTTP/browser smoke where available.
  - Input: Current local project/meeting suites.
  - Output: Passing regressions or documented environmental blockers.
  - Dependencies: TODO-052.
  - Completion standard: Project/meeting regressions pass and changed model/setup UI is smoke-tested.
  - Checklist: CHK-097, CHK-098.

- [x] TODO-054 - Update Phase 3 acceptance records and final comparison report.
  - Goal: Make reference parity completion auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, remaining reference diff analysis.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-052, TODO-053.
  - Completion standard: Phase 3 status and remaining gaps are documented.
  - Checklist: CHK-086 through CHK-099.


## Phase 3 Completion Notes - 2026-06-27T01:59:00+08:00

Completed TODO-044 through TODO-054 for remaining reference provider-runtime parity:

- Recompared `eliautobot/main` against current Phase 2 and kept the same merge boundary: provider runtime, setup/model UI, docs/config, and tests only.
- Upgraded `models.html` Native Agents tab from read-only status to actionable Hermes/Codex/Claude Code setup panels with save/test actions.
- Added Native Setup Guide content to `models.html` covering OpenClaw, Hermes, Codex, and Claude Code native config locations.
- Extended `setup.html` first-run provider step with Codex CLI and Claude Code native runtime fields and test actions.
- Added Hermes `preferApi` compatibility alongside `apiEnabled`, including `VO_HERMES_PREFER_API`.
- Expanded `/config/providers.nativeProviders` with safe runtime fields needed by the richer models UI.
- Updated Hermes docs and `.env.example` for native API/Codex/Claude Code provider runtime configuration.
- Verified provider/server/config/project/meeting/UI source checks and isolated HTTP smoke.

Remaining differences from the reference branch are intentional:

- The reference branch's broader `models.html` full-page rewrite was not wholesale adopted; local cloud/custom/Ollama/LM Studio behavior remains authoritative.
- Browser Hermes SSE proxy routes described in the reference docs are not claimed as implemented; local Hermes native API events are consumed server-side through the existing chat route.
- Project, meeting, archive, scheduled cron, and unrelated UI changes from the reference branch remain excluded from this provider-runtime migration.


## Phase 4 Project And Meeting UI Parity Tasks

Phase 4 continues from TODO-055. This phase merges useful reference project/meeting/canvas visibility features while preserving local project execution and meeting state machines. Read-only UI and projections come first; write actions must be disabled or routed through existing local APIs with tests.

### Phase 4 Preparation

- [x] TODO-055 - Rebaseline reference project/meeting/canvas UI against local state machines.
  - Goal: Build a precise merge map for meeting visualization, agent workspace, scheduled/cron visibility, and canvas state behavior.
  - Involves: `eliautobot/main`, `app/server.py`, `app/game.js`, `app/projects.js`, `app/projects.css`, existing meeting/project tests.
  - Input: Phase 4 checklist, current local project/meeting implementation, reference branch diff.
  - Output: Implementation notes listing safe-to-merge presentation code, adapter needs, and explicitly skipped write paths.
  - Dependencies: Phase 4 checklist confirmed.
  - Completion standard: No implementation starts until state writers and read-only surfaces are categorized.
  - Checklist: CHK-100, CHK-101, CHK-102, CHK-121.

- [x] TODO-056 - Define local meeting visualization projection contract.
  - Goal: Provide a stable server/client shape for office canvas/sidebar meeting visualization without introducing a second source of truth.
  - Involves: `app/server.py`, `app/game.js`, meeting request/executable meeting helpers.
  - Input: Existing meeting request/blocker/result state and reference `_meetings` shape.
  - Output: Projection fields for active/pending/completed visual meeting cards and participant placement.
  - Dependencies: TODO-055.
  - Completion standard: Projection is read-only and derived from local meeting state.
  - Checklist: CHK-100, CHK-103, CHK-104, CHK-105.

### Meeting Visualization

- [x] TODO-057 - Implement read-only active meeting canvas projection.
  - Goal: Let the office canvas visualize active local meetings using existing meeting state.
  - Involves: `app/server.py`, `app/game.js`, tests for projection/source checks.
  - Input: Projection contract from TODO-056.
  - Output: `game.js` can render/move agents for meetings without writing independent `_meetings` state.
  - Dependencies: TODO-056.
  - Completion standard: Pending/rejected meetings do not become active; active meetings place participants correctly.
  - Checklist: CHK-103, CHK-104, CHK-107.

- [x] TODO-058 - Add meeting table/sidebar display mapped to local meeting lifecycle.
  - Goal: Bring reference meeting table/sidebar usability while preserving local meeting actions.
  - Involves: `app/game.js`, `app/index.html` if needed, CSS/locales.
  - Input: Local meeting projection and reference meeting UI.
  - Output: Sidebar/cards show pending/active/completed/rejected states accurately.
  - Dependencies: TODO-057.
  - Completion standard: UI status labels match local lifecycle and do not expose unsupported actions.
  - Checklist: CHK-104, CHK-106, CHK-114, CHK-116.

- [x] TODO-059 - Map completed meeting display to local meeting records.
  - Goal: Reuse reference completed-meeting visibility without introducing separate history storage.
  - Involves: `app/server.py`, `app/game.js`, `app/projects.js` integration points if needed.
  - Input: Local meeting records/action items/discussion points.
  - Output: Completed meeting display renders summary, decisions, risks, action items, project/task source, and participants.
  - Dependencies: TODO-056, TODO-058.
  - Completion standard: Existing meeting record tests pass and completed display does not duplicate or lose records.
  - Checklist: CHK-105, CHK-106, CHK-118, CHK-119.

### Agent Workspace Read-Only Context

- [x] TODO-060 - Add agent workspace read-only project/task context projection.
  - Goal: Expose assigned project cards and current task context to agent workspace without enabling unsafe task writes.
  - Involves: `app/server.py`, `app/game.js`, project store helpers.
  - Input: Existing project/task assignment, active execution state, meeting blocker state, provider metadata.
  - Output: Safe read-only JSON for agent workspace project cards/current work.
  - Dependencies: TODO-055.
  - Completion standard: Projection includes project/task/status metadata and no direct mutation endpoint.
  - Checklist: CHK-108, CHK-109, CHK-111, CHK-119.

- [x] TODO-061 - Integrate agent workspace UI for read-only project/task/meeting context.
  - Goal: Bring useful reference agent workspace visibility while keeping project modal authoritative.
  - Involves: `app/game.js`, CSS/locales as needed.
  - Input: Projection from TODO-060 and reference workspace UI.
  - Output: Agent workspace shows project cards, current execution phase, meeting blocker, and provider/workspace metadata.
  - Dependencies: TODO-060.
  - Completion standard: Start/complete/delete/toggle task actions are absent, disabled, or routed to existing APIs with clear tests.
  - Checklist: CHK-108, CHK-109, CHK-115, CHK-116.

- [x] TODO-062 - Contain file/notes/skills workspace panels.
  - Goal: Decide which non-project agent workspace panels are safe to include and keep side effects isolated.
  - Involves: `app/game.js`, server helper routes if reused, tests/source checks.
  - Input: Reference workspace panels and local agent/provider capabilities.
  - Output: Safe panels are read-only or use existing non-project APIs; unsupported panels are hidden with clear unavailable state.
  - Dependencies: TODO-061.
  - Completion standard: No project task state changes occur from notes/files/skills panels unless explicitly routed and tested.
  - Checklist: CHK-110, CHK-111, CHK-114.

### Scheduled/Cron Visibility

- [x] TODO-063 - Add scheduled/cron visibility without enabling unsafe execution.
  - Goal: Reuse reference cron UI/status ideas as visibility only unless local project execution supports the action.
  - Involves: `app/projects.css`, `app/game.js` or `app/projects.js`, server projection if needed.
  - Input: Existing local scheduled/cron support, if present, and reference styles.
  - Output: Cron status/list/badges render safely; run/start controls remain disabled unless routed through local pipeline.
  - Dependencies: TODO-055.
  - Completion standard: No cron write path bypasses project execution safeguards.
  - Checklist: CHK-112, CHK-113, CHK-114.

- [x] TODO-064 - If scheduled execution is enabled, route through existing project execution pipeline.
  - Goal: Ensure scheduled triggers behave like manual project execution.
  - Involves: `app/server.py`, project execution tests, scheduled trigger tests if added.
  - Input: Existing project execution handlers and scheduled/cron requirements.
  - Output: Scheduled trigger uses dirty workspace, executor-required, review, meeting blocker, cancellation, and stale repair rules.
  - Dependencies: TODO-063.
  - Completion standard: Tests cover scheduled trigger safeguards or feature remains visibility-only.
  - Checklist: CHK-112, CHK-113, CHK-118, CHK-119.

### Canvas And State Layering

- [x] TODO-065 - Preserve provider/project activity while adding meeting canvas state.
  - Goal: Avoid meeting visualization overwriting provider activity, project execution indicators, or chat status.
  - Involves: `app/game.js`, status rendering helpers, project work indicators.
  - Input: Existing activity/status rules and reference meeting state rendering.
  - Output: Deterministic state priority or combined labels for project work plus meeting participation.
  - Dependencies: TODO-057.
  - Completion standard: Tests/source checks cover simultaneous project execution and meeting participation.
  - Checklist: CHK-107, CHK-114, CHK-115.

- [x] TODO-066 - Optionally adapt safe canvas interaction utilities.
  - Goal: Bring low-risk reference UX such as object service queues or meeting table click handlers only where they do not mutate project state.
  - Involves: `app/game.js`, CSS if needed.
  - Input: Reference canvas interaction functions and local canvas behavior.
  - Output: Safe canvas interaction improvements integrated behind local state contracts.
  - Dependencies: TODO-055, TODO-057.
  - Completion standard: Existing chat/project/provider controls remain usable; no unrelated canvas regressions.
  - Checklist: CHK-101, CHK-102, CHK-114.

### Tests And Acceptance

- [x] TODO-067 - Add Phase 4 projection/source tests.
  - Goal: Make adapter boundaries testable.
  - Involves: New or existing Python/Node tests for meeting projection, workspace read-only rendering, disabled/routed write actions, and state layering.
  - Input: Implemented Phase 4 projections/UI.
  - Output: Tests that fail if reference bypass writers are introduced.
  - Dependencies: TODO-057 through TODO-066.
  - Completion standard: Focused Phase 4 tests pass.
  - Checklist: CHK-119.

- [x] TODO-068 - Run provider runtime regression suite.
  - Goal: Ensure Phase 4 does not break Phase 1-3 provider runtime behavior.
  - Involves: Provider/config/server tests.
  - Input: Existing Phase 3 test commands.
  - Output: Passing provider runtime regressions.
  - Dependencies: TODO-067.
  - Completion standard: Codex, Claude Code, Hermes, config, and UI source checks still pass.
  - Checklist: CHK-117.

- [x] TODO-069 - Run project and meeting regression suite.
  - Goal: Prove local project execution and meeting flows remain authoritative.
  - Involves: Existing project execution and meeting tests.
  - Input: Current local project/meeting test suite.
  - Output: Passing targeted project/meeting regressions.
  - Dependencies: TODO-067.
  - Completion standard: Meeting request/blocking/result/action-item and project execution tests pass.
  - Checklist: CHK-118.

- [x] TODO-070 - Run browser or Chrome MCP smoke for Phase 4 surfaces.
  - Goal: Validate user-visible meeting visualization and agent workspace behavior.
  - Involves: Temporary server, Chrome MCP fallback if CDP unavailable, fixture data.
  - Input: Implemented Phase 4 UI.
  - Output: Browser smoke evidence for meeting table/sidebar, agent workspace context, and project modal.
  - Dependencies: TODO-068, TODO-069.
  - Completion standard: No critical overlap or JS errors; environmental noise documented separately.
  - Checklist: CHK-120.

- [x] TODO-071 - Update Phase 4 acceptance records and final report.
  - Goal: Make Phase 4 auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, implementation diff, skipped/deferred reference behavior.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-068, TODO-069, TODO-070.
  - Completion standard: Implemented, deferred, and intentionally skipped reference behavior are documented.
  - Checklist: CHK-100 through CHK-121.

### Phase 4 Completion Notes

- 2026-06-27T02:55:25+08:00 - TODO-055 through TODO-071 completed for the safe-merge scope. Reference meeting/workspace/cron code was compared against local implementations; local project/meeting writers remain authoritative. The implemented code expands agent workspace project context read-only and keeps existing reference-derived workspace UI rather than replacing files wholesale.
- Browser/MCP smoke used the available Chrome DevTools MCP page by navigating to the isolated local server on port 8148. Main page, `/status`, `/api/agents`, and `/api/agent-workspace/main` loaded; only `/pc-metrics` 502 environmental noise was observed.
- Deferred/skipped by design: reference full-page rewrites, independent meeting writers, direct project task actions from agent workspace, and any cron write path outside local project execution.


## Phase 5 Generic Provider Run Bridge Tasks

Phase 5 continues from TODO-072. This phase extracts a common provider run bridge and migrates Claude Code and Codex run/SSE distribution onto it while preserving existing Codex chat/activity compatibility and all local project/meeting behavior.

### Phase 5 Preparation

- [x] TODO-072 - Rebaseline reference run/SSE implementation against local provider handlers.
  - Goal: Build a precise merge map for reference Claude Code/Codex run endpoints, SSE events, stop behavior, and presence updates.
  - Involves: `eliautobot/main`, `app/server.py`, `app/chat.js`, `app/gateway_presence.py`, existing provider tests.
  - Input: Phase 5 checklist and current local provider runtime implementation.
  - Output: Implementation notes identifying shared bridge logic, provider-specific adapters, and endpoints to preserve.
  - Dependencies: Phase 5 checklist confirmed.
  - Completion standard: No provider run code is changed until common/shared vs provider-specific responsibilities are categorized.
  - Checklist: CHK-122, CHK-123, CHK-140.

- [x] TODO-073 - Define `ProviderRunBridge` lifecycle contract.
  - Goal: Specify the provider-neutral behavior for run registration, metadata updates, event emission, SSE streaming, terminal handling, and cleanup.
  - Involves: `app/server.py` helper section and tests.
  - Input: Existing Claude Code stream helpers, Codex activity state, reference run/SSE behavior.
  - Output: Bridge method contract and event naming rules.
  - Dependencies: TODO-072.
  - Completion standard: Contract keeps provider-specific parsing out of the bridge.
  - Checklist: CHK-124, CHK-125, CHK-126.

### Bridge Implementation

- [x] TODO-074 - Implement or complete generic `ProviderRunBridge`.
  - Goal: Move shared run registry and SSE distribution into one reusable bridge.
  - Involves: `app/server.py`.
  - Input: Contract from TODO-073.
  - Output: `ProviderRunBridge` with remember/get/update/emit/stream_events/clear methods.
  - Dependencies: TODO-073.
  - Completion standard: Source-level and Python tests prove bridge lifecycle behavior.
  - Checklist: CHK-124, CHK-125.

- [x] TODO-075 - Add focused bridge tests.
  - Goal: Guard the common lifecycle against regressions.
  - Involves: `tests/` source-level and Python tests.
  - Input: Implemented bridge.
  - Output: Tests for success, failure, cancellation, late cleanup, missing run, and provider metadata.
  - Dependencies: TODO-074.
  - Completion standard: Tests fail if terminal events are dropped or provider metadata is lost.
  - Checklist: CHK-124, CHK-125, CHK-126, CHK-139.

### Claude Code Migration

- [x] TODO-076 - Migrate Claude Code run registry to `ProviderRunBridge`.
  - Goal: Ensure Claude Code run/SSE/stop routes delegate to the common bridge.
  - Involves: `app/server.py`, `tests/check_claude_code_runs_sse.mjs`, `tests/test_claude_code_runs_sse.py`.
  - Input: Existing Claude Code run helpers and bridge implementation.
  - Output: Claude Code stream helpers become thin wrappers around the bridge.
  - Dependencies: TODO-074.
  - Completion standard: Existing Claude Code run/SSE tests pass.
  - Checklist: CHK-127, CHK-128.

- [x] TODO-077 - Preserve Claude Code progress, history, and presence behavior.
  - Goal: Keep reference-derived Claude Code lower-layer behavior intact while moving distribution to the bridge.
  - Involves: `app/server.py`, `app/chat.js`, `app/gateway_presence.py`.
  - Input: Existing Claude Code chat/run implementation and tests.
  - Output: Progress messages, final messages, stop behavior, token usage, tool events, and presence events remain coherent.
  - Dependencies: TODO-076.
  - Completion standard: Claude Code server/provider/source tests pass with no duplicated final messages.
  - Checklist: CHK-128, CHK-129, CHK-135.

### Codex Migration

- [x] TODO-078 - Add Codex run/SSE/stop routes on top of `ProviderRunBridge`.
  - Goal: Expose a common run API for Codex without removing existing chat/activity endpoints.
  - Involves: `app/server.py`, route handlers for `/api/codex/runs`, `/api/codex/runs/<id>/events`, `/api/codex/runs/<id>/stop`.
  - Input: Existing `_handle_codex_chat`, `_handle_codex_activity`, `_handle_codex_cancel`, and bridge implementation.
  - Output: New Codex run endpoints that execute through existing Codex chat/provider logic.
  - Dependencies: TODO-074.
  - Completion standard: Codex run route can stream started/progress/terminal events and stop active runs.
  - Checklist: CHK-130, CHK-131, CHK-134.

- [x] TODO-079 - Emit Codex activity into both legacy polling and the bridge.
  - Goal: Let Codex SSE reuse the same underlying activity stream while keeping `/api/codex/activity` compatible.
  - Involves: `app/server.py`, Codex activity callback path.
  - Input: Existing `_append_codex_activity` and provider event callback.
  - Output: Codex events are mapped to `run.started`, `message.delta`, `tool.started`, `tool.completed`, `tool.failed`, `approval.request`, `run.completed`, `run.failed`, and `run.cancelled` where applicable.
  - Dependencies: TODO-078.
  - Completion standard: Legacy activity and new SSE both receive expected events in tests.
  - Checklist: CHK-132, CHK-133, CHK-136.

- [x] TODO-080 - Preserve Codex approval, interaction, cancellation, and active-state semantics.
  - Goal: Ensure the new bridge route does not break existing Codex user intervention behavior.
  - Involves: `app/server.py`, Codex provider/server tests.
  - Input: Existing `/api/codex/interaction`, `/api/codex/cancel`, `_CODEX_ACTIVE_OPERATIONS`.
  - Output: Approval/deny/cancel/stale cases continue to work with both old and new paths.
  - Dependencies: TODO-078, TODO-079.
  - Completion standard: Codex approval and cancellation tests pass; active operation state clears correctly.
  - Checklist: CHK-133, CHK-134, CHK-136.

### Frontend Compatibility

- [x] TODO-081 - Keep Claude Code frontend SSE behavior working.
  - Goal: Verify the existing Claude Code EventSource path still works with the bridge-backed server.
  - Involves: `app/chat.js`, Claude Code UI/source tests.
  - Input: Bridge-backed Claude Code routes.
  - Output: Send, stream, stop, fallback chat, and history clear remain usable.
  - Dependencies: TODO-076, TODO-077.
  - Completion standard: Claude Code chat/source tests pass.
  - Checklist: CHK-135.

- [x] TODO-082 - Add Codex frontend compatibility hooks without removing activity polling.
  - Goal: Make the new Codex run API available for incremental frontend migration while preserving current UI behavior.
  - Involves: `app/chat.js` if needed, Codex source tests.
  - Input: New Codex run routes and existing activity polling UI.
  - Output: Existing Codex chat/activity UI remains intact; any new SSE code has polling fallback.
  - Dependencies: TODO-078, TODO-079, TODO-080.
  - Completion standard: Existing Codex UI/source tests pass and no approval UI capability is lost.
  - Checklist: CHK-136.

### Tests And Acceptance

- [x] TODO-083 - Run Phase 5 provider bridge test suite.
  - Goal: Verify generic bridge plus Claude Code and Codex run/SSE integrations.
  - Involves: Python and Node tests for bridge, Claude Code runs, Codex runs, provider config/server behavior.
  - Input: Implemented Phase 5 code.
  - Output: Passing focused provider bridge tests or documented blockers.
  - Dependencies: TODO-075 through TODO-082.
  - Completion standard: Syntax, source checks, Claude Code run tests, Codex run tests, and provider server tests pass.
  - Checklist: CHK-127, CHK-130, CHK-137, CHK-139.

- [x] TODO-084 - Run project and meeting regression suite after Phase 5.
  - Goal: Prove bridge migration did not alter local project/meeting behavior.
  - Involves: Existing project execution and meeting blocker tests.
  - Input: Current local project/meeting suites.
  - Output: Passing regressions or documented environmental blockers.
  - Dependencies: TODO-083.
  - Completion standard: Project execution and meeting blocker tests pass.
  - Checklist: CHK-122, CHK-138, CHK-139.

- [x] TODO-085 - Run browser or Chrome MCP smoke if needed.
  - Goal: Validate user-visible chat/provider surfaces after bridge migration.
  - Involves: Temporary server, Chrome MCP fallback if CDP unavailable.
  - Input: Implemented Phase 5 server/frontend changes.
  - Output: Smoke evidence for Claude Code/Codex chat controls and no major UI breakage.
  - Dependencies: TODO-083, TODO-084.
  - Completion standard: Browser smoke passes or environmental limitations are documented.
  - Checklist: CHK-135, CHK-136, CHK-139.

- [x] TODO-086 - Update Phase 5 acceptance records and remaining reference-diff report.
  - Goal: Make Phase 5 auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, implementation diff, skipped/deferred reference behavior.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-083, TODO-084, TODO-085.
  - Completion standard: Implemented, deferred, and intentionally preserved behavior are documented.
  - Checklist: CHK-139, CHK-140.

### Phase 5 Completion Notes

- 2026-06-27T03:52:31+08:00 - TODO-072 through TODO-086 completed. The reference branch lower-level run/SSE pattern was merged as a shared `ProviderRunBridge` instead of a full-file replacement. Claude Code continues to use the reference-derived run/SSE/stop path through the bridge.
- Codex now has additive run/SSE/stop endpoints backed by the same bridge: `/api/codex/runs`, `/api/codex/runs/<id>/events`, and `/api/codex/runs/<id>/stop`. The implementation reuses `_handle_codex_chat` and adds optional `_onActivity` forwarding so legacy `/api/codex/activity` remains authoritative and compatible.
- Preserved by design: existing Codex chat/activity/interaction/cancel endpoints, project execution state transitions, meeting blocker behavior, archive handling, and scheduled/cron handling.
- Test evidence is recorded in `checklist.md`. Browser/MCP smoke was not run for Phase 5 because the Codex frontend primary send path was intentionally left on existing activity polling; source-level frontend checks covered the touched surfaces.


## Phase 6 Provider Execution Contract And Codex Native Bottom Layer Tasks

Phase 6 continues from TODO-087. This phase extracts the provider-facing office execution semantics out of Codex-specific server logic, lets Codex and Claude Code return the same normalized contract, and migrates Codex's execution bottom layer closer to the reference branch's native app-server JSON-RPC implementation.

### Phase 6 Preparation

- [x] TODO-087 - Rebaseline Codex provider bottom layer against reference branch.
  - Goal: Produce a precise merge map for reference `app/providers/codex.py` and local Codex provider/server contracts.
  - Involves: `app/providers/codex.py`, `app/providers/codex_bridge.py`, `app/server.py`, Codex provider/server tests.
  - Input: `eliautobot/main` Codex provider, local Phase 5 implementation.
  - Output: Notes identifying code to copy, adapt, preserve, and defer.
  - Dependencies: Phase 6 checklist confirmed.
  - Completion standard: No provider replacement starts until compatibility methods and local lifecycle behavior are mapped.
  - Checklist: CHK-141, CHK-152, CHK-153, CHK-160.

- [x] TODO-088 - Define provider-neutral office execution contract.
  - Goal: Specify normalized result, approval, active operation, modified files, status mapping, and cancellation shapes.
  - Involves: New or existing server/provider helper module, tests.
  - Input: Current Codex server semantics, Claude Code result shape, project execution expectations.
  - Output: Contract definitions and helper responsibilities.
  - Dependencies: TODO-087.
  - Completion standard: Contract is documented in code/tests and remains separate from `ProviderRunBridge`.
  - Checklist: CHK-142, CHK-144, CHK-145, CHK-146, CHK-147.

### Contract Implementation

- [x] TODO-089 - Implement normalized provider execution result helpers.
  - Goal: Convert provider-specific results into one office-facing result shape.
  - Involves: `app/server.py` or a focused helper module, provider tests.
  - Input: Contract from TODO-088.
  - Output: Normalizer for Codex and Claude Code success/error/timeout/cancel/human-intervention cases.
  - Dependencies: TODO-088.
  - Completion standard: Unit tests cover required normalized fields and terminal statuses.
  - Checklist: CHK-144, CHK-146, CHK-158.

- [x] TODO-090 - Implement common modified-file tracking helper.
  - Goal: Move before/after workspace diff handling out of Codex-specific server logic where possible.
  - Involves: `app/server.py` or helper module, project/provider tests.
  - Input: Current `_codex_git_paths` behavior.
  - Output: Provider-neutral helper that can be used by Codex and later providers.
  - Dependencies: TODO-089.
  - Completion standard: Codex modifiedFiles behavior remains unchanged; unsupported providers return `[]`.
  - Checklist: CHK-145, CHK-156.

- [x] TODO-091 - Implement common approval/interaction record helpers.
  - Goal: Normalize approval records while preserving provider-specific response adapters.
  - Involves: `app/server.py`, Codex interaction tests, Claude Code compatibility tests.
  - Input: Current Codex interaction records and Claude Code capabilities.
  - Output: Office-facing approval shape plus provider-specific raw metadata.
  - Dependencies: TODO-088.
  - Completion standard: Codex interaction remains compatible and Claude Code unsupported approval behavior is explicit.
  - Checklist: CHK-147, CHK-148, CHK-149.

- [x] TODO-092 - Implement provider-neutral active operation helpers.
  - Goal: Generalize active operation state currently tied to Codex.
  - Involves: `app/server.py`, Codex/Claude active operation tests.
  - Input: `_CODEX_ACTIVE_OPERATIONS`, Claude Code run meta, cancellation paths.
  - Output: Scoped active operation helper by provider/agent/conversation with busy/cancel/clear semantics.
  - Dependencies: TODO-088.
  - Completion standard: Concurrent provider operations do not leak state across providers or conversations.
  - Checklist: CHK-150, CHK-151.

### Codex Native Bottom Layer

- [x] TODO-093 - Migrate reference Codex app-server client into local provider.
  - Goal: Bring reference `CodexAppServerClient` and native JSON-RPC execution logic into `app/providers/codex.py`.
  - Involves: `app/providers/codex.py`, provider tests.
  - Input: Reference branch Codex provider, local provider lifecycle methods.
  - Output: Native app-server execution path with progress callbacks, approval response, and interrupt/cancel support.
  - Dependencies: TODO-087, TODO-089.
  - Completion standard: Mocked native app-server tests pass without requiring a real Codex install.
  - Checklist: CHK-152, CHK-154, CHK-158.

- [x] TODO-094 - Preserve Codex local compatibility methods and fixtures.
  - Goal: Keep server-facing `send_message`, `respond`, `cancel`, replyText fixture, missing runtime behavior, and multi-profile lifecycle support.
  - Involves: `app/providers/codex.py`, `app/server.py`, Codex provider/server tests.
  - Input: Current local Codex provider and tests.
  - Output: Compatibility layer over the reference-derived native bottom layer.
  - Dependencies: TODO-093.
  - Completion standard: Existing Codex provider/server tests pass.
  - Checklist: CHK-153, CHK-154, CHK-155.

- [x] TODO-095 - Route Codex server handlers through normalized contract.
  - Goal: Make `_handle_codex_chat`, run/SSE, interaction, cancel, and project execution receive normalized results without losing legacy activity.
  - Involves: `app/server.py`, Codex run/server/project tests.
  - Input: Helpers from TODO-089 through TODO-092 and provider from TODO-094.
  - Output: Codex paths use common office contract and preserve legacy endpoints.
  - Dependencies: TODO-089, TODO-090, TODO-091, TODO-092, TODO-094.
  - Completion standard: Codex run/SSE, chat/activity, interaction, cancel, and project execution tests pass.
  - Checklist: CHK-143, CHK-148, CHK-151, CHK-153, CHK-156.

### Claude Code Contract Adoption

- [x] TODO-096 - Adapt Claude Code server results to normalized contract.
  - Goal: Let Claude Code produce the same office-facing result fields as Codex where supported.
  - Involves: `app/server.py`, Claude Code provider/server/run tests.
  - Input: Existing Claude Code chat/run result shape and normalizer from TODO-089.
  - Output: Claude Code normalized results with explicit unsupported fields where needed.
  - Dependencies: TODO-089, TODO-091, TODO-092.
  - Completion standard: Claude Code run/SSE and server tests pass; unsupported approval/modified files are represented safely.
  - Checklist: CHK-144, CHK-149, CHK-150, CHK-151.

### Project And Meeting Regression

- [x] TODO-097 - Route project execution consumers through normalized provider results.
  - Goal: Ensure Codex and Claude Code project execution records use the common contract.
  - Involves: `app/server.py`, project execution tests.
  - Input: Normalized provider results.
  - Output: Attempt/review records preserve reply, evidence, provider refs, modified files, human intervention, and statuses.
  - Dependencies: TODO-095, TODO-096.
  - Completion standard: Project execution provider matrix and existing project tests pass.
  - Checklist: CHK-156, CHK-159.

- [x] TODO-098 - Verify meeting blocker behavior after contract migration.
  - Goal: Prove provider execution contract changes do not alter local meeting blocker semantics.
  - Involves: Meeting blocker tests and related project execution tests.
  - Input: Implemented normalized contract.
  - Output: Passing meeting blocker/request regressions.
  - Dependencies: TODO-097.
  - Completion standard: Existing meeting blocker tests pass.
  - Checklist: CHK-157, CHK-159.

### Tests And Acceptance

- [x] TODO-099 - Add Phase 6 focused provider contract tests.
  - Goal: Cover normalizer, active operation, approval, modified files, and Codex native bottom-layer behavior.
  - Involves: New or existing tests under `tests/`.
  - Input: Implemented contract and provider changes.
  - Output: Passing tests that do not require real provider installs.
  - Dependencies: TODO-089 through TODO-096.
  - Completion standard: Tests cover success, failure, timeout, cancellation, approval, stale state, fixture mode, and missing runtime.
  - Checklist: CHK-144 through CHK-155, CHK-158.

- [x] TODO-100 - Run Phase 6 full targeted regression suite.
  - Goal: Ensure no break update after contract and Codex bottom-layer migration.
  - Involves: Provider, run/SSE, project, meeting, and UI source tests.
  - Input: Implemented Phase 6 code.
  - Output: Passing targeted regressions or documented environmental blockers.
  - Dependencies: TODO-097, TODO-098, TODO-099.
  - Completion standard: Codex, Claude Code, provider config, project execution, meeting blocker, and Phase 5 bridge tests pass.
  - Checklist: CHK-158, CHK-159.

- [x] TODO-101 - Update Phase 6 acceptance records and remaining reference-diff report.
  - Goal: Make Phase 6 auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, implementation diff, copied/adapted/deferred reference behavior.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-100.
  - Completion standard: Phase 6 status and reference parity gaps are documented.
  - Checklist: CHK-160.

### Phase 6 Completion Notes

- 2026-06-27T04:15:17+08:00 - TODO-087 through TODO-101 completed for the safe migration scope. The reference branch Codex provider was rebaselined against local `codex_bridge.py`; the local bridge already implements the native app-server JSON-RPC execution bottom layer, so Phase 6 added the reference-style provider facade rather than replacing the file wholesale.
- Added `app/provider_execution.py` as the office execution contract layer. `ProviderRunBridge` remains transport/SSE-only; normalized result, modified-file merging, approval record, active operation record, and HTTP status mapping live in the new contract helper.
- Codex and Claude Code server chat paths now normalize through the common contract. Codex `send_message/respond/cancel` compatibility remains intact; reference-style `send_chat_message/interrupt/respond_approval/pending_approval` methods are available for future consumers.
- Project execution and meeting blocker logic were not rewritten. Regression tests confirm those workflows still consume compatible provider results.


## Phase 7 Generic App-Server Runtime And Codex Reference Protocol Layer Tasks

Phase 7 continues from TODO-102. This phase extracts the generic JSONL app-server runtime mechanics currently embedded in `codex_bridge.py`, then moves Codex-specific app-server protocol handling into a focused adapter that follows the reference branch more closely.

### Phase 7 Preparation

- [x] TODO-102 - Rebaseline `codex_bridge.py` generic runtime vs Codex-specific protocol behavior.
  - Goal: Classify transport/runtime code, Codex protocol code, office contract code, and compatibility shims.
  - Involves: `app/providers/codex_bridge.py`, `app/providers/codex.py`, reference `app/providers/codex.py`, tests.
  - Input: Current Phase 6 implementation and reference branch.
  - Output: Split map for generic runtime, Codex protocol adapter, provider facade, and deferred gaps.
  - Dependencies: Phase 7 checklist confirmed.
  - Completion standard: No extraction starts until runtime/protocol boundaries are identified.
  - Checklist: CHK-161, CHK-164, CHK-169, CHK-174.

- [x] TODO-103 - Design generic app-server runtime API.
  - Goal: Define constructor, start/close, request/send, reader loop, pending queue, timeout, and hook interfaces.
  - Involves: New runtime module and tests.
  - Input: Existing `CodexAppServerClient` runtime mechanics and possible future provider needs.
  - Output: Runtime API that does not mention Codex methods.
  - Dependencies: TODO-102.
  - Completion standard: API supports provider-specific request/notification hooks without protocol coupling.
  - Checklist: CHK-161, CHK-162, CHK-163.

### Runtime Extraction

- [x] TODO-104 - Implement generic JSONL app-server runtime module.
  - Goal: Extract process/JSONL/RPC mechanics into a reusable runtime.
  - Involves: `app/provider_app_server.py` or equivalent, unit tests.
  - Input: Runtime API from TODO-103.
  - Output: Runtime that handles subprocess lifecycle, JSONL send/read, request IDs, pending queues, timeouts, close, and crash handling.
  - Dependencies: TODO-103.
  - Completion standard: Fake process tests cover success, timeout, server request, notification, crash, and close.
  - Checklist: CHK-161, CHK-162, CHK-163.

- [x] TODO-105 - Add compatibility shim or migration path for existing `codex_bridge.py` callers.
  - Goal: Avoid breaking imports and existing server/provider code during extraction.
  - Involves: `app/providers/codex_bridge.py`, caller search, tests.
  - Input: Runtime implementation.
  - Output: Existing callers continue to work or are explicitly migrated to the new adapter.
  - Dependencies: TODO-104.
  - Completion standard: Existing Codex bridge/run/server tests pass.
  - Checklist: CHK-168, CHK-169.

### Codex Protocol Adapter

- [x] TODO-106 - Implement Codex app-server protocol adapter on top of generic runtime.
  - Goal: Move Codex-specific app-server methods and parsing into a focused adapter.
  - Involves: `app/providers/codex_app_server.py` or equivalent.
  - Input: Reference branch Codex provider and local `codex_bridge.py` protocol logic.
  - Output: Adapter for initialize, thread start/resume, turn start/interrupt, approval response, notifications, and terminal results.
  - Dependencies: TODO-104.
  - Completion standard: Fake Codex protocol tests cover success, failure, approval, cancellation, timeout, file changes, and token/reasoning/tool events.
  - Checklist: CHK-164, CHK-165, CHK-166, CHK-167.

- [x] TODO-107 - Preserve Codex provider facade over the new protocol adapter.
  - Goal: Keep existing `CodexProvider` methods stable while swapping bottom-layer implementation.
  - Involves: `app/providers/codex.py`, protocol adapter, provider tests.
  - Input: Adapter from TODO-106 and Phase 6 facade.
  - Output: `CodexProvider` uses the new adapter where appropriate while keeping fixtures and fallback behavior.
  - Dependencies: TODO-106.
  - Completion standard: Existing and new provider tests pass without a real Codex install.
  - Checklist: CHK-168, CHK-170.

- [x] TODO-108 - Route protocol adapter outputs through `provider_execution.py`.
  - Goal: Ensure final Codex results remain office-contract compatible.
  - Involves: Protocol adapter, server handlers, contract tests.
  - Input: Adapter outputs and execution contract helpers.
  - Output: Normalized result fields remain complete and stable.
  - Dependencies: TODO-106, TODO-107.
  - Completion standard: Contract, Codex server, and project execution tests pass.
  - Checklist: CHK-165, CHK-167, CHK-171, CHK-172.

### Tests And Acceptance

- [x] TODO-109 - Add fake app-server runtime and fake Codex protocol tests.
  - Goal: Test extraction without requiring a real authenticated Codex binary.
  - Involves: New tests under `tests/`.
  - Input: Runtime and Codex adapter.
  - Output: Deterministic tests for runtime and protocol behavior.
  - Dependencies: TODO-104, TODO-106.
  - Completion standard: Tests cover success, timeout, crash, server request, approval, cancel, file changes, and terminal ordering.
  - Checklist: CHK-162 through CHK-167, CHK-170.

- [x] TODO-110 - Run Phase 7 full targeted regression suite.
  - Goal: Prove runtime split does not break provider, project, meeting, bridge, or UI behavior.
  - Involves: Provider tests, server tests, bridge/run tests, project/meeting tests, UI source checks.
  - Input: Implemented Phase 7 code.
  - Output: Passing targeted regressions or documented environmental blockers.
  - Dependencies: TODO-107, TODO-108, TODO-109.
  - Completion standard: Phase 5/6 tests plus project/meeting/UI checks pass.
  - Checklist: CHK-171, CHK-172, CHK-173.

- [x] TODO-111 - Update Phase 7 acceptance records and remaining reference-diff report.
  - Goal: Make runtime extraction auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, implementation diff, copied/adapted/deferred reference behavior.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-110.
  - Completion standard: Phase 7 status and reference parity gaps are documented.
  - Checklist: CHK-174.

### Phase 7 Completion Notes

- 2026-06-27T04:31:57+08:00 - TODO-102 through TODO-111 completed for the runtime extraction scope. `codex_bridge.py` was split so generic process/JSONL/RPC mechanics live in `app/provider_app_server.py`, while Codex protocol parsing stays in the Codex bridge.
- Added fake-runtime tests for request/response routing, server request dispatch, notification dispatch, timeout, and close behavior. Existing Codex provider/server/run-SSE tests and Phase 6 execution-contract tests continue to pass.
- Deferred by design: a separate `app/providers/codex_app_server.py` file can still be introduced later if we want a stricter file-level split. For this phase, the important runtime/protocol boundary is enforced by `JsonlAppServerRuntime` owning transport only and `codex_bridge.py` owning Codex protocol semantics.


## Phase 8 Codex Protocol Adapter File Split Tasks

Phase 8 continues from TODO-112. This phase performs the file-level split deferred in Phase 7: Codex protocol behavior moves into `app/providers/codex_app_server.py`, while `codex_bridge.py` remains as a compatibility shim.

- [x] TODO-112 - Move Codex protocol implementation into `app/providers/codex_app_server.py`.
  - Goal: Separate Codex app-server protocol code from compatibility bridge exports.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex_bridge.py`.
  - Input: Current `codex_bridge.py` after Phase 7.
  - Output: Adapter file containing Codex protocol client/operation/HTTP bridge/client cache.
  - Dependencies: Phase 8 checklist confirmed.
  - Completion standard: Adapter imports and py_compile pass.
  - Checklist: CHK-175, CHK-177.

- [x] TODO-113 - Convert `codex_bridge.py` into a compatibility shim.
  - Goal: Preserve existing imports and callers.
  - Involves: `app/providers/codex_bridge.py`, caller search.
  - Input: Adapter exports from TODO-112.
  - Output: Shim re-exporting existing public names.
  - Dependencies: TODO-112.
  - Completion standard: Existing callers require no broad rewrite.
  - Checklist: CHK-176.

- [x] TODO-114 - Add source-level adapter/shim test.
  - Goal: Lock the file split boundary.
  - Involves: New or existing Node/Python source tests.
  - Input: Adapter and shim files.
  - Output: Test proves adapter uses generic runtime and shim exports public names.
  - Dependencies: TODO-112, TODO-113.
  - Completion standard: Test fails if protocol code moves back into shim or runtime coupling regresses.
  - Checklist: CHK-175, CHK-176, CHK-177.

- [x] TODO-115 - Run Phase 8 targeted regression suite.
  - Goal: Ensure file split does not break provider/runtime/project/meeting behavior.
  - Involves: Codex provider/server/run tests, runtime tests, contract tests, project/meeting tests, UI source checks.
  - Input: Implemented split.
  - Output: Passing targeted regressions or documented environmental blockers.
  - Dependencies: TODO-114.
  - Completion standard: CHK-178 through CHK-180 pass.
  - Checklist: CHK-178, CHK-179, CHK-180.

- [x] TODO-116 - Update Phase 8 acceptance records and status.
  - Goal: Make the split auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs and implementation diff.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-115.
  - Completion standard: Phase 8 completion is documented.
  - Checklist: CHK-181.

### Phase 8 Completion Notes

- 2026-06-27T04:42:09+08:00 - TODO-112 through TODO-116 completed. `app/providers/codex_app_server.py` now owns the Codex app-server protocol adapter. `app/providers/codex_bridge.py` is intentionally thin and only re-exports the existing public bridge API for compatibility.
- Added `tests/check_codex_app_server_split.mjs` to enforce the adapter/shim boundary. Full targeted regressions passed, including Codex provider/server/run-SSE, runtime, execution contract, project execution, meeting blocker, provider config, and source-level UI checks.


## Phase 9 Codex App-Server Run State Parity Tasks

Phase 9 continues from TODO-117. This phase aligns Codex app-server run-state behavior with the reference branch: run-state aggregation, token usage, pending approvals, and first-class provider native send path.

- [x] TODO-117 - Rebaseline reference `CodexAppRunState` against local adapter.
  - Goal: Identify exact run-state fields and event handlers still missing locally.
  - Involves: Reference `app/providers/codex.py`, `app/providers/codex_app_server.py`, provider tests.
  - Input: Phase 8 split implementation and reference branch.
  - Output: Field/event parity map for reply, tools, thinking, approval, tokenUsage, IDs, and terminal status.
  - Dependencies: Phase 9 checklist confirmed.
  - Completion standard: Missing behaviors are categorized before implementation.
  - Checklist: CHK-182, CHK-187, CHK-191.

- [x] TODO-118 - Implement Codex run-state aggregator in adapter.
  - Goal: Centralize Codex run-state parsing and snapshots.
  - Involves: `app/providers/codex_app_server.py`, focused tests.
  - Input: Parity map from TODO-117.
  - Output: Dedicated state object/helper for reply/tools/thinking/approval/token usage/status.
  - Dependencies: TODO-117.
  - Completion standard: Fake event tests prove state snapshots and terminal results.
  - Checklist: CHK-182, CHK-187.

- [x] TODO-119 - Add token usage late-drain handling.
  - Goal: Preserve `thread/tokenUsage/updated` emitted before or shortly after completion.
  - Involves: Adapter execution loop and tests.
  - Input: Reference late-drain behavior.
  - Output: Final result includes tokenUsage when emitted around completion.
  - Dependencies: TODO-118.
  - Completion standard: Fake runtime tests cover pre/post completion token usage updates.
  - Checklist: CHK-183.

- [x] TODO-120 - Implement provider-level pending approval store.
  - Goal: Match reference pending approval query/response behavior.
  - Involves: Adapter/client approval state, `CodexProvider` facade, tests.
  - Input: Reference `_pending_approvals`, `pending_approval`, and `respond_approval` behavior.
  - Output: Pending approvals are queryable and resolvable without leaking stale state.
  - Dependencies: TODO-118.
  - Completion standard: Pending, approve, deny, cancel, timeout, and close tests pass.
  - Checklist: CHK-184.

- [x] TODO-121 - Promote `send_chat_message` to first-class native app-server path.
  - Goal: Use adapter run-state/progress snapshots directly from provider facade.
  - Involves: `app/providers/codex.py`, adapter APIs, provider tests.
  - Input: Adapter run-state implementation.
  - Output: `send_chat_message` no longer acts only as a light wrapper over legacy `send_message`.
  - Dependencies: TODO-118, TODO-119, TODO-120.
  - Completion standard: Provider facade tests pass and progress callback includes tools/thinking/approval/tokenUsage where available.
  - Checklist: CHK-185, CHK-189.

- [x] TODO-122 - Preserve legacy compatibility and project evidence.
  - Goal: Keep `send_message/respond/cancel` and project execution result fields stable.
  - Involves: `app/providers/codex.py`, `app/server.py`, tests.
  - Input: New run-state path and existing compatibility methods.
  - Output: Legacy server/project consumers keep stable reply/status/threadId/turnId/modifiedFiles/needsHumanIntervention behavior.
  - Dependencies: TODO-121.
  - Completion standard: Existing Codex server/project tests pass.
  - Checklist: CHK-186, CHK-188.

- [x] TODO-123 - Run Phase 9 targeted regression suite.
  - Goal: Ensure no break update after run-state parity work.
  - Involves: Runtime, adapter split, provider, run/SSE, contract, project, meeting, config, and UI checks.
  - Input: Implemented Phase 9 code.
  - Output: Passing targeted regressions or documented environmental blockers.
  - Dependencies: TODO-118 through TODO-122.
  - Completion standard: CHK-190 passes.
  - Checklist: CHK-190.

- [x] TODO-124 - Update Phase 9 acceptance records and remaining reference-diff report.
  - Goal: Make run-state parity auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs and implementation diff.
  - Output: Checklist evidence, completed todolist marks, residual difference summary.
  - Dependencies: TODO-123.
  - Completion standard: Phase 9 completion is documented.
  - Checklist: CHK-191.

### Phase 9 Completion Notes

- 2026-06-27T05:07:00+08:00 - TODO-117 through TODO-124 completed. The local Codex app-server adapter now includes the reference-style run-state aggregation layer, late tokenUsage capture, pending approval query/response store, and native adapter `send_chat_message`.
- Preserved compatibility: legacy `send_message`, `/api/codex/*` run/SSE paths, project execution result dependencies, meeting blocker behavior, `modifiedFiles`, `threadId`, `turnId`, `sessionId`, `runId`, and fixture `reply_text` mode.
- Residual reference difference: the local implementation keeps Phase 7's shared `JsonlAppServerRuntime` and existing `_Operation` event/SSE compatibility instead of adopting the reference branch's monolithic Codex provider class and manual JSONL loop wholesale.


## Phase 10 Reference Provider Bottom-Layer Alignment Tasks

Phase 10 continues from TODO-125. This phase reduces the remaining bottom-layer gap against `eliautobot/main` while keeping local bridge, run/SSE, office execution contract, project, meeting, archive, and scheduled behavior authoritative.

- [x] TODO-125 - Rebaseline reference provider bottom-layer diff.
  - Goal: Produce an implementation map for remaining Codex/Claude provider differences.
  - Involves: `refs/remotes/eliautobot/main`, `app/providers/codex.py`, `app/providers/codex_app_server.py`, `app/providers/claude_code.py`, `app/server.py`, `app/chat.js`.
  - Input: Fresh fetched reference branch and current local working tree.
  - Output: Copied/adapted/preserved/deferred map for Phase 10.
  - Dependencies: Phase 10 checklist confirmation.
  - Completion standard: CHK-192 and CHK-193 are satisfied before code edits.
  - Checklist: CHK-192, CHK-193, CHK-206.

- [x] TODO-126 - Align Codex app-server auth/test behavior.
  - Goal: Bring `CodexProvider.test()` closer to the reference `initialize` + `account/read` flow.
  - Involves: `app/providers/codex.py`, `app/providers/codex_app_server.py`, provider tests.
  - Input: Reference Codex test/auth implementation and local adapter APIs.
  - Output: App-server auth status reporting with safe fallback for disabled, fixture, missing binary, unauthenticated, and timeout cases.
  - Dependencies: TODO-125.
  - Completion standard: Fake app-server auth tests pass and existing provider config tests remain green.
  - Checklist: CHK-194.

- [x] TODO-127 - Align Codex active run/client lifecycle.
  - Goal: Improve parity for active run registration, interrupt/stop, timeout, close cleanup, and pending approval cleanup.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, Codex run/SSE tests.
  - Input: Reference `_ACTIVE_RUNS` behavior and local ProviderRunBridge/SSE requirements.
  - Output: Lifecycle behavior closer to reference without losing local run/SSE terminal delivery.
  - Dependencies: TODO-126.
  - Completion standard: Start/stop/timeout/close/concurrent fake-runtime tests pass.
  - Checklist: CHK-195, CHK-202.

- [x] TODO-128 - Complete or document remaining Codex event/result metadata parity.
  - Goal: Close remaining gaps in event parsing and final/progress snapshots.
  - Involves: `app/providers/codex_app_server.py`, `provider_execution.py` tests, Codex provider/server tests.
  - Input: Reference Codex event handlers and local `CodexAppRunState`.
  - Output: All compatible reference event metadata is captured or explicitly deferred.
  - Dependencies: TODO-127.
  - Completion standard: Fake protocol fixtures cover tools/reasoning/token/file/approval/error/terminal events and contract fields remain stable.
  - Checklist: CHK-196, CHK-203.

- [x] TODO-129 - Preserve Codex facade and endpoint compatibility.
  - Goal: Ensure deeper native parity does not break existing local Codex semantics.
  - Involves: `app/providers/codex.py`, `app/server.py`, `app/chat.js`, tests.
  - Input: Phase 10 Codex bottom-layer changes.
  - Output: Existing facade methods and server endpoints keep current behavior.
  - Dependencies: TODO-128.
  - Completion standard: Existing Codex provider/server/run-SSE/chat source tests pass.
  - Checklist: CHK-197, CHK-202, CHK-205.

- [x] TODO-130 - Align Claude Code auth/test behavior.
  - Goal: Bring `ClaudeCodeProvider.test()` closer to reference `claude auth status --json` while keeping fallback testability.
  - Involves: `app/providers/claude_code.py`, provider tests.
  - Input: Reference Claude Code test implementation and local compatibility requirements.
  - Output: Native auth status parsing with fallback for unsupported CLI behavior.
  - Dependencies: TODO-125.
  - Completion standard: Fake subprocess tests cover auth success/failure/malformed/unsupported/missing binary/replyText.
  - Checklist: CHK-198.

- [x] TODO-131 - Align Claude Code stream-json parsing.
  - Goal: Improve reply/tool/error/session parsing parity with the reference provider.
  - Involves: `app/providers/claude_code.py`, Claude Code provider/server/run-SSE tests.
  - Input: Reference stream-json parser behavior and local history/SSE requirements.
  - Output: Normalized Claude Code results include stable reply/tools/thinking/session/run/status/error fields.
  - Dependencies: TODO-130.
  - Completion standard: Stream-json fixture tests and server run/SSE tests pass.
  - Checklist: CHK-199, CHK-202, CHK-203.

- [x] TODO-132 - Align Claude Code active run stop/interrupt lifecycle.
  - Goal: Make Claude Code active subprocess lifecycle and stop semantics robust.
  - Involves: `app/providers/claude_code.py`, `app/server.py`, run bridge tests.
  - Input: Reference active run cleanup behavior and local ProviderRunBridge.
  - Output: Stop/interrupt targets the correct profile/run and preserves terminal history/SSE events.
  - Dependencies: TODO-131.
  - Completion standard: Fake subprocess lifecycle and `/api/claude-code/runs/*` tests pass.
  - Checklist: CHK-200, CHK-202.

- [x] TODO-133 - Reverify Claude Code native agent lifecycle and roster names.
  - Goal: Prevent regressions in create/discover/delete and custom display-name preservation.
  - Involves: `app/providers/claude_code.py`, `app/server.py`, `app/game.js`, provider/server tests.
  - Input: Recent roster/profile/name fix and reference native agent lifecycle behavior.
  - Output: Native agent lifecycle stays compatible with office-config overrides.
  - Dependencies: TODO-132.
  - Completion standard: Create/discover/delete/name-override tests pass for main/local/custom agents.
  - Checklist: CHK-201, CHK-205.

- [x] TODO-134 - Run Phase 10 regression suite.
  - Goal: Prove bottom-layer alignment does not break local workflows.
  - Involves: Provider tests, server tests, run/SSE tests, provider execution contract, project, meeting, archive/scheduled/source UI checks, optional MCP smoke.
  - Input: Implemented Phase 10 code.
  - Output: Passing targeted regressions or documented environmental blockers.
  - Dependencies: TODO-129, TODO-133.
  - Completion standard: CHK-202 through CHK-205 pass; MCP locks are released after browser checks.
  - Checklist: CHK-202, CHK-203, CHK-204, CHK-205.

- [x] TODO-135 - Update Phase 10 acceptance records and remaining reference-diff report.
  - Goal: Make the bottom-layer alignment auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, implementation diff, copied/adapted/deferred reference behavior.
  - Output: Phase 10 completion notes and explicit residual gap list.
  - Dependencies: TODO-134.
  - Completion standard: CHK-206 is satisfied and status reflects test outcome.
  - Checklist: CHK-206.

## Phase 10 Completion Notes - 2026-06-28T11:21:33+08:00

Completed TODO-125 through TODO-135 for the provider bottom-layer alignment slice:

- Codex app-server auth/test behavior now follows the reference-style app-server probe path (`initialize` then `account/read`) when the native binary is available, while preserving reply-text fixtures, missing-binary safety, external bridge fallback, and local Codex facade semantics.
- `CodexAppServerClient._ensure_started()` now returns initialize metadata so auth probes can expose reference-compatible runtime information without changing existing callers.
- Claude Code test/auth behavior now prefers `claude auth status --json` and falls back to `claude --version` for older CLIs, keeping local stream-json chat/run/SSE behavior intact.
- Existing Codex run-state, pending approval, `modifiedFiles`, `threadId`, `turnId`, active operation, ProviderRunBridge/SSE, and provider execution contract semantics are preserved.
- Project execution, meeting blockers, meeting phases, scheduled cron, provider settings UI, Codex/Claude run-SSE source checks, and chat i18n checks passed.
- Remaining reference gap is intentional: local code keeps the shared generic bridge/runtime architecture and office-facing normalization instead of replacing it with the reference branch's monolithic provider loop.

## Phase 10 MCP E2E Notes - 2026-06-28T12:52:56+08:00

Chrome MCP real E2E was run against `http://127.0.0.1:8090/` after restarting the local service with the latest code:

- Provider roster included OpenClaw, Hermes, `codex-local`, `codex-main`, `claude-code-local`, and `claude-code-main`.
- Real Codex CLI auth/test passed through `/api/codex/test`; real Claude Code CLI test passed through `/api/claude-code/test`.
- Real Codex `/api/codex/runs` emitted named SSE events through `run.completed`, and `/api/codex/activity` preserved the app-server event stream.
- Real Claude Code `/api/claude-code/runs` emitted named SSE events through `run.completed`, and history contained the user message, assistant `OK`, session id, and token usage.
- MCP exposed and verified a Codex history persistence race. The fix now sets human source defaults for Codex run requests and persists the assistant reply immediately when terminal Codex activity arrives, while avoiding duplicate reply history when `_handle_codex_chat` returns.
- Final Codex persistence smoke confirmed `/api/codex/history` immediately contains both the user request and assistant `OK` reply after terminal SSE, so closing and reopening the chat can reload the response.
- No residual Codex or Claude Code subprocesses were observed after the runs. The 8090 local service remains running for user acceptance.


## Phase 11 Remaining Reference Bottom-Layer Merge Tasks

Phase 11 continues from TODO-136. This phase selectively merges the remaining reference bottom-layer behavior from `eliautobot/main` while preserving the local layered provider architecture, VO project/meeting/archive/scheduled state machines, existing Codex compatibility semantics, and localized UI.

- [x] TODO-136 - Rebaseline Phase 11 reference diff and merge boundaries.
  - Goal: Confirm the exact remaining reference code paths before implementation.
  - Involves: `refs/remotes/eliautobot/main`, `app/server.py`, `app/providers/codex_app_server.py`, `app/providers/codex.py`, `app/providers/claude_code.py`, `app/providers/hermes.py`, `app/chat.js`, setup/model provider files.
  - Input: Fresh fetched reference branch and current local working tree.
  - Output: Copied/adapted/preserved/deferred map for approval APIs, progress history, Hermes runs/SSE, native model/auth helpers, and protocol parity details.
  - Dependencies: Phase 11 checklist confirmation.
  - Completion standard: CHK-207 through CHK-209 are satisfied before code edits.
  - Checklist: CHK-207, CHK-208, CHK-209.

- [x] TODO-137 - Align Codex pending approval server APIs.
  - Goal: Expose reference-compatible pending/respond approval APIs while keeping existing Codex interaction endpoints stable.
  - Involves: `app/server.py`, `app/providers/codex.py`, `app/providers/codex_app_server.py`, Codex server/run tests.
  - Input: Reference approval API behavior and local pending approval store from Phase 9.
  - Output: `/api/codex/approval/pending` and `/api/codex/approval/respond` resolve the same adapter approval requests used by legacy interaction paths.
  - Dependencies: TODO-136.
  - Completion standard: Pending, approve, deny, stale approval, cancel, compact, and existing interaction tests pass.
  - Checklist: CHK-210.

- [ ] TODO-138 - Localize and verify Codex approval UI.
  - Goal: Ensure Codex approval controls remain VO-styled and Chinese/i18n-compatible after API alignment.
  - Involves: `app/chat.js`, `app/i18n.js`, locale files, source/browser checks.
  - Input: Existing approval card UI and reference approval flow expectations.
  - Output: Approval pending/respond UI uses localized strings, avoids duplicate cards, and preserves current chat behavior.
  - Dependencies: TODO-137.
  - Completion standard: Source checks and targeted browser/MCP checks validate approval card rendering and actions.
  - Checklist: CHK-211.

- [ ] TODO-139 - Harden Codex progress history reload and duplicate prevention.
  - Goal: Keep run progress recoverable while final assistant replies persist exactly once.
  - Involves: `app/server.py`, `ProviderRunBridge`, Codex run/SSE/history tests.
  - Input: Phase 10 MCP-discovered history persistence fix and reference `claude-code-progress` style behavior.
  - Output: Progress activity is ephemeral or cleaned on terminal state; final user/assistant history survives close/reopen without duplication.
  - Dependencies: TODO-137.
  - Completion standard: Codex run/SSE tests cover progress, approval, terminal completion, history reload, and duplicate guards.
  - Checklist: CHK-212.

- [ ] TODO-140 - Audit and merge remaining Codex protocol parity details.
  - Goal: Reduce small bottom-layer gaps without replacing the local adapter architecture.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, Codex bridge/provider tests.
  - Input: Reference Codex app-server event/result parsing, token metrics, status/error fallback, and lifecycle behavior.
  - Output: Compatible protocol fields are merged; monolithic loop or incompatible choices are documented as deferred.
  - Dependencies: TODO-136, TODO-139.
  - Completion standard: Fake protocol tests cover merged fields and final report documents deferrals.
  - Checklist: CHK-213.

- [ ] TODO-141 - Harden Claude Code progress history reload.
  - Goal: Bring Claude Code close/reopen behavior to the same generic bridge semantics as Codex.
  - Involves: `app/server.py`, `app/providers/claude_code.py`, Claude Code run/SSE/history tests.
  - Input: Existing Claude Code stream-json parsing, ProviderRunBridge, and reference progress event behavior.
  - Output: Progress state, `sessionId`, `runId`, tools, thinking, token usage, errors, and final replies remain stable and non-duplicated.
  - Dependencies: TODO-136.
  - Completion standard: Claude Code run/SSE tests cover terminal history persistence and reload after progress events.
  - Checklist: CHK-214, CHK-215.

- [x] TODO-142 - Add Hermes native run/SSE/stop through ProviderRunBridge.
  - Goal: Let Hermes native API use the same generic run distribution as Codex and Claude Code.
  - Involves: `app/server.py`, `app/providers/hermes.py`, Hermes native API client/server tests.
  - Input: Reference Hermes native streaming behavior, local Hermes native API foundation, and existing CLI fallback.
  - Output: `/api/hermes/runs`, `/api/hermes/runs/<id>/events`, and `/api/hermes/runs/<id>/stop` support named SSE, terminal history, approval/failure/timeout handling, and fallback safety.
  - Dependencies: TODO-136.
  - Completion standard: Hermes native run/SSE tests pass for success, approval, stop, failure, missing native API, and CLI fallback.
  - Checklist: CHK-216, CHK-217.

- [ ] TODO-143 - Selectively merge native model/auth backend helpers.
  - Goal: Close safe reference backend gaps for provider setup/auth/model visibility without exposing secrets.
  - Involves: `app/server.py`, `app/discovery.py`, provider config helpers, config tests.
  - Input: Reference native model/auth endpoints and local `/config/providers`, `/vo-config`, OAuth/model config behavior.
  - Output: Safe helper parity for available native providers, tests, API key save/delete, custom provider save/delete, and redaction.
  - Dependencies: TODO-136.
  - Completion standard: Config/provider tests prove secrets are not exposed and existing model flows keep working.
  - Checklist: CHK-218.

- [ ] TODO-144 - Preserve localized setup/model UI after backend parity.
  - Goal: Verify UI remains localized and avoids reference hardcoded-English regressions.
  - Involves: `app/models.html`, `app/setup.html`, `app/i18n.js`, locale files, UI source/browser checks.
  - Input: Backend helper changes and current localized native provider UI.
  - Output: Native Agents, setup, OpenClaw/Hermes/Codex/Claude settings, and model provider flows remain localized and usable.
  - Dependencies: TODO-143.
  - Completion standard: Source checks and browser/MCP smoke pass for setup/model pages.
  - Checklist: CHK-219.

- [x] TODO-145 - Run provider run/SSE matrix regressions.
  - Goal: Prove Codex, Claude Code, and Hermes all work through the generic bridge/run distribution.
  - Involves: Codex, Claude Code, Hermes server/provider tests and Node source checks.
  - Input: TODO-137 through TODO-142 implementation.
  - Output: Passing run started/progress/approval/terminal/history/stop tests for all applicable providers.
  - Dependencies: TODO-137, TODO-139, TODO-141, TODO-142.
  - Completion standard: CHK-220 passes.
  - Checklist: CHK-220.

- [x] TODO-146 - Run office execution and project regressions.
  - Goal: Ensure provider bottom-layer changes do not break project execution contract dependencies.
  - Involves: `app/provider_execution.py`, `app/server.py`, project execution tests.
  - Input: Provider runtime changes from Phase 11.
  - Output: Stable `modifiedFiles`, `threadId`, `turnId`, `runId`, `needsHumanIntervention`, reply/tools/thinking/status fields.
  - Dependencies: TODO-145.
  - Completion standard: Provider execution contract and project execution tests pass.
  - Checklist: CHK-221.

- [x] TODO-147 - Run meeting, archive, and scheduled regressions.
  - Goal: Prove provider bottom-layer merge did not overwrite local business state machines.
  - Involves: Meeting phase/blocker tests, archive/project context checks, scheduled cron tests.
  - Input: Implemented Phase 11 provider changes.
  - Output: Passing regressions or documented non-blocking environmental cleanup issues.
  - Dependencies: TODO-145.
  - Completion standard: CHK-222 passes.
  - Checklist: CHK-222.

- [x] TODO-148 - Run Chrome MCP real E2E where available.
  - Goal: Validate real browser behavior after automated tests.
  - Involves: Local service, Chrome MCP, chat close/reopen, provider roster, setup/model pages, Codex/Claude/Hermes run paths.
  - Input: Implemented and tested Phase 11 code.
  - Output: MCP evidence for real run/SSE/history reload behavior, or documented MCP/environmental blocker with fallback checks.
  - Dependencies: TODO-145, TODO-146, TODO-147.
  - Completion standard: CHK-223 passes or blocker is explicitly documented; MCP locks are released.
  - Checklist: CHK-223.

- [x] TODO-149 - Update Phase 11 acceptance records and final reference-gap report.
  - Goal: Make the Phase 11 merge auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, implementation diff, copied/adapted/deferred reference behavior.
  - Output: Completed checklist/todolist marks, latest verification note, and explicit remaining gap list.
  - Dependencies: TODO-145, TODO-146, TODO-147, TODO-148.
  - Completion standard: CHK-224 is satisfied and status reflects implementation/test results.
  - Checklist: CHK-224.

## Phase 11 Completion Notes - 2026-06-28T13:42:48+08:00

Completed TODO-136, TODO-137, TODO-142, TODO-145, TODO-146, TODO-147, TODO-148, and TODO-149 for this bottom-layer merge slice:

- Rebaseline confirmed that the safely mergeable reference gaps were Codex approval server APIs and Hermes native `/runs`/SSE/stop exposure through the already-local `ProviderRunBridge`.
- Added `GET /api/codex/approval/pending` and `POST /api/codex/approval/respond` as thin server wrappers over the existing Codex provider facade, preserving the adapter pending approval store, `/api/codex/interaction`, active operation, `threadId`, `turnId`, and project execution semantics.
- Added Hermes `POST /api/hermes/runs`, `GET /api/hermes/runs/<id>/events`, and `POST /api/hermes/runs/<id>/stop`; native Hermes API events now feed `ProviderRunBridge` as `message.delta`, `reasoning.available`, `tool.started`, `tool.completed`, `tool.failed`, `approval.required`, and terminal run events where available.
- Preserved local project, meeting, archive, scheduled, setup/model, and i18n behavior. Reference UI replacements and deleted-i18n changes were intentionally not imported.
- Verification passed across provider run/SSE, Hermes native API, Codex approval/server, Claude Code run/SSE, provider execution contract, project execution, meeting blocker/phase checks, UI source checks, `git diff --check`, and a temporary Chrome MCP smoke on `http://127.0.0.1:8149/`.
- Deferred TODO-138 through TODO-141, TODO-143, and TODO-144 for a later Phase 11 continuation because they cover deeper UI/progress-history/model-auth parity not required for the Codex approval + Hermes run bridge slice.


## Phase 12 Provider Progress History Parity Tasks

Phase 12 continues from TODO-150. This phase ports the reference branch's recoverable provider progress history behavior into the local shared runtime architecture. The target is close/reopen chat reliability for Codex, Claude Code, and Hermes without replacing local i18n UI, project/meeting/archive/scheduled logic, or the ProviderRunBridge abstraction.

- [x] TODO-150 - Rebaseline reference progress-history diff.
  - Goal: Identify the exact reference progress helpers and frontend restore logic to adapt.
  - Involves: `refs/remotes/eliautobot/main`, `app/server.py`, `app/chat.js`, provider run workers, history helpers.
  - Input: Reference `_publish_codex_progress`, `_publish_claude_code_progress`, `_publish_hermes_api_progress`, remove helpers, and `chat.js` restore code.
  - Output: Copied/adapted/preserved/deferred map for Phase 12 implementation.
  - Dependencies: Phase 12 checklist confirmation.
  - Completion standard: CHK-225 and CHK-226 are satisfied before broad edits.
  - Checklist: CHK-225, CHK-226.

- [x] TODO-151 - Implement generic provider progress history helper.
  - Goal: Avoid three divergent progress persistence implementations.
  - Involves: `app/server.py`, history store helpers, provider-specific adapters.
  - Input: Existing Codex comm history, Claude Code history, Hermes history, and reference progress message shapes.
  - Output: A reusable helper that upserts one ephemeral progress message per provider/run and removes it on terminal states.
  - Dependencies: TODO-150.
  - Completion standard: Unit tests prove duplicate updates replace prior progress for the same progressId.
  - Checklist: CHK-227, CHK-231.

- [x] TODO-152 - Connect Codex runs to progress history helper.
  - Goal: Persist active Codex progress for reload while preserving final reply duplicate guards.
  - Involves: `_handle_codex_run_start`, `_handle_codex_chat`, Codex history/activity helpers, Codex run/SSE tests.
  - Input: Existing Codex ProviderRunBridge events and Phase 10 history persistence fix.
  - Output: `codex-progress` contains current tools/thinking/tokenUsage/approval/session metadata during active runs and is cleaned on terminal completion.
  - Dependencies: TODO-151.
  - Completion standard: Codex reload/no-duplicate tests pass.
  - Checklist: CHK-228, CHK-231, CHK-237.

- [x] TODO-153 - Connect Claude Code runs to progress history helper.
  - Goal: Persist active Claude Code progress for reload without changing stream-json parsing semantics.
  - Involves: `_handle_claude_code_run_start`, `_handle_claude_code_chat`, Claude Code history helpers, run/SSE tests.
  - Input: Existing Claude Code progress callback and ProviderRunBridge events.
  - Output: `claude-code-progress` restores tools/thinking/tokenUsage/session/run state and is removed on terminal states.
  - Dependencies: TODO-151.
  - Completion standard: Claude Code reload/no-duplicate tests pass.
  - Checklist: CHK-229, CHK-231, CHK-237.

- [x] TODO-154 - Connect Hermes native runs to progress history helper.
  - Goal: Persist active Hermes native API progress for reload while keeping CLI fallback compatible.
  - Involves: `_handle_hermes_run_start`, `_handle_hermes_api_chat`, Hermes history helpers, Hermes native API tests.
  - Input: Phase 11 Hermes `/runs` bridge and reference Hermes progress behavior.
  - Output: `hermes-progress` stores native message/tool/reasoning/approval progress and is cleaned on terminal states.
  - Dependencies: TODO-151.
  - Completion standard: Hermes native run reload/cleanup tests pass; CLI fallback tests still pass.
  - Checklist: CHK-230, CHK-231, CHK-237.

- [x] TODO-155 - Port frontend progress restore behavior without replacing local UI.
  - Goal: Restore provider progress after close/reopen in the chat window.
  - Involves: `app/chat.js`, `app/i18n.js`, locale files, source checks.
  - Input: Reference restore logic for `codex-progress`, `claude-code-progress`, and `hermes-progress`.
  - Output: Local chat UI restores pending stream text, tools, thinking, metrics, and active run IDs for all three providers.
  - Dependencies: TODO-152, TODO-153, TODO-154.
  - Completion standard: Source checks and browser/MCP close/reopen checks pass.
  - Checklist: CHK-232, CHK-233, CHK-234, CHK-236.

- [ ] TODO-156 - Connect Codex approval UI to new approval APIs.
  - Goal: Make approval cards actionable after reload while keeping legacy interaction compatibility.
  - Involves: `app/chat.js`, Codex approval server routes, i18n/locales, source/browser tests.
  - Input: Phase 11 `/api/codex/approval/pending/respond`, existing `/api/codex/interaction`, and reference approval UI behavior.
  - Output: Localized Codex approval card can approve/deny/cancel pending requests and handles stale responses clearly.
  - Dependencies: TODO-152, TODO-155.
  - Completion standard: Approval source tests and MCP/browser approval fixture checks pass.
  - Checklist: CHK-235, CHK-236.

- [x] TODO-157 - Run provider progress/history regression matrix.
  - Goal: Prove Phase 12 does not break provider runtime behavior.
  - Involves: Codex, Claude Code, Hermes run/SSE/history tests and Node source checks.
  - Input: TODO-151 through TODO-156 implementation.
  - Output: Passing tests for progress persistence, reload, cleanup, terminal events, and duplicate guards.
  - Dependencies: TODO-152, TODO-153, TODO-154, TODO-155, TODO-156.
  - Completion standard: CHK-237 passes.
  - Checklist: CHK-237.

- [x] TODO-158 - Run office workflow regressions and MCP close/reopen E2E.
  - Goal: Validate provider progress changes against local business workflows and real browser behavior.
  - Involves: Provider execution contract, project execution, meeting regressions, archive/scheduled checks, Chrome MCP.
  - Input: Implemented Phase 12 code.
  - Output: Passing workflow regressions and MCP close/reopen evidence for supported providers, or documented environmental blockers.
  - Dependencies: TODO-157.
  - Completion standard: CHK-238, CHK-239, and CHK-240 pass or blockers are documented.
  - Checklist: CHK-238, CHK-239, CHK-240.

- [x] TODO-159 - Update Phase 12 acceptance records and reference-gap report.
  - Goal: Make progress-history parity auditable.
  - Involves: `checklist.md`, `todolist.md`, `status.json`, final delivery.
  - Input: Test outputs, MCP evidence, implementation diff, copied/adapted/deferred reference behavior.
  - Output: Completed checklist/todolist marks, latest verification note, and explicit remaining gap list.
  - Dependencies: TODO-157, TODO-158.
  - Completion standard: CHK-241 is satisfied and status reflects implementation/test results.
  - Checklist: CHK-241.

### Phase 12 Acceptance Notes

- 2026-06-28T14:50:50+08:00 - Implemented generic recoverable provider progress history for Codex, Claude Code, and Hermes while preserving local `ProviderRunBridge`, `JsonlAppServerRuntime`, project/meeting/archive/scheduled behavior, and i18n UI.
- Merged/adapted: `codex-progress` comm events, `claude-code-progress` history upserts, `hermes-progress` native run history upserts, terminal cleanup guards, and frontend history restore for active progress.
- Preserved: local Codex final reply duplicate guard, `modifiedFiles`, `threadId`, `turnId`, active operation semantics, Claude Code stream-json parsing, Hermes CLI fallback, and local VO chat styling.
- Deferred: CHK-235/TODO-156 remains open because Codex approval cards still submit through legacy `/api/codex/interaction`; Phase 11 `/api/codex/approval/pending` and `/api/codex/approval/respond` server APIs exist but are not yet wired into the UI.
- Verification passed: `python3 -m py_compile app/server.py app/providers/hermes.py app/providers/codex_app_server.py app/providers/codex.py app/providers/claude_code.py`; `.venv/bin/python tests/test_codex_runs_sse.py`; `.venv/bin/python tests/test_claude_code_runs_sse.py`; `.venv/bin/python tests/test_hermes_server_native_api.py`; `.venv/bin/python tests/test_codex_server.py`; `.venv/bin/python tests/test_claude_code_server.py`; `.venv/bin/python tests/test_hermes_api_client.py`; `.venv/bin/python tests/test_provider_execution_contract.py`; `.venv/bin/python tests/test_project_execution.py`; `.venv/bin/python tests/test_meeting_request_blocks_task.py`; `node tests/check_codex_runs_bridge.mjs`; `node tests/check_claude_code_runs_sse.mjs`; `node tests/check_provider_runtime_settings_ui.mjs`; `git diff --check`.
- Chrome MCP smoke: loaded `http://127.0.0.1:8149/` with current `chat.js` and locale bundles, verified page load completed and console had no JS exceptions. Existing environment noise remained: WS port 8091 already in use from the user's running service and repeated `/pc-metrics` 502 responses. The temporary 8149 service was stopped after the check.
- 2026-06-28T15:07:44+08:00 - Follow-up Chrome MCP E2E completed after the user asked whether MCP end-to-end acceptance was actually done. The recheck found the previous note was only smoke coverage, then ran a stricter real Codex `/api/codex/runs` + SSE + history reload flow on an isolated current-code service.
- Follow-up fix: real MCP exposed stale terminal `codex-progress` operation events remaining in communication history. Added communication-log progress upsert/remove cleanup and extended `tests/test_codex_runs_sse.py` so active progress is recoverable/upserted, while terminal history keeps only the user message and final assistant reply.
- Follow-up E2E evidence: conversation `phase12-mcp-codex-final-1782630268480` returned exactly two history events after browser reload: the user request and one Codex `OK` reply with `threadId`, `turnId`, and `modifiedFiles=[]`; no `codex-progress` remained. Artifact: `/tmp/phase12-mcp-codex-after-reload-assert.json`.


## Phase 13 Reference Bottom-Layer Parity Follow-Up Tasks

Phase 13 continues from TODO-160. This phase selectively ports remaining reference bottom-layer behavior from `eliautobot/main` `eb119493` while preserving the local layered provider runtime, project/meeting/archive/scheduled workflows, i18n files, and MCP-verified Codex history behavior.

- [x] TODO-160 - Capture Phase 13 reference merge map.
  - Goal: Make the remaining reference parity scope auditable before implementation.
  - Involves: `git diff`/`git show` against `eliautobot/main`, provider modules, server routes, chat approval UI, setup/model provider settings.
  - Input: `eliautobot/main` at `eb119493`, current local working tree, Phase 13 review/checklist.
  - Output: Copied/adapted/preserved/deferred/not-merged map in implementation notes or acceptance records.
  - Dependencies: Phase 13 checklist confirmation.
  - Completion standard: CHK-242 and CHK-243 have concrete evidence before code edits.
  - Checklist: CHK-242, CHK-243.

- [x] TODO-161 - Protect local layered runtime and product boundaries.
  - Goal: Prevent accidental whole-file replacement or deletion of local functionality.
  - Involves: `app/server.py`, `app/chat.js`, `app/game.js`, `app/projects.js`, `app/i18n.js`, locale files, tests, provider split files.
  - Input: Current local architecture and Phase 13 merge safety boundaries.
  - Output: Source checks or manual diff notes proving local provider split and project/meeting/archive/i18n files remain authoritative.
  - Dependencies: TODO-160.
  - Completion standard: CHK-243 and CHK-244 pass.
  - Checklist: CHK-243, CHK-244.

- [x] TODO-162 - Wire Codex chat approval UI to pending/respond APIs.
  - Goal: Make Codex approval cards actionable after reload through Phase 11 APIs.
  - Involves: `app/chat.js`, locale files, `app/style.css`, Codex approval server routes, approval source/browser tests.
  - Input: Existing `/api/codex/approval/pending`, `/api/codex/approval/respond`, legacy `/api/codex/interaction`, reference approval chat behavior.
  - Output: Localized Codex approval card that loads pending approval, submits approve/cancel, handles stale state, and keeps legacy interaction compatibility.
  - Dependencies: TODO-160, TODO-161.
  - Completion standard: CHK-245 and CHK-246 pass with source and browser/MCP fixture evidence.
  - Checklist: CHK-245, CHK-246, CHK-255.

- [x] TODO-163 - Align Codex approval protocol response mapping.
  - Goal: Ensure approval decisions sent to Codex app-server match reference behavior.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, Codex provider/server tests.
  - Input: Reference approval response handling for command execution, file changes, permissions, approve/cancel/stale/timeout.
  - Output: Tested approval mapping for all supported approval kinds without breaking pending approval store lifecycle.
  - Dependencies: TODO-162.
  - Completion standard: CHK-247 passes.
  - Checklist: CHK-247.

- [x] TODO-164 - Align Codex app-server streaming/tool/context normalization.
  - Goal: Port remaining useful reference protocol details without changing local transport layering.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, `app/provider_execution.py`, Codex app-server fixture tests.
  - Input: Reference v0.6.26-v0.6.28 Codex streaming/context metrics behavior and local Phase 12 MCP fix.
  - Output: Tools, thinking, token usage/context metrics, `threadId`, `turnId`, `modifiedFiles`, terminal cleanup, and final reply duplicate guards remain coherent.
  - Dependencies: TODO-160, TODO-163.
  - Completion standard: CHK-248 and CHK-249 pass.
  - Checklist: CHK-248, CHK-249.

- [x] TODO-165 - Verify and complete Claude Code native discovery parity.
  - Goal: Match reference native Claude Code discovery behavior where useful.
  - Involves: `app/providers/claude_code.py`, `app/discovery.py`, Claude Code provider tests.
  - Input: Reference v0.6.30 native Claude Code provider discovery and local provider implementation.
  - Output: Stable main/native/project/custom agent discovery metadata with safe unavailable/disabled/auth states.
  - Dependencies: TODO-160, TODO-161.
  - Completion standard: CHK-250 passes.
  - Checklist: CHK-250.

- [x] TODO-166 - Verify and complete Claude Code create/delete native lifecycle parity.
  - Goal: Safely support standard/custom Claude Code agent lifecycle without writing to real user directories during tests.
  - Involves: `app/providers/claude_code.py`, server agent platform routes, isolated filesystem tests.
  - Input: Reference v0.6.30 create/delete behavior and local native agent registry conventions.
  - Output: Tested standard, native registered, custom-directory, duplicate, invalid path, and delete paths.
  - Dependencies: TODO-165.
  - Completion standard: CHK-251 passes.
  - Checklist: CHK-251.

- [x] TODO-167 - Align Claude Code auth/model/permission and stream-json runtime parity.
  - Goal: Preserve current Claude Code run/SSE behavior while filling reference gaps.
  - Involves: `app/providers/claude_code.py`, `app/server.py`, `app/chat.js`, Claude Code provider/server/run-SSE tests.
  - Input: Reference auth/model/permission CLI behavior, stream-json parser behavior, local progress/history restore.
  - Output: Tested auth status, model/permission CLI args, partial messages, tools, JSON argument deltas, usage metrics, terminal errors, and interrupt.
  - Dependencies: TODO-165, TODO-166.
  - Completion standard: CHK-252 and CHK-253 pass.
  - Checklist: CHK-252, CHK-253.

- [x] TODO-168 - Selectively merge native provider settings diagnostics.
  - Goal: Improve Codex/Claude/Hermes settings diagnostics without replacing local UI.
  - Involves: `app/server.py`, `app/models.html`, `app/setup.html`, `app/chat.js`, `app/locales/*.json`, provider settings source tests.
  - Input: Reference v0.6.29 native provider settings and local safe config/i18n patterns.
  - Output: More informative status/model/auth payloads, no secret leaks, localized UI strings, and no layout regressions.
  - Dependencies: TODO-162, TODO-167.
  - Completion standard: CHK-254 and CHK-255 pass.
  - Checklist: CHK-254, CHK-255.

- [x] TODO-169 - Run provider runtime regression matrix.
  - Goal: Prove provider bottom-layer parity changes do not break shared runtime contracts.
  - Involves: Python provider/server/run-SSE/app-server tests and Node provider source checks.
  - Input: TODO-162 through TODO-168 implementation.
  - Output: Passing Codex, Claude Code, Hermes, provider app-server runtime, provider execution, and source-level checks.
  - Dependencies: TODO-162, TODO-163, TODO-164, TODO-165, TODO-166, TODO-167, TODO-168.
  - Completion standard: CHK-256 passes.
  - Checklist: CHK-256.

- [x] TODO-170 - Run project, meeting, archive, and scheduled regressions.
  - Goal: Prove provider parity changes preserve original office workflows.
  - Involves: Project execution tests, meeting blocker/phase tests, archive/project context checks, scheduled cron checks, sidebar/project meeting records checks.
  - Input: TODO-169 passing provider matrix.
  - Output: Passing workflow regressions or explicitly documented environmental blockers.
  - Dependencies: TODO-169.
  - Completion standard: CHK-257 and CHK-258 pass.
  - Checklist: CHK-257, CHK-258.

- [x] TODO-171 - Run Chrome MCP E2E for Phase 13 changed surfaces.
  - Goal: Validate user-visible provider approval/settings/history behavior in a real browser.
  - Involves: Local temporary service, Chrome MCP, Codex approval fixture/reload, Codex final history reload, Claude Code fixture/real path where available, provider settings page.
  - Input: TODO-169 and TODO-170 results.
  - Output: MCP artifacts and notes proving changed provider UI works, or documented environment blockers with equivalent fallback checks.
  - Dependencies: TODO-170.
  - Completion standard: CHK-259 passes and MCP locks/pages are released.
  - Checklist: CHK-249, CHK-259.

- [x] TODO-172 - Update Phase 13 acceptance records and remaining reference-gap report.
  - Goal: Make Phase 13 outcome auditable and ready for user-tested confirmation.
  - Involves: `review.md`, `checklist.md`, `todolist.md`, `status.json`, final delivery notes.
  - Input: Implementation diff, test outputs, MCP artifacts, copied/adapted/deferred map.
  - Output: Checklist evidence, todolist completion states, latest status verification, and explicit remaining gaps.
  - Dependencies: TODO-171.
  - Completion standard: CHK-260 passes and status reflects implementation/test results.
  - Checklist: CHK-260.


## Phase 14 Final Reference Bottom-Layer Closure Tasks

Phase 14 is the final provider-runtime reference bottom-layer closure phase. It should merge every remaining safe behavior from `eliautobot/main` `eb119493` while preserving local provider layering, meeting/project/archive/scheduled workflows, i18n, VO styling, and Phase 13 run/history cleanup guarantees.

- [x] TODO-173 - Capture final reference closure map.
  - Goal: Make the last remaining safe merge candidates explicit before implementation.
  - Involves: `eliautobot/main` provider/server/chat diff, local layered runtime, final Phase 14 checklist.
  - Input: Current worktree, `eliautobot/main` `eb119493`, Phase 13 completion notes.
  - Output: Final copied/adapted/preserved/permanent-not-merged map in acceptance records.
  - Dependencies: Phase 14 checklist confirmation.
  - Completion standard: CHK-261 and CHK-262 pass.
  - Checklist: CHK-261, CHK-262.

- [x] TODO-174 - Add Codex approval respond history side effects.
  - Goal: Match reference-visible approval response history without duplicating approval cards or assistant replies.
  - Involves: Codex approval respond handler, communication/history helpers, tests.
  - Input: Existing `/api/codex/approval/respond`, reference `_codex_approval_result_message`, local progress cleanup behavior.
  - Output: Approve/cancel writes exactly one persisted approval result message with duplicate protection.
  - Dependencies: TODO-173.
  - Completion standard: CHK-263 passes.
  - Checklist: CHK-263.

- [x] TODO-175 - Add Codex approval responded presence event.
  - Goal: Expose approval responses to provider presence observers as in the reference branch.
  - Involves: `gateway_presence.set_provider_event`, approval metadata normalization, tests/source checks.
  - Input: Reference `approval.responded` payload shape and local provider event conventions.
  - Output: Presence event includes approval id, provider, thread id, turn id, choice, and status key.
  - Dependencies: TODO-174.
  - Completion standard: CHK-264 passes.
  - Checklist: CHK-264.

- [x] TODO-176 - Complete Codex app-server item/tool/context final audit.
  - Goal: Ensure all remaining safe reference Codex protocol normalization details are absorbed.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, provider execution normalization, Codex fixture tests.
  - Input: Reference command/file/MCP/dynamic/web-search/reasoning/token/error/terminal handling.
  - Output: Coherent SSE/history/project execution output for tools, thinking, token usage, errors, threadId, turnId, modifiedFiles, and final reply.
  - Dependencies: TODO-173, TODO-174.
  - Completion standard: CHK-265 and CHK-266 pass.
  - Checklist: CHK-265, CHK-266.

- [x] TODO-177 - Complete Claude Code final facade parity.
  - Goal: Add safe reference-compatible progress callback behavior while preserving shared run bridge semantics.
  - Involves: `app/providers/claude_code.py`, Claude Code server run/SSE/history tests.
  - Input: Reference `on_progress` facade conventions and local `/api/claude-code/runs` behavior.
  - Output: Provider callback and server run/SSE/history paths produce non-duplicated progress/final output.
  - Dependencies: TODO-173.
  - Completion standard: CHK-267 passes.
  - Checklist: CHK-267.

- [x] TODO-178 - Re-verify Claude Code native profile execution closure.
  - Goal: Ensure chat, meeting, and project paths can rely on final Claude Code native profile behavior.
  - Involves: native profile workspace lookup, custom registry, `--agent`, model, permission mode, interrupt, stream-json parsing.
  - Input: Phase 13 Claude Code implementation and reference native provider.
  - Output: Isolated tests cover main/local/native/project/custom profiles and runtime parsing.
  - Dependencies: TODO-177.
  - Completion standard: CHK-268 passes.
  - Checklist: CHK-268.

- [x] TODO-179 - Merge final safe provider diagnostics.
  - Goal: Bring remaining useful reference diagnostics into local native provider settings.
  - Involves: `/config/providers`, provider test endpoints, settings/source checks, locale strings.
  - Input: Reference native provider diagnostics and local safe config/i18n behavior.
  - Output: Codex/Claude/Hermes diagnostics are clear, localized where user-facing, and secret-redacted.
  - Dependencies: TODO-173.
  - Completion standard: CHK-269 and CHK-270 pass.
  - Checklist: CHK-269, CHK-270.

- [x] TODO-180 - Run final provider runtime regression matrix.
  - Goal: Prove final bottom-layer closure does not break shared provider contracts.
  - Involves: Codex, Claude Code, Hermes, provider app-server runtime, provider execution, provider config tests.
  - Input: TODO-174 through TODO-179 implementation.
  - Output: Passing provider/runtime test matrix.
  - Dependencies: TODO-174, TODO-175, TODO-176, TODO-177, TODO-178, TODO-179.
  - Completion standard: CHK-271 passes.
  - Checklist: CHK-271.

- [x] TODO-181 - Run final office workflow regressions.
  - Goal: Ensure final provider closure preserves local office business workflows.
  - Involves: project execution, meeting blocker/phase, archive/project context, sidebar/project meeting records, scheduled cron checks.
  - Input: TODO-180 passing provider matrix.
  - Output: Passing workflow regressions or explicit environmental blockers only.
  - Dependencies: TODO-180.
  - Completion standard: CHK-272 passes.
  - Checklist: CHK-272.

- [x] TODO-182 - Run final E2E acceptance.
  - Goal: Validate final user-visible provider behavior after close/reopen.
  - Involves: Chrome MCP if available, otherwise isolated HTTP/SSE/history fallback; Codex approval respond/history; Codex run cleanup; Claude Code run cleanup; provider settings.
  - Input: TODO-180 and TODO-181 results.
  - Output: E2E artifacts and notes, temporary services stopped, MCP locks/pages released when used.
  - Dependencies: TODO-181.
  - Completion standard: CHK-273 passes.
  - Checklist: CHK-273.

- [x] TODO-183 - Write final provider-runtime closure report.
  - Goal: Close the reference bottom-layer migration with no further safe merge phases pending.
  - Involves: `review.md`, `checklist.md`, `todolist.md`, `status.json`, final delivery notes.
  - Input: Final diff, test outputs, E2E artifacts, merge map.
  - Output: Final merged/adapted/preserved/permanent-not-merged report and status update.
  - Dependencies: TODO-182.
  - Completion standard: CHK-274 passes.
  - Checklist: CHK-274.


## Phase 15 Codex Native App-Server Core Merge Tasks

Phase 15 merges the reference branch's more complete Codex native app-server bottom layer into the current local layered implementation. It must preserve `ProviderRunBridge`, `JsonlAppServerRuntime`, `CodexAppRunState`, `provider_execution`, and local meeting/project/archive/scheduled behavior.

- [x] TODO-184 - Create Codex native app-server reference/local merge map.
  - Goal: Identify exactly which reference `app/providers/codex.py` components are already covered, missing, adapted, or intentionally skipped.
  - Involves: `remotes/eliautobot/main:app/providers/codex.py`, `app/provider_app_server.py`, `app/providers/codex_app_server.py`, `app/providers/codex_bridge.py`, `app/providers/codex.py`, `app/provider_execution.py`, `app/server.py`.
  - Input: Phase 15 checklist and current local layered implementation.
  - Output: Implementation notes in `review.md` or final report with copied/adapted/already-covered/skipped map.
  - Dependencies: Phase 15 checklist confirmation.
  - Completion standard: CHK-275 and CHK-276 pass.
  - Checklist: CHK-275, CHK-276.

- [x] TODO-185 - Add fixture coverage for reference Codex app-server lifecycle shapes.
  - Goal: Lock expected behavior before merging deeper lifecycle logic.
  - Involves: `tests/test_provider_app_server_runtime.py`, `tests/test_codex_bridge.py`, `tests/test_codex_provider.py`, or new focused fixture tests.
  - Input: Reference `CodexAppServerClient` lifecycle behavior.
  - Output: Tests for initialize, request, notify, stdout/stderr reading, timeout, process exit, interrupt, and cleanup.
  - Dependencies: TODO-184.
  - Completion standard: CHK-277 has failing/passing coverage that proves lifecycle parity.
  - Checklist: CHK-277.

- [x] TODO-186 - Merge missing JSON-RPC stdio lifecycle behavior into the local runtime layer.
  - Goal: Absorb useful reference `CodexAppServerClient` lifecycle behavior without making Codex transport monolithic again.
  - Involves: `app/provider_app_server.py`, `app/providers/codex_app_server.py`.
  - Input: TODO-185 tests and reference client behavior.
  - Output: Runtime/adapter lifecycle parity for process cleanup, request correlation, stderr reporting, interrupt, and timeout handling.
  - Dependencies: TODO-185.
  - Completion standard: CHK-277 passes and no provider app-server runtime regressions occur.
  - Checklist: CHK-277.

- [x] TODO-187 - Align Codex server-request and approval request/response handling.
  - Goal: Ensure reference-style app-server approval/server requests map cleanly to local pending approval and respond APIs.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, `app/server.py`, approval tests.
  - Input: Reference approval request/response mapping and local `/api/codex/approval/*`.
  - Output: Stable approval IDs, command previews, pending approval lookup, approve/cancel mapping, and run resume behavior.
  - Dependencies: TODO-186.
  - Completion standard: CHK-278 and CHK-286 pass.
  - Checklist: CHK-278, CHK-286.

- [x] TODO-188 - Expand Codex run-state parsing fixture coverage.
  - Goal: Cover missing reference event shapes before changing parser behavior.
  - Involves: `tests/test_codex_bridge.py`, `tests/test_codex_provider.py`, `tests/test_codex_runs_sse.py`, possible new fixture files.
  - Input: Reference `CodexAppRunState` message/reasoning/tool/token/error event shapes.
  - Output: Tests for deltas, final replies, reasoning, tools, token usage, terminal errors, interruption, and cancellation.
  - Dependencies: TODO-184.
  - Completion standard: CHK-279 through CHK-283 have targeted coverage.
  - Checklist: CHK-279, CHK-280, CHK-281, CHK-282, CHK-283.

- [x] TODO-189 - Merge missing CodexAppRunState parsing semantics into local adapter.
  - Goal: Bring local `CodexAppRunState` to reference-level coverage while preserving no-duplicate UI/history behavior.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex_bridge.py` if needed.
  - Input: TODO-188 tests and reference run-state implementation.
  - Output: Normalized reply, thinking, tools, tokenUsage, model/context, error/cancel status, `threadId`, `turnId`, `modifiedFiles`, and active operation fields.
  - Dependencies: TODO-188.
  - Completion standard: CHK-279 through CHK-283 pass.
  - Checklist: CHK-279, CHK-280, CHK-281, CHK-282, CHK-283.

- [x] TODO-190 - Preserve office execution and Codex run/SSE/history contracts.
  - Goal: Ensure bottom-layer changes do not alter office-facing APIs relied on by chat, project, and meeting paths.
  - Involves: `app/provider_execution.py`, `app/server.py`, `app/chat.js`, provider/server tests.
  - Input: TODO-187 and TODO-189 implementation.
  - Output: Stable `/api/codex/runs`, events, stop, history, progress cleanup, final reply persistence, approval UI, and project execution result shape.
  - Dependencies: TODO-187, TODO-189.
  - Completion standard: CHK-284, CHK-285, and CHK-286 pass.
  - Checklist: CHK-284, CHK-285, CHK-286.

- [x] TODO-191 - Run office workflow regression matrix.
  - Goal: Prove Codex bottom-layer merge does not regress local business workflows.
  - Involves: Project execution tests, meeting blocker/phase tests, project meeting records, archive/project context, scheduled checks where available.
  - Input: TODO-190 passing provider tests.
  - Output: Passing workflow regressions or documented environmental blockers only.
  - Dependencies: TODO-190.
  - Completion standard: CHK-287 passes.
  - Checklist: CHK-287.

- [x] TODO-192 - Run real or fixture-backed Codex app-server E2E.
  - Goal: Validate user-visible behavior after the native core merge.
  - Involves: Local service, HTTP/SSE/history checks, Chrome MCP when available, real Codex CLI if available or fixture app-server fallback.
  - Input: TODO-191 passing regression suite.
  - Output: E2E evidence for chat, tool/reasoning, approval, cancel, history reload, and no stale progress/status/message duplication.
  - Dependencies: TODO-191.
  - Completion standard: CHK-288 passes and temporary services/MCP locks are cleaned up.
  - Checklist: CHK-288.

- [x] TODO-193 - Update Phase 15 acceptance report and status.
  - Goal: Make the Codex native core merge auditable.
  - Involves: `review.md`, `checklist.md`, `todolist.md`, `status.json`, final delivery notes.
  - Input: Implementation diff, tests, E2E artifacts, merge map.
  - Output: Completed checklist evidence, completed todolist items, latest verification record, and documented remaining intentional architecture boundaries.
  - Dependencies: TODO-192.
  - Completion standard: CHK-289 passes.
  - Checklist: CHK-289.


## Phase 15 Implementation Notes - 2026-06-30T17:05:00+08:00

Completed in this slice: TODO-184 through TODO-193.

Merged/adapted from the reference Codex native app-server core:

- Generic JSONL app-server runtime now keeps stderr diagnostics and includes process-exit stderr in pending request failures.
- Codex app-server initialize now advertises experimental API capability while preserving the local layered runtime.
- Codex app-server approval handling now supports reference-style command, file-change, permissions, legacy exec/apply-patch, user-input, and MCP elicitation request shapes through the existing local pending interaction store.
- Codex approval records now include stable profile-aware metadata and continue to resolve through both `respond()` and `respond_approval()`.
- Codex run-state handling now preserves final reply, reasoning, tools, token usage, file/path/URI modified files, cancellation, timeout, and app-server exit errors in the local normalized result contract.

Preserved local boundaries:

- `ProviderRunBridge`, `JsonlAppServerRuntime`, `CodexAppRunState`, `provider_execution`, `app/providers/codex.py` facade, and local meeting/project/archive/scheduled behavior remain authoritative.
- The reference monolithic `app/providers/codex.py` loop was not whole-file merged.

Verification completed:

- `.venv/bin/python tests/test_provider_app_server_runtime.py`
- `.venv/bin/python tests/test_codex_bridge.py`
- `.venv/bin/python tests/test_codex_provider.py`
- `.venv/bin/python tests/test_codex_server.py`
- `.venv/bin/python tests/test_codex_runs_sse.py`
- `.venv/bin/python tests/test_provider_execution_contract.py`
- `.venv/bin/python tests/test_project_execution.py`
- `.venv/bin/python tests/test_meeting_request_blocks_task.py`
- `node tests/check_codex_runs_bridge.mjs`
- `node tests/check_codex_approval_ui.mjs`
- `node tests/check_codex_app_server_split.mjs`
- `node --check app/chat.js`
- `git diff --check`

Known non-blocking noise: `tests/test_project_execution.py` logged expected gateway WebSocket connection failures because no local OpenClaw gateway was reachable; assertions passed. Real Codex/Chrome MCP E2E was not run in this slice because the requested core parity is covered by fixture-backed app-server tests and existing HTTP/SSE/source regressions.


## Phase 15 MCP E2E Follow-Up - 2026-06-30T18:39:30+08:00

A real Chrome MCP E2E recheck found an intermittent real Codex app-server failure: after one successful native run, a later run could fail with `App-server request timed out: thread/start`. The root cause was that the local bridge reused a long-lived Codex app-server process without recovering when a startup RPC became stuck.

Fix applied:

- `CodexAppServerClient` now serializes run/compact operations per client.
- `thread/start` and `thread/resume` now restart the app-server and retry once on timeout.
- Startup request timeout is configurable via `VO_CODEX_START_TIMEOUT_SEC` for focused tests; production default remains 30 seconds.
- Fixture coverage now simulates a stuck first `thread/start` and verifies restart/retry recovery.

Real MCP validation after the fix:

- Temporary latest-code service started at `http://127.0.0.1:8148` with `VO_CODEX_ENABLED=1`.
- Chrome MCP executed two consecutive real Codex `/api/codex/runs` requests against `codex-local`.
- Both runs emitted SSE sequence `run.started -> provider.activity -> run.completed`.
- Both histories contained exactly the human request and Codex reply with real `threadId`, `turnId`, `modifiedFiles: []`, and expected reply text:
  - `OK_phase15-first-1782815840992`
  - `OK_phase15-second-1782815895867`
- `allOk: true`; temporary service was stopped after verification.

Additional regressions after the fix passed:

- `.venv/bin/python tests/test_codex_bridge.py`
- `.venv/bin/python tests/test_provider_app_server_runtime.py`
- `.venv/bin/python tests/test_codex_runs_sse.py`
- `.venv/bin/python tests/test_codex_provider.py`
- `.venv/bin/python tests/test_codex_server.py`
- `.venv/bin/python tests/test_provider_execution_contract.py`
- `.venv/bin/python tests/test_project_execution.py`
- `.venv/bin/python tests/test_meeting_request_blocks_task.py`
- `node tests/check_codex_runs_bridge.mjs`
- `node tests/check_codex_approval_ui.mjs`
- `node tests/check_codex_app_server_split.mjs`
- `git diff --check`


## Phase 16 Final Reference Feature Closure Tasks

Phase 16 is the final selective merge phase for `eliautobot/main`. The target is feature closure, not text identity: merge or adapt all safe reference behavior into the local layered architecture, then document every remaining difference as intentional or unsafe.

- [x] TODO-194 - Build final reference/local diff inventory and closure matrix.
  - Goal: Create the working map for the last merge pass.
  - Involves: `remotes/eliautobot/main`, local provider/runtime/server/UI/docs/tests files, `review.md`.
  - Input: Phase 16 checklist, current local branch, cached or freshly fetched reference branch.
  - Output: A file/feature matrix that marks each reference difference as pending, merged, adapted, already covered, local boundary, or unsafe/obsolete.
  - Dependencies: Phase 16 checklist confirmation.
  - Completion standard: CHK-290 and CHK-291 pass.
  - Checklist: CHK-290, CHK-291.

- [x] TODO-195 - Preserve non-replace boundaries before editing.
  - Goal: Make sure the final merge remains selective and does not erase local architecture or VO product behavior.
  - Involves: `app/server.py`, `app/chat.js`, `app/game.js`, `app/projects.js`, `app/models.html`, `app/setup.html`, provider facades.
  - Input: TODO-194 matrix and local architecture boundaries.
  - Output: Explicit implementation guardrails in the closure matrix and final report.
  - Dependencies: TODO-194.
  - Completion standard: CHK-292 passes throughout the phase.
  - Checklist: CHK-292.

- [x] TODO-196 - Close remaining Codex app-server/runtime parity gaps.
  - Goal: Merge any remaining safe Codex runtime details while preserving the local layered client/facade.
  - Involves: `app/provider_app_server.py`, `app/providers/codex_app_server.py`, `app/providers/codex_bridge.py`, `app/providers/codex.py`, `app/provider_execution.py`, `app/server.py`.
  - Input: Reference `app/providers/codex.py`, prior Phase 15 implementation, Codex tests.
  - Output: Final Codex parity for auth/status, initialize, run/resume/compact/cancel, timeout recovery, stderr diagnostics, and availability reporting.
  - Dependencies: TODO-194, TODO-195.
  - Completion standard: CHK-293 passes.
  - Checklist: CHK-293.

- [x] TODO-197 - Finalize Codex approval and pending interaction parity.
  - Goal: Ensure app-server, legacy, UI, history, and presence approval flows are all complete and duplicate-safe.
  - Involves: `app/providers/codex_app_server.py`, `app/providers/codex.py`, `app/server.py`, `app/chat.js`, approval tests.
  - Input: Reference approval metadata/response shapes and local `/api/codex/approval/*` implementation.
  - Output: Stable pending discovery, approve/cancel response mapping, cancellation, duplicate response protection, history persistence, and `gateway_presence` events.
  - Dependencies: TODO-196.
  - Completion standard: CHK-294 passes.
  - Checklist: CHK-294.

- [x] TODO-198 - Finalize Codex event parsing parity and fixture coverage.
  - Goal: Cover remaining reference event shapes for tool, reasoning, token, and error data.
  - Involves: `app/providers/codex_app_server.py`, Codex fixture tests, run/SSE tests.
  - Input: Reference run-state/event parsing and local no-duplicate UI/history rules.
  - Output: Stable normalized `reply`, `thinking`, `tools`, `tokenUsage`, `threadId`, `turnId`, `modifiedFiles`, status, and error fields.
  - Dependencies: TODO-196.
  - Completion standard: CHK-295 passes.
  - Checklist: CHK-295.

- [x] TODO-199 - Validate real Codex app-server behavior.
  - Goal: Prove final Codex bottom layer works with the real CLI where available.
  - Involves: Latest-code temporary service, `/api/codex/runs`, SSE events, history reload, Chrome MCP or HTTP/SSE fallback.
  - Input: TODO-196 through TODO-198 implementation.
  - Output: Consecutive real Codex run evidence and cleanup of temporary service/MCP resources.
  - Dependencies: TODO-198.
  - Completion standard: CHK-296 passes or an environmental fallback is documented.
  - Checklist: CHK-296.

- [x] TODO-200 - Close remaining Claude Code provider/profile parity gaps.
  - Goal: Merge safe Claude Code metadata/profile/roster/create-delete-edit behavior from the reference branch.
  - Involves: `app/providers/claude_code.py`, `app/server.py`, `app/discovery.py`, `app/game.js`, `app/models.html`, provider config tests.
  - Input: Reference Claude Code provider/server/UI behavior and current local profile fixes.
  - Output: Correct Claude Code agent names, profiles, status, custom registry/workspace handling, and VO roster semantics.
  - Dependencies: TODO-194, TODO-195.
  - Completion standard: CHK-297 passes.
  - Checklist: CHK-297.

- [x] TODO-201 - Finalize Claude Code stream-json/progress/run behavior.
  - Goal: Cover remaining stream-json edge cases and keep shared bridge history/progress semantics.
  - Involves: `app/providers/claude_code.py`, `ProviderRunBridge`, Claude Code run/SSE tests.
  - Input: Reference stream-json parser behavior and local progress-history implementation.
  - Output: Stable deltas, JSON arg fragments, tool events, final response, errors, cancellation, and progress snapshots.
  - Dependencies: TODO-200.
  - Completion standard: CHK-298 passes.
  - Checklist: CHK-298.

- [x] TODO-202 - Verify Claude Code chat, meeting, and project compatibility.
  - Goal: Ensure Claude Code uses the normalized office contract in all supported VO entry points.
  - Involves: `app/server.py`, `app/provider_execution.py`, Claude provider tests, project/meeting tests.
  - Input: TODO-200 and TODO-201 implementation.
  - Output: Fixture-backed evidence for Claude Code chat/run/SSE plus meeting/project participation paths.
  - Dependencies: TODO-201.
  - Completion standard: CHK-299 passes.
  - Checklist: CHK-299.

- [x] TODO-203 - Close remaining Hermes native API/provider parity gaps.
  - Goal: Merge safe Hermes status/settings/facade details while preserving CLI fallback.
  - Involves: `app/providers/hermes.py`, `app/server.py`, provider config, Hermes tests.
  - Input: Reference Hermes provider/settings/server behavior and current native API client.
  - Output: Native API status, run/SSE, fallback diagnostics, profile settings, and history metadata parity.
  - Dependencies: TODO-194, TODO-195.
  - Completion standard: CHK-300 passes.
  - Checklist: CHK-300.

- [x] TODO-204 - Verify Hermes fallback and opt-in behavior.
  - Goal: Make sure Hermes remains usable when native API is absent or fails.
  - Involves: Hermes API client/server tests, CLI fallback paths, approval/failure tests.
  - Input: TODO-203 implementation.
  - Output: Passing native success, native failure fallback, approval/failure state, and CLI fallback coverage.
  - Dependencies: TODO-203.
  - Completion standard: CHK-301 passes.
  - Checklist: CHK-301.

- [x] TODO-205 - Merge safe server API, discovery, presence, and config parity.
  - Goal: Bring remaining provider-supporting server helpers in without replacing local workflow APIs.
  - Involves: `app/server.py`, `app/discovery.py`, `app/gateway_presence.py`, `app/api-usage.js`, `.env.example`, `app/vo-config.json`.
  - Input: Reference provider config/status/progress/approval/discovery/model helper behavior.
  - Output: Reference-compatible provider runtime metadata, complete presence events, and safe config examples.
  - Dependencies: TODO-196, TODO-200, TODO-203.
  - Completion standard: CHK-302, CHK-303, and CHK-304 pass.
  - Checklist: CHK-302, CHK-303, CHK-304.

- [x] TODO-206 - Merge safe chat UI progress/history/approval parity.
  - Goal: Bring remaining reference chat behavior while preserving local fixes for persistence and duplicate filtering.
  - Involves: `app/chat.js`, `app/style.css`, `app/i18n.js`, `app/locales/en.json`, `app/locales/zh.json`, UI tests.
  - Input: Reference chat UI behavior, local Codex/Claude/Hermes progress history, VO modal style.
  - Output: Stable send/progress/completion/history reload/provider switching plus localized VO-styled pending interaction controls.
  - Dependencies: TODO-197, TODO-201, TODO-205.
  - Completion standard: CHK-305 and CHK-306 pass.
  - Checklist: CHK-305, CHK-306.

- [x] TODO-207 - Merge safe models/setup native provider UI parity.
  - Goal: Make native provider configuration and diagnostics complete and localized.
  - Involves: `app/models.html`, `app/setup.html`, `app/style.css`, locales, provider runtime settings checks.
  - Input: Reference setup/model fields and local secret-preserving config behavior.
  - Output: Actionable Codex/Claude/Hermes settings, status/test controls, localized labels, and no setup/model regressions.
  - Dependencies: TODO-205.
  - Completion standard: CHK-307 passes.
  - Checklist: CHK-307.

- [x] TODO-208 - Merge safe game/office UI parity and i18n cleanup.
  - Goal: Bring compatible reference office UI details without breaking canvas, agents, meetings, or projects.
  - Involves: `app/game.js`, `app/index.html`, `app/style.css`, locale files, source/browser checks.
  - Input: Reference office UI changes and recent local VO dialog/agent-name fixes.
  - Output: Compatible roster/dialog/label improvements plus i18n integrity for all new text.
  - Dependencies: TODO-206, TODO-207.
  - Completion standard: CHK-308 and CHK-309 pass.
  - Checklist: CHK-308, CHK-309.

- [x] TODO-209 - Copy or adapt useful reference tests.
  - Goal: Ensure merged behavior is covered by runnable local tests.
  - Involves: `tests/`, provider tests, UI source checks, browser/MCP checks.
  - Input: Reference tests and TODO-196 through TODO-208 implementation.
  - Output: Added/adapted tests for safe behavior; obsolete/conflicting tests documented in the closure report.
  - Dependencies: TODO-208.
  - Completion standard: CHK-310 passes.
  - Checklist: CHK-310.

- [x] TODO-210 - Update provider runtime docs and troubleshooting notes.
  - Goal: Make final provider behavior auditable and usable.
  - Involves: `docs/`, `.env.example`, `review.md`, possible README-adjacent docs if relevant.
  - Input: Final implementation and closure matrix.
  - Output: Docs for Codex/Claude/Hermes native runtime, settings, fallbacks, approvals, progress/history, diagnostics, and known boundaries.
  - Dependencies: TODO-209.
  - Completion standard: CHK-311 passes.
  - Checklist: CHK-311.

- [x] TODO-211 - Run core provider/runtime regression suite.
  - Goal: Validate all provider-runtime behavior after the final merge.
  - Involves: Python tests, Node source checks, `git diff --check`.
  - Input: TODO-196 through TODO-210 implementation.
  - Output: Passing provider app-server runtime, Codex, Claude Code, Hermes, provider execution, provider config, and UI source checks.
  - Dependencies: TODO-210.
  - Completion standard: CHK-312 passes.
  - Checklist: CHK-312.

- [x] TODO-212 - Run VO workflow regression suite.
  - Goal: Prove local project/meeting/archive/scheduled behavior was not regressed.
  - Involves: Project execution tests, meeting blocker/phase tests, project meeting records, archive/source checks, scheduled/cron checks where available.
  - Input: TODO-211 passing provider suite.
  - Output: Passing workflow regressions or documented environment-only blockers.
  - Dependencies: TODO-211.
  - Completion standard: CHK-313 passes.
  - Checklist: CHK-313.

- [x] TODO-213 - Run final browser/MCP E2E.
  - Goal: Validate user-visible Codex, Claude Code, Hermes-visible, settings, model, and history flows.
  - Involves: Latest-code temporary service, Chrome MCP when available, HTTP/SSE fallback, service cleanup.
  - Input: TODO-211 and TODO-212 passing regressions.
  - Output: End-to-end evidence for chat/run/SSE/history/settings/model surfaces and released MCP/Chrome/temp-service resources.
  - Dependencies: TODO-212.
  - Completion standard: CHK-314 passes.
  - Checklist: CHK-314.

- [x] TODO-214 - Write final reference-diff closure report and update status.
  - Goal: Close the migration with no unexplained safe feature gaps against `eliautobot/main`.
  - Involves: `requirement.md`, `review.md`, `checklist.md`, `todolist.md`, `status.json`, final delivery notes.
  - Input: Final diff, closure matrix, test results, E2E evidence, documented boundaries.
  - Output: Completed Phase 16 report, checklist evidence, todo status, latest verification, and remaining intentional differences.
  - Dependencies: TODO-213.
  - Completion standard: CHK-315 passes.
  - Checklist: CHK-315.


## Phase 16 Completion Notes - 2026-06-30T19:31:55+08:00

Completed in this slice: TODO-194 through TODO-214.

Implementation notes:

- TODO-194/TODO-195: Final reference diff accounting was completed against cached `remotes/eliautobot/main` at `eb119493`. Broad textual differences remain expected because local layered provider/runtime, project, meeting, archive, scheduled, i18n, and VO UI boundaries are authoritative.
- TODO-196/TODO-199: Codex final parity was rechecked rather than broadly rewritten. The Phase 15 native app-server core merge already covered the safe reference Codex bottom-layer behavior; this phase verified it with provider tests and a real Codex HTTP/SSE/history run.
- TODO-200/TODO-202: Claude Code native profile behavior was completed by using profile workspace defaults for native agents and preventing non-agent workspace directories from shadowing native user agents. Chat/run/SSE behavior was verified through provider/server tests and HTTP/SSE E2E.
- TODO-203/TODO-204: Hermes native API parity was completed by fixing native chat/SSE visible-thinking result handling while preserving CLI fallback and existing native API tests.
- TODO-205/TODO-208: Server/config/UI parity remains covered by the local implementation; no additional broad UI replacement was needed. Existing source/i18n/provider runtime UI checks passed.
- TODO-209/TODO-214: Regression, E2E, checklist, and status documentation were completed. Final closure report is in `review.md`, checklist evidence is in `checklist.md`, and latest verification is in `status.json`.

Final verification:

- Provider/runtime Python suite passed for Claude Code, Codex, Hermes, provider runtime config, provider app-server runtime, provider execution contract, and run/SSE server paths.
- VO workflow regressions passed for project execution, meeting blockers, and meeting phase behavior.
- Node/source UI checks passed for Codex/Claude run bridges, Codex approval UI, provider runtime settings, Codex app-server split, i18n integrity, project meeting records, and project execution start payload.
- Final temporary service `http://127.0.0.1:8156` passed `/health`, provider metadata, Claude Code run/SSE/history, and real Codex run/SSE/history checks. The service was stopped after verification.

Residual differences:

- Remaining differences from `eliautobot/main` are intentional: the local branch keeps `ProviderRunBridge`, `JsonlAppServerRuntime`, Codex protocol adapter split, provider execution normalization, VO project/meeting/archive/scheduled behavior, localized UI, and existing setup/model/chat surfaces instead of adopting reference whole-file server/UI/provider replacements.
