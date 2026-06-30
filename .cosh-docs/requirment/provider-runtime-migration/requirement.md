# Provider Runtime Migration

## Background

We need to merge provider-runtime capabilities from the reference implementation at:

https://github.com/codeshitmeshit/my-virtual-office/compare/main...eliautobot%3Amy-virtual-office%3Amain

The reference branch adds deeper native provider handling for Codex, Hermes, Claude Code, chat streaming/events, setup/model management, and provider run lifecycle APIs. Our current working tree already contains substantial project and meeting changes. The migration must preserve those existing project and meeting behaviors while absorbing the useful provider-runtime foundation.

## Product Goal

Enable richer native provider support without losing the current project and meeting workflows.

The user-visible outcome should be:

- Agent lists become richer with Codex, Hermes, and Claude Code provider agents.
- Provider execution becomes more transparent through run status, tools, approvals, errors, cancellation, and history.
- Project execution can keep using provider agents reliably and leave traceable records.
- Existing project and meeting flows remain intact.

## Target Users

- Users who run Virtual Office with multiple AI providers.
- Users who rely on project task execution, review, and acceptance flows.
- Users who rely on AI meeting requests, meeting blocking, meeting records, and meeting action items.
- Advanced users who need provider-level visibility and approval handling.

## Scope

### In Scope

- Use the reference implementation as the source of provider-runtime ideas and lower-level provider capabilities.
- Preserve our current project and meeting behavior as the product authority.
- Add or adapt native provider support for:
  - Codex provider runtime.
  - Hermes native run/event capability where applicable.
  - Claude Code provider discovery and basic chat/task participation.
- Improve provider discovery and agent roster handling.
- Improve chat/provider run visibility using stream/event/history patterns where safe.
- Improve setup/model management where it does not break existing workflows.
- Add detailed regression and acceptance coverage.

### Out of Scope

- Replacing our project execution flow with the reference branch's project behavior.
- Replacing our meeting request, blocking, meeting record, or action-item logic.
- Broad UI redesign unrelated to provider runtime migration.
- Removing existing OpenClaw behavior.
- Changing product semantics for task acceptance, reviewer skip, meeting request confirmation, or meeting result writeback unless explicitly required to preserve compatibility.

## Conflict Policy

If the reference implementation conflicts with our current behavior:

- Project pages and meeting pages use our current behavior as the source of truth.
- Chat, setup, models, and provider-management pages may follow the reference implementation more closely.
- Shared server code must be manually merged by functional area. Do not replace `app/server.py` wholesale.
- Shared frontend code must be manually merged by functional area. Do not replace `app/chat.js`, `app/game.js`, or `app/projects.js` wholesale.

## Provider Expectations

### Codex

- Preserve current Codex project execution conversation/attempt behavior.
- Absorb useful native provider runtime concepts from the reference implementation.
- Support clear run status, tools, reasoning/thinking, approvals, cancellation, history, and traceable task records.

### Hermes

- Preserve current Hermes profile discovery, CLI compatibility, per-conversation history, and approval behavior.
- Absorb Hermes native API run/event support where available.
- Fallback behavior must remain usable when Hermes native API is unavailable.

### Claude Code

- Add provider discovery and basic chat/task participation based on the reference implementation.
- Claude Code does not need full meeting parity in the first migration pass unless it can be added without destabilizing current project/meeting flows.

## Non-Regression Requirements

The following existing capabilities must not regress:

- Project creation, task creation, project execution, execution state transitions, review, rework, acceptance, cancellation, retry, and continuous flow.
- Task execution evidence, comments, checklist updates, attempt/review records, and blocked reasons.
- Meeting request creation, confirmation, rejection, auto-approval rules, high-priority meeting confirmation, meeting blocking, meeting records, meeting result writeback, and action items.
- Archive/project context behavior that depends on project/task/meeting records.
- Existing OpenClaw chat and agent discovery behavior.
- Existing Hermes and Codex fallback behavior.

## Success Criteria

- Existing project and meeting tests continue to pass.
- New provider-runtime paths are covered by targeted tests.
- Codex, Hermes, and Claude Code provider agents can be discovered according to configuration.
- Codex/Hermes can participate in project task execution without losing attempt/review traceability.
- Provider run events and approvals are visible enough for debugging and user action.
- Existing meeting and project user workflows remain behaviorally compatible after migration.

## Phase 15 Addendum - Codex Native App-Server Core Merge

Added at 2026-06-30T16:18:00+08:00 after another comparison with `eliautobot/main`.

### Background

The reference branch's `app/providers/codex.py` still contains a more complete native Codex app-server bottom layer than the current local provider facade. The useful pieces are:

- `CodexAppServerClient`
- app-server JSON-RPC stdio lifecycle management
- server request/approval request handling
- approval request/response mapping
- `CodexAppRunState`
- tool, reasoning, token usage, terminal error, and final turn parsing

The local implementation has already built a safer layered architecture around:

- `app/provider_app_server.py`
- `app/providers/codex_app_server.py`
- `app/providers/codex_bridge.py`
- `app/providers/codex.py`
- `app/provider_execution.py`
- `ProviderRunBridge` in `app/server.py`

### Phase 15 Goal

Merge the reference Codex native app-server core into the current layered implementation instead of replacing the local provider files wholesale.

### Phase 15 Scope

In scope:

- Re-audit the reference `CodexAppServerClient` against local `JsonlAppServerRuntime` and `CodexAppServerBridge`.
- Merge any still-missing app-server JSON-RPC lifecycle behavior into the local runtime/adapter layer.
- Re-audit reference approval server-request handling and ensure local approval request/response behavior remains equivalent.
- Re-audit `CodexAppRunState` parsing coverage for:
  - message deltas and final replies
  - reasoning/thinking events
  - tool calls and tool results
  - MCP/dynamic/web-search style tool events
  - token usage/model/context metadata
  - terminal errors/interruption/cancellation
  - `threadId`, `turnId`, `modifiedFiles`, active operation semantics
- Preserve the current office-facing return contract for chat, meeting, project execution, approval, history, and SSE.

Out of scope:

- Whole-file replacement of `app/providers/codex.py`.
- Removing `ProviderRunBridge`, `JsonlAppServerRuntime`, `CodexAppRunState`, or `provider_execution`.
- Breaking current Codex approval UI, interaction fallback, project execution return values, meeting/project blocker behavior, modified file display, conversation history, or active operation handling.
- Replacing local meeting/project/archive/scheduled behavior with reference branch behavior.

### Phase 15 Success Criteria

- Current Codex behavior remains compatible for chat, approval, project execution, meeting participation, history reload, run/SSE, and cancellation.
- Local Codex bottom layer demonstrably covers the useful reference native app-server behavior without reverting to the reference monolithic provider structure.
- Tests cover both fixture app-server behavior and office-facing normalized results.
- Remaining differences, if any, are documented as intentional architecture boundaries.

## Phase 16 Addendum - Final Reference Feature Closure

Added at 2026-06-30T19:05:00+08:00 after the user requested the next phase to be the final merge phase and expected the next branch comparison against `eliautobot/main` to show all safe reference features merged.

### Background

Phases 1 through 15 migrated the core provider runtime architecture, Codex app-server bottom layer, Claude Code run/SSE integration, Hermes native API foundation, provider settings, progress history, approval flows, and major VO UI compatibility fixes. A fresh comparison against cached `remotes/eliautobot/main` still shows broad differences across:

- `app/server.py`
- `app/chat.js`
- `app/game.js`
- `app/models.html`
- `app/setup.html`
- `app/providers/codex.py`
- `app/providers/claude_code.py`
- `app/providers/hermes.py`
- `app/discovery.py`
- `app/gateway_presence.py`
- `app/api-usage.js`
- `app/style.css`
- `.env.example`
- `app/vo-config.json`
- docs/tests and peripheral repo files

The goal of Phase 16 is not to make the local branch text-identical to the reference branch. The goal is to close the feature gap: all safe user-facing and bottom-layer provider features from the reference branch should be merged or deliberately adapted into the local architecture, and every remaining reference difference should be explicitly categorized.

### Phase 16 Goal

Complete the final selective merge of all safe remaining reference features from `eliautobot/main`, while preserving local VO product behavior and the layered provider architecture.

### Phase 16 Scope

In scope:

- Rebuild a complete reference/local diff inventory by file and by feature.
- Merge any remaining safe Codex bottom-layer details not already covered by `JsonlAppServerRuntime`, `CodexAppServerClient`, `CodexAppRunState`, `ProviderRunBridge`, and `provider_execution`.
- Merge any remaining safe Claude Code provider details, especially native agent metadata, stream-json parsing edge cases, run status/auth diagnostics, and provider roster behavior.
- Merge any remaining safe Hermes native API/provider facade details, including settings, discovery, status, and fallback diagnostics.
- Merge safe server API helper parity where it supports providers, progress history, native settings, approvals, or diagnostics without replacing local meeting/project/archive/scheduled behavior.
- Merge safe chat/setup/models/game UI parity only when it is localized, VO-styled, and does not regress current conversation, meeting, project, archive, scheduled, or agent creation workflows.
- Merge safe configuration and documentation parity for provider runtime variables, native provider setup, and troubleshooting.
- Add or adapt reference tests that verify merged behavior and keep local regression coverage.
- Produce a final branch-diff closure report that categorizes every remaining reference difference as:
  - merged
  - adapted into local architecture
  - already covered
  - intentionally local product boundary
  - unsafe or obsolete reference behavior

Out of scope:

- Whole-file replacement of `app/server.py`, `app/chat.js`, `app/game.js`, `app/projects.js`, `app/models.html`, `app/setup.html`, or provider facades.
- Replacing local project execution, meeting request/blocker, archive room, scheduled/cron, i18n, or VO UI semantics with reference implementations.
- Removing local tests, docs, i18n, project/meeting state machines, or bridge/runtime abstractions.
- Blindly accepting reference README/LICENSE/website/docker changes unless they directly support the provider-runtime migration and pass review.
- Treating formatting-only or product-direction differences as mandatory merges.

### Phase 16 Non-Regression Requirements

- Codex chat, run/SSE, approval, history reload, cancellation, app-server recovery, project execution, meeting participation, `threadId`, `turnId`, `modifiedFiles`, tools, thinking, token usage, and active operation semantics must remain stable.
- Claude Code chat, run/SSE, history reload, provider roster display, meeting participation, project execution entry points, stream-json parsing, and progress display must remain stable.
- Hermes CLI fallback and native API opt-in behavior must remain stable.
- Existing OpenClaw behavior must not regress.
- User chat messages and provider replies must persist across closing/reopening panels.
- No duplicate terminal completion cards, no stale progress messages, and no status-only thinking bubbles should appear.
- Existing local project, meeting, archive, scheduled, and task/review workflows remain authoritative.

### Phase 16 Success Criteria

- The post-phase comparison against `eliautobot/main` has no unexplained provider-runtime feature gaps.
- All safe reference features are either merged directly or adapted into the local architecture.
- Remaining differences are documented with concrete reasons and are acceptable intentional boundaries.
- Unit, integration, source-level UI, and browser/MCP E2E checks pass for Codex, Claude Code, Hermes, and core VO workflows.
- Temporary services and MCP/Chrome locks are released after validation.
