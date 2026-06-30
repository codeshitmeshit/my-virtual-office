# Provider Runtime Migration Review

## Review Summary

The requirement is product-clear enough to proceed to a testing checklist. No blocking product clarification remains.

This is a high-risk merge because the reference implementation changes broad shared files, especially `app/server.py`, `app/chat.js`, `app/discovery.py`, `app/setup.html`, `app/models.html`, and provider modules. The migration must be handled as a functional transplant, not a branch-level merge or full-file replacement.

## Reference Areas

The reference implementation contributes useful provider-runtime concepts:

- Full Codex provider adapter with native app-server style run lifecycle.
- Claude Code provider adapter.
- Hermes API client and native run/event support.
- Provider run endpoints such as `/api/*/runs`, `/events`, stop/interrupt, approval response, and history clear.
- Native provider setup/model-management extensions.
- Chat handling for provider-specific history, tools, thinking, approvals, token usage, and run events.

## Existing Local Areas To Preserve

The current working tree contains local changes that must remain authoritative:

- Project execution pipeline and state transitions.
- Task execution prompts, checklist update handling, meeting context handling, evidence handling, cancellation, stale active reconciliation, and executor-required behavior.
- AI meeting request flows, high-priority confirmation/auto-approve rules, task blocking, meeting result records, and action-item handling.
- Project/meeting frontend interactions in `app/game.js`, `app/projects.js`, related CSS/locales, and tests.

## Technical Merge Guidance

### Provider Modules

- `app/providers/claude_code.py` can be introduced mostly as a new module.
- `app/providers/hermes.py` should be merged by adding native API/run support while preserving current CLI fallback and per-conversation history assumptions.
- `app/providers/codex.py` requires careful adaptation because our current provider is thin and delegates to `codex_bridge.py`; the reference implementation is a larger provider-runtime implementation. Preserve the server-facing contract used by project execution.

### Discovery

`app/discovery.py` should gain richer Codex and Claude Code discovery while preserving existing OpenClaw and Hermes behavior. Backward-compatible function arguments matter because server configuration code may call discovery helpers in existing shapes.

### Server

`app/server.py` must be merged by function groups:

- Provider config loading.
- Provider discovery helpers.
- Provider history/session storage.
- Codex chat/run/approval/cancel APIs.
- Hermes chat/run/approval/cancel APIs.
- Claude Code APIs.
- Native model/setup APIs.

Do not overwrite project execution functions or meeting functions from the reference implementation. Any provider changes must be threaded into current project/meeting code through existing provider abstraction points.

### Frontend

- `app/chat.js`: integrate provider history/run/event/approval rendering carefully. Preserve existing Codex activity/interaction behavior unless replaced by an equivalent or better user-visible flow.
- `app/setup.html` and `app/models.html`: reference implementation can guide provider configuration UX.
- `app/game.js`, `app/projects.js`: avoid reference replacement. Only add provider compatibility where needed for project/meeting workflows.

## Risk Assessment

### High Risks

- Full-file replacement could remove local project/meeting changes.
- Provider run events may introduce inconsistent history or duplicated assistant messages.
- Approval flows differ by provider and may deadlock task execution if not normalized.
- Claude Code provider may appear available but not satisfy task execution expectations.
- Setup/model management changes may alter existing OpenClaw or OAuth behavior.

### Medium Risks

- Token usage and context metrics may be missing or inconsistent across providers.
- Cancellation semantics may differ across Codex, Hermes, Claude Code, and OpenClaw.
- Long-running provider runs may leave stale active state after restart.
- History clearing may clear the wrong provider/profile/conversation.

### Low Risks

- Adding new documentation and provider tests is low risk if isolated.
- Adding new provider module files is low risk if imports are guarded and disabled-by-default behavior is clear.

## Compatibility Requirements

- Provider routes should return consistent `ok`, `error`, `reply`, `sessionId` or `threadId`, `runId`, `tools`, `thinking`, `approval`, and `tokenUsage` fields where applicable.
- Existing project execution should continue to consume provider results without needing to know provider internals.
- Existing UI should not require all provider capabilities to exist. Missing native APIs must degrade gracefully.
- Existing tests should be run before and after provider migration where practical.

## Review Decision

Proceed to checklist.

There are no blocking technical questions at the requirements level, but implementation must be staged and verified with a broad regression checklist before any final acceptance.


## Phase 4 Review - Reference Project/Meeting UI Parity

Phase 4 is a follow-up planning scope after the provider-runtime migration. It targets useful non-provider reference behavior from `eliautobot/main`, especially office meeting visualization and agent workspace/project context, while preserving the local project execution and AI meeting state machines.

### Product Direction

The useful parts to merge are presentation and visibility features:

- Meeting room / meeting table visualization.
- Active/completed meeting panels and sidebar awareness.
- Agent workspace read-only project/task/meeting context.
- Canvas interaction UX such as furniture/object service queues when they do not alter project state.
- Optional scheduled/cron visual status only if it routes through local project execution.

The risky parts are state-writing features that could bypass local workflows:

- Direct office-level meeting create/end routes that do not know about project meeting requests, blockers, results, or action-item writeback.
- Agent workspace task start/complete/delete actions that bypass project execution checks.
- Cron-triggered task execution that bypasses dirty workspace, executor-required, review, meeting-blocker, cancellation, and stale repair rules.
- Canvas agent state overrides that hide project/provider activity.

### Technical Decision

Proceed with a Phase 4 checklist focused on adapter-driven UI integration:

- Use local project/meeting state as the source of truth.
- Build adapter/projection helpers for office meeting visualization instead of replacing existing meeting handlers.
- Start with read-only agent workspace project/task context.
- Gate or omit write actions until they can call existing local APIs safely.
- Do not wholesale replace `app/server.py`, `app/game.js`, `app/projects.js`, or project/meeting CSS.


## Phase 5 Review - Generic Provider Run Bridge

Phase 5 continues the provider-runtime migration by extracting the current run/SSE/event distribution behavior into a provider-neutral bridge. The concrete product goal is to let Claude Code reuse the same run distribution foundation as Codex, while preserving each provider's own protocol, subprocess/API adapter, approval behavior, and history semantics.

### Product Direction

The useful reference implementation area is the lower-level run lifecycle and SSE mechanism:

- Background run creation endpoints.
- Run event streaming through SSE.
- Stop/interrupt endpoints.
- Ephemeral progress messages such as `claude-code-progress`.
- Provider activity updates through `gateway_presence.set_provider_event(...)`.
- Tool, reasoning, token usage, final reply, and failure events flowing through one UI-compatible channel.

The local implementation remains authoritative for project execution, meetings, archive behavior, scheduled/cron behavior, and existing Codex approval/activity compatibility.

### Technical Decision

Proceed with a Phase 5 checklist focused on a generic `ProviderRunBridge`:

- Extract shared run registry, queue, SSE streaming, event emission, metadata update, and cleanup behavior into `ProviderRunBridge`.
- Wire Claude Code run/SSE/stop routes to the generic bridge while preserving reference-derived Claude Code bottom-layer behavior.
- Add Codex run/SSE/stop routes on top of the same bridge, but keep existing `/api/codex/chat`, `/api/codex/activity`, `/api/codex/interaction`, and `/api/codex/cancel` intact for compatibility.
- Convert Codex activity events into bridge events incrementally instead of replacing the Codex provider adapter or frontend flow in one step.
- Keep Codex and Claude Code protocol-specific parsing in provider-specific handlers; only the lifecycle and distribution layer is common.
- Use focused server/source tests first, then project/meeting regression tests to prove original functionality is not lost.

### Risks

- If Codex activity polling is removed too early, existing approval and interaction UI may regress.
- If Claude Code and Codex event schemas are forced to be identical, provider-specific tool/reasoning data may be lost.
- If run cleanup is too aggressive, late SSE clients may miss terminal events.
- If presence events are emitted from provider-specific paths inconsistently, agent status may diverge between Codex and Claude Code.

### Non-Goals

- Do not replace local project, meeting, archive, or scheduled/cron implementations with reference branch versions.
- Do not remove existing Codex chat/activity endpoints in Phase 5.
- Do not make Claude Code claim unsupported project/meeting parity only because it now uses the common bridge.


## Phase 6 Review - Provider Execution Contract And Codex Native Bottom Layer

Phase 6 follows the Phase 5 bridge work. Phase 5 unified run/SSE distribution, but approval handling, active operation state, project execution result shape, modified file detection, thread/turn IDs, cancellation, and provider-specific result normalization are still mostly encoded in Codex-specific server logic. The next step is to extract those office-facing semantics into a provider-neutral execution contract and then move Codex's provider execution bottom layer closer to the reference branch.

### Product Direction

The product goal is that Codex and Claude Code can both participate in the same office workflows without each workflow knowing provider internals:

- Project execution consumes one normalized result contract.
- Meeting blockers and project task state can rely on common active-operation and cancellation semantics.
- Approval/interaction can be represented consistently even when provider-specific response APIs differ.
- Thread/session/turn IDs are preserved and traceable across chat, project execution, and history.
- Modified files and evidence are surfaced consistently where the provider can report them.
- Provider-specific details remain available as metadata instead of being discarded.

### Technical Decision

Proceed with a Phase 6 checklist focused on a new provider-neutral execution layer:

- Add shared helpers for normalized provider execution results, active operation records, approval/interaction records, modified-file tracking, and terminal status mapping.
- Keep `ProviderRunBridge` focused on run/SSE distribution; do not mix transport with result semantics.
- Adapt Codex and Claude Code to return the shared office execution contract while keeping provider-specific protocol parsing in their adapters.
- Migrate Codex's execution bottom layer toward the reference branch's app-server JSON-RPC implementation, preferably in `app/providers/codex.py`, while preserving the local server-facing compatibility methods: `send_message(...)`, `respond(...)`, and `cancel(...)`.
- Keep project execution, meeting blocker, archive, and scheduled/cron logic as consumers of the normalized contract, not as code copied from the reference branch.

### Reference Merge Guidance

The reference branch's `app/providers/codex.py` should be treated as the primary source for Codex native app-server execution:

- `CodexAppServerClient`.
- JSON-RPC initialize/account/read/conversation or turn execution flow.
- Progress callback/event parsing.
- interrupt/cancel and approval response behavior.
- token/tool/reasoning/session metadata where available.

Local compatibility must be retained:

- Current config fields and fixture modes such as `replyText`.
- Current multi-agent/workspace discovery and lifecycle work already merged in earlier phases.
- Current server handlers and tests that expect `send_message`, `respond`, and `cancel`.
- Current project execution result assumptions until they are routed through the new normalizer.

### Risks

- Replacing Codex provider wholesale could drop local fixture mode, multi-profile workspace handling, or current lifecycle safety checks.
- If project execution is switched before normalized result tests exist, task attempt/review records may lose evidence or modified-file data.
- Claude Code may not have equivalent approval or modified-file capabilities; the contract must allow unsupported fields to be explicit instead of pretending parity.
- Active operation state must stay per provider/agent/conversation to avoid cross-provider cancellation or approval leaks.

### Non-Goals

- Do not rewrite project execution or meeting blocker business logic in Phase 6.
- Do not remove legacy Codex endpoints until the normalized contract and frontend migration are verified.
- Do not force Claude Code to support Codex-specific approval protocol; normalize the office-facing shape and keep provider-specific response APIs behind adapters.


## Phase 7 Review - Generic App-Server Runtime And Codex Reference Protocol Layer

Phase 7 follows the Phase 6 execution contract work. The current local `app/providers/codex_bridge.py` already contains useful generic JSONL app-server runtime mechanics, but those mechanics are still coupled to Codex-specific operation parsing. The next step is to extract the generic runtime capability and then move the Codex protocol layer closer to the reference branch implementation.

### Product Direction

The product goal is to make provider app-server style integrations easier to maintain and extend:

- Generic runtime owns subprocess lifecycle, JSONL request/response routing, pending queues, reader thread, timeout, close, crash handling, and server-request dispatch.
- Codex protocol layer owns Codex-specific methods, event parsing, approval response, interrupt, token/tool/reasoning/message parsing, and conversion to the office execution contract.
- `CodexProvider` remains a stable facade for existing server/project/meeting consumers.
- Future providers with similar JSONL app-server behavior can reuse the runtime without inheriting Codex protocol assumptions.

### Technical Decision

Proceed with a Phase 7 checklist focused on a layered split:

- Add a generic app-server runtime module, for example `app/provider_app_server.py`.
- Move transport-only logic out of `codex_bridge.py`: process start/stop, JSONL send/read, request ID allocation, pending response queues, reader thread, and generic server request/notification hooks.
- Add a Codex-specific app-server protocol adapter, for example `app/providers/codex_app_server.py`, using the reference branch as the primary guide for Codex protocol behavior.
- Keep `app/providers/codex.py` as the public provider facade and preserve `send_message`, `send_chat_message`, `respond`, `respond_approval`, `cancel`, `interrupt`, and fixture/fallback behavior.
- Keep `provider_execution.py` as the office-facing normalization layer and `ProviderRunBridge` as the run/SSE distribution layer.

### Reference Merge Guidance

Reference branch Codex protocol code should be used for:

- `initialize` / initialized handshake where compatible.
- account/read or auth test behavior where safe.
- `thread/start`, `thread/resume`, `turn/start`, `turn/interrupt`.
- approval request/response handling.
- turn/tool/reasoning/message/token usage parsing.
- progress callback snapshots and terminal result construction.

Local code should remain authoritative for:

- fixture behavior such as `replyText`.
- current config/env compatibility.
- multi-agent workspace discovery/lifecycle already merged in previous phases.
- project/meeting/archive/scheduled business logic.
- testability without requiring a real authenticated Codex install.

### Risks

- Extracting runtime incorrectly can introduce deadlocks in stdout/stderr or pending request cleanup.
- Moving Codex protocol parsing can regress approval/interaction behavior or lose modified-file data.
- A wholesale provider replacement could remove local multi-profile lifecycle and fixture support.
- Tests must cover process crash, timeout, pending server request, cancel, approval, and terminal event ordering.

### Non-Goals

- Do not make generic runtime aware of Codex method names such as `thread/start` or `item/commandExecution/requestApproval`.
- Do not remove legacy Codex endpoints or `send_message/respond/cancel` compatibility in Phase 7.
- Do not migrate frontend Codex primary send path unless the protocol split is verified first.


## Phase 8 Review - Codex Protocol Adapter File Split

Phase 8 follows the Phase 7 runtime extraction. The generic JSONL runtime now lives in `app/provider_app_server.py`, but Codex-specific protocol parsing still lives in `app/providers/codex_bridge.py`. Phase 8 moves Codex protocol behavior into a dedicated adapter file while keeping `codex_bridge.py` as a compatibility shim.

### Technical Decision

Proceed with a focused file-level split:

- Create `app/providers/codex_app_server.py` for Codex-specific protocol behavior.
- Move Codex app-server client, operation state, approval methods, event parsing, and HTTP bridge client where appropriate.
- Keep `app/providers/codex_bridge.py` as a thin compatibility module exporting existing names such as `CodexAppServerClient`, `CodexHttpBridgeClient`, and `get_codex_bridge`.
- Keep `CodexProvider` facade and server/project/meeting consumers unchanged.
- Reuse existing Phase 7 runtime tests and add adapter/shim source or behavior tests.

### Risks

- Moving code can break imports for existing callers.
- A thin shim must preserve public names and behavior exactly.
- Tests must confirm run/SSE, approval, modified files, and provider facade still work after the file split.


## Phase 9 Review - Codex App-Server Run State Parity

Phase 9 follows the Phase 8 Codex adapter file split. The architecture is now close to the reference branch, but local Codex run-state handling still differs from the reference implementation. The next step is to migrate the reference branch's richer run-state aggregation into the Codex protocol adapter while preserving the compatibility entrypoints built in earlier phases.

### Technical Direction

Phase 9 should align these reference behaviors:

- `CodexAppRunState` style aggregation for reply, tools, thinking, approval, token usage, run/thread/session IDs, and terminal status.
- `thread/tokenUsage/updated` handling and brief post-completion drain so late token usage is not lost.
- Provider-level pending approval store, including `pending_approval()` and `respond_approval()` behavior.
- `send_chat_message(...)` as a first-class native app-server path instead of a light facade around `send_message(...)`.
- Stable compatibility for existing `send_message(...)`, `respond(...)`, and `cancel(...)` callers.

### Compatibility Decision

Keep the current layered shape:

- `provider_app_server.py` remains generic runtime.
- `providers/codex_app_server.py` owns Codex protocol and run state.
- `providers/codex_bridge.py` remains compatibility shim.
- `providers/codex.py` remains the public provider facade.
- `provider_execution.py` remains office-facing normalization.

The migration should improve parity without forcing real Codex authentication in tests. Fixture mode, missing binary handling, and local project/meeting behavior remain protected.

### Risks

- Token usage may be emitted after `turn/completed`; tests must cover late-drain behavior.
- Pending approval state can leak if it is not cleared on approval response, cancel, timeout, or client close.
- Switching `send_chat_message` to a first-class native path can accidentally bypass local `send_message` compatibility behavior.
- Project execution depends on stable `modifiedFiles`, `threadId`, `turnId`, `reply`, `status`, and `needsHumanIntervention`.


## Phase 10 Review - Reference Provider Bottom-Layer Alignment

Phase 10 follows the Phase 9 Codex app-server run-state parity work. A fresh comparison against `eliautobot/main` shows that the local implementation has absorbed most user-visible run/SSE and office-facing semantics, but the provider bottom layer is still structurally different from the reference branch:

- Reference `app/providers/codex.py` is a native Codex app-server provider with direct `initialize`, `account/read`, run lifecycle, active client tracking, approval response, token/tool/reasoning parsing, and `codex exec` fallback in one provider file.
- Local Codex is intentionally layered: `CodexProvider` facade, `providers/codex_app_server.py` protocol adapter, `providers/codex_bridge.py` compatibility shim, `provider_app_server.py` generic JSONL runtime, `provider_execution.py` office contract, and ProviderRunBridge/server compatibility.
- Reference `app/providers/claude_code.py` is a native Claude Code provider that relies more directly on `claude auth status --json`, stream-json execution, native agent files, and native main/workspace defaults.
- Local Claude Code still carries compatibility paths such as `reply_text`, legacy-local agent exposure, and a shallower auth/test path.

### Product Direction

The user expectation is to continue merging the reference branch's bottom layer while preserving local project, meeting, archive, scheduled, chat history, Codex interaction, and office execution semantics. Phase 10 should reduce the remaining reference gap in provider-native implementation details, not replace the local office-facing architecture.

### Technical Decision

Proceed with a bottom-layer alignment phase:

- Keep the local layered architecture as the integration boundary:
  - `provider_app_server.py` remains generic runtime.
  - `providers/codex_app_server.py` remains Codex protocol adapter.
  - `providers/codex_bridge.py` remains compatibility shim.
  - `providers/codex.py` remains public facade.
  - `provider_execution.py` remains office-facing result contract.
  - ProviderRunBridge remains shared run/SSE distribution.
- Port additional reference Codex bottom-layer behavior into the adapter/facade instead of copying the reference provider wholesale.
- Port additional reference Claude Code bottom-layer behavior into `ClaudeCodeProvider` while keeping local fixture and graceful-degradation support.
- Keep local frontend/server project and meeting behavior authoritative.

### Reference Merge Targets

Codex targets:

- Reference-style auth/test path using app-server `initialize` and `account/read` when `prefer_app_server` is enabled.
- Closer parity for active run/client lifecycle, cleanup, and stop/interrupt behavior.
- Remaining protocol event names and result metadata not yet covered by `CodexAppRunState`.
- Clearer app-server versus fallback mode reporting.
- Compatibility-preserving fallback for fixture/replyText, disabled provider, missing binary, unauthenticated Codex, and existing bridge URL behavior.

Claude Code targets:

- Reference-style `claude auth status --json` test path when supported, with fallback to version check if needed.
- Tighter stream-json event parsing for assistant output, tools, errors, session IDs, and partial messages.
- Native agent discovery/create/delete metadata parity, including main workspace and native user/project agent files.
- Stop/interrupt active run lifecycle parity.
- Preservation of local `reply_text`, disabled/missing binary behavior, and existing server history routes.

### Risks

- Directly replacing `app/providers/codex.py` could drop local facade methods, fixture modes, bridge URL handling, project result shape, or current tests.
- Directly replacing `app/providers/claude_code.py` could remove local graceful degradation and break testability without a real Claude install.
- Changing run/client lifecycle can regress SSE terminal events, progress history, cancellation, or approval cleanup.
- Auth checks can become too strict and hide configured provider agents in development environments.
- Provider result shape changes can break project execution, meeting blockers, modified-file evidence, or chat history replay.

### Non-Goals

- Do not replace local project/meeting/archive/scheduled implementations.
- Do not remove `provider_app_server.py`, ProviderRunBridge, or `provider_execution.py`.
- Do not remove existing Codex chat/activity/interaction/cancel compatibility endpoints.
- Do not require real authenticated Codex or Claude Code for automated tests.


## Phase 11 Review - Remaining Reference Bottom-Layer Merge Targets

After Phase 10 and the real Chrome MCP E2E pass, a fresh fetch and comparison against `eliautobot/main` still shows mergeable reference behavior. The remaining gap is not that the local implementation lacks Codex/Claude fundamentals; it is that the reference branch still has several bottom-layer conveniences and native-provider API shapes that can be selectively folded into the local layered architecture.

### Current Alignment State

Already aligned or intentionally superseded locally:

- Codex app-server execution exists locally through `providers/codex_app_server.py`, with `CodexAppRunState`, token usage snapshots, approval storage, app-server auth probe, activity events, run completion, and MCP-verified history persistence.
- Claude Code native stream-json execution exists locally with run/SSE/history behavior and MCP-verified real CLI completion.
- `ProviderRunBridge` is the local shared SSE distribution layer for Codex and Claude Code. This should remain authoritative instead of adopting reference per-provider run queues wholesale.
- `provider_execution.py` is the local office-facing contract for `reply`, `status`, `modifiedFiles`, `threadId`, `turnId`, `runId`, `needsHumanIntervention`, tools, thinking, and provider metadata.
- Local project, meeting, archive, scheduled, and UI i18n behavior remain intentionally authoritative.

Remaining reference differences worth merging:

- Reference Codex exposes clearer server/chat approval APIs around pending/respond behavior. Local adapter has pending/respond capability, but server routes and chat UX can be aligned further.
- Reference provider chat uses ephemeral progress history messages such as `codex-progress` and `claude-code-progress`. Local code currently relies more heavily on SSE/activity. The useful part is resumable/reloadable progress history, not the exact monolithic implementation.
- Reference Hermes has a native `/api/hermes/runs` + `/events` + `/stop` shape. Local Hermes has native API client/chat support, but the run/SSE shape is not yet fully unified through `ProviderRunBridge`.
- Reference native model/auth management includes more OpenClaw/Hermes provider/auth APIs. These can be merged selectively into backend helpers, but UI must preserve local i18n and existing model/OAuth behavior.
- Reference Codex monolithic provider still contains small protocol details that should be audited against `providers/codex_app_server.py`, especially token metrics, approval request normalization, and fallback status text.

### Phase 11 Technical Direction

Proceed with selective bottom-layer merge:

- Keep the local layered provider runtime architecture:
  - `provider_app_server.py` remains generic JSONL runtime.
  - `providers/codex_app_server.py` remains Codex protocol adapter.
  - `providers/codex_bridge.py` remains compatibility shim.
  - `providers/codex.py` remains Codex facade and agent lifecycle surface.
  - `providers/claude_code.py` remains Claude Code facade/runtime surface.
  - `provider_execution.py` remains office execution contract.
  - `ProviderRunBridge` remains shared run/SSE distribution.
- Port remaining reference behavior into these local layers instead of replacing files wholesale.
- For UI, merge behavior and state handling, not hardcoded English text. Keep `data-i18n` and local Chinese strings.
- For project/meeting/archive/scheduled logic, only adapt provider call sites if needed; do not replace local state machines.

### Phase 11 Risks

- Adding ephemeral progress history can reintroduce duplicate final messages or stale progress cards if not removed on terminal events.
- Codex approval server routes can conflict with existing `/api/codex/interaction`, `/cancel`, `/compact`, and pending approval store if not normalized carefully.
- Hermes run/SSE integration can break existing CLI fallback or native API approval retry if it bypasses current history and approval queues.
- Native model/auth APIs can leak secrets if safe config redaction is not preserved.
- Reference UI contains many English hardcoded strings and removal of i18n attributes; direct UI replacement would regress localization.

### Phase 11 Non-Goals

- Do not replace local `app/server.py`, `app/chat.js`, `app/game.js`, `app/projects.js`, `app/models.html`, or `app/setup.html` wholesale.
- Do not replace local Codex layered adapter with reference monolithic `app/providers/codex.py`.
- Do not remove MCP-verified Codex history persistence fix from Phase 10.
- Do not make real Codex/Claude/Hermes authentication mandatory for automated tests.


## Phase 12 Review - Provider Progress History Parity

Phase 12 follows the Phase 11 Codex approval API and Hermes run/SSE merge. A fresh comparison against `eliautobot/main` shows that the largest remaining bottom-layer user-experience gap is not raw provider execution; it is recoverable progress history. The reference branch persists temporary progress messages such as `codex-progress`, `claude-code-progress`, and `hermes-progress` so a user can close and reopen chat while a run is active and still see current tools, thinking, token metrics, approvals, and partial output.

### Product Direction

Phase 12 should make provider progress reliable across chat reloads for Codex, Claude Code, and Hermes while preserving the local shared runtime architecture:

- Active provider runs should expose progress through SSE and also persist a single ephemeral progress message in the relevant history store.
- Closing and reopening the chat should restore progress, pending stream text, tools, thinking, token usage, and approval card state where available.
- Terminal completion should remove or supersede the ephemeral progress message and persist exactly one final assistant reply.
- User messages must remain visible after close/reopen, including the Codex `/runs` path fixed in Phase 10.
- The behavior should be generic enough to reuse through `ProviderRunBridge`, while provider-specific history stores remain responsible for their own persistence.

### Technical Decision

Proceed with a scoped progress-history parity phase:

- Add a provider-neutral progress history helper in `app/server.py`, for example `_publish_provider_progress(...)` plus provider-specific adapters for Codex, Claude Code, and Hermes history stores.
- Reuse existing local markers:
  - `codex-progress`
  - `claude-code-progress`
  - `hermes-progress`
- Integrate progress publishing into the existing `ProviderRunBridge` run workers instead of replacing them with the reference branch's per-provider queues.
- Preserve existing terminal reply persistence and duplicate guards.
- Adapt the reference branch's frontend restore logic into local `app/chat.js` without direct wholesale replacement and without losing local i18n/Chinese UI strings.
- Connect Codex approval cards to the Phase 11 `approval/pending` and `approval/respond` routes while preserving legacy `/api/codex/interaction`.

### Reference Merge Targets

- Reference `_publish_codex_progress`, `_publish_claude_code_progress`, `_publish_hermes_api_progress`, and corresponding remove-progress helpers should be adapted into a generic local helper.
- Reference `chat.js` restore logic for `codex-progress`, `claude-code-progress`, and `hermes-progress` should be selectively ported.
- Reference handling for approval pending state inside progress messages should be adapted for local Codex approval cards.

### Risks

- Persisted progress can cause duplicate final assistant replies if cleanup and terminal persistence are not ordered carefully.
- A stale progress message can make completed runs appear still active after reload.
- Frontend restore logic can conflict with current SSE streaming state if `currentRunId`, pending stream text, and tool cards are not reset consistently.
- Codex approval UI can accidentally split between new `approval/respond` routes and legacy `interaction` routes.
- Directly copying reference `chat.js` would regress local i18n and VO style.

### Non-Goals

- Do not merge the full reference `models.html` native model/auth UI in Phase 12.
- Do not implement the remaining OpenClaw/Hermes native model/auth backend helpers in Phase 12.
- Do not replace `ProviderRunBridge`, `JsonlAppServerRuntime`, `provider_execution.py`, or the local provider facades.
- Do not replace local project, meeting, archive, or scheduled state machines.


## Phase 13 Review - Reference Bottom-Layer Parity Follow-Up

After Phase 12 and the follow-up Chrome MCP E2E fix, the reference branch was fetched again:

- Reference: `eliautobot/main` at `eb119493f0c8597187d0f4b6a6054cf5d30c9f05` (`v0.6.30`, `Add native Claude Code provider`).
- Reference history since the base includes `v0.6.20` through `v0.6.30`: native Hermes streaming, native model settings, Codex CLI/app-server support, Codex agent directory support, Codex approvals in chat, Codex streaming/context metrics, native provider settings, and native Claude Code provider.

### Current Parity Assessment

The local branch has already absorbed most provider-runtime bottom-layer behavior, but through a deliberately different architecture:

- Reference branch keeps much of the Codex app-server protocol and run-state behavior inside a monolithic `app/providers/codex.py`.
- Local branch keeps provider-neutral app-server transport in `app/provider_app_server.py`, Codex protocol behavior in `app/providers/codex_app_server.py`, a compatibility shim in `app/providers/codex_bridge.py`, and office-facing execution semantics in `app/provider_execution.py`.
- Reference branch adds Claude Code as a native provider in `app/providers/claude_code.py`; local branch already has a Claude Code provider and server/run/SSE integration, but should be checked for exact native subagent lifecycle parity.
- Reference branch has useful Codex approval chat UX and native-provider settings behavior; local branch has the backend approval APIs and provider settings foundation, but the Codex approval UI still uses legacy `/api/codex/interaction`.

### Merge Safety Boundary

Do not perform a whole-branch or whole-file replacement from `eliautobot/main`. The current compare contains many changes that would remove or regress local product surfaces:

- The reference branch deletes large local `.cosh-docs` requirement archives and many existing tests.
- The reference branch removes local i18n files (`app/i18n.js`, `app/locales/en.json`, `app/locales/zh.json`) relative to the current local worktree.
- The reference branch deletes archive-room and several local meeting/project test files.
- The reference branch rewrites large parts of `app/server.py`, `app/chat.js`, `app/game.js`, `app/projects.js`, `app/models.html`, and `app/setup.html` in ways that conflict with local project/meeting/archive/scheduled behavior.

The correct merge strategy remains selective bottom-layer porting:

- Copy or adapt provider protocol logic, approval mapping, native lifecycle helpers, and settings data shapes from the reference branch.
- Preserve local files that own meetings, projects, archive room, scheduled tasks, i18n, VO styling, and MCP-verified Codex history behavior.
- Keep local `ProviderRunBridge` as the shared SSE/run distributor and keep `provider_execution.py` as the normalized project/meeting execution contract.

### Phase 13 Product Direction

Phase 13 should close the remaining user-visible provider bottom-layer gaps without destabilizing local office workflows:

- Codex approvals should be first-class in chat after reload, using Phase 11 `/api/codex/approval/pending` and `/api/codex/approval/respond` while preserving legacy `/api/codex/interaction` fallback.
- Codex app-server protocol details should be reviewed against reference `v0.6.26` through `v0.6.28` for approval response mapping, tool/item normalization, token/context metrics, and terminal state handling.
- Claude Code native provider should be checked against reference `v0.6.30` for native subagent discovery, create/delete, custom directory handling, auth detection, model/permission configuration, stream-json parsing, and run interruption.
- Native provider settings should selectively absorb reference `v0.6.29` behavior where it improves backend safety or user feedback, while keeping local Chinese/i18n UI and VO modal style.

### Reference Merge Targets

High-value targets to port or verify:

- Codex approval chat flow:
  - approval card rendering for pending requests
  - reload recovery via `approval/pending`
  - approve/cancel submission via `approval/respond`
  - stale/terminal cleanup behavior
  - compatibility with legacy interaction cards
- Codex protocol parity:
  - command/file/permission approval response shape
  - app-server item-to-tool conversion
  - token usage/context metric propagation
  - pending approval store lifecycle and terminal cleanup
  - active run cancellation/interrupt behavior
- Claude Code native parity:
  - `claude auth status --json` and version fallback behavior
  - native user/project subagent file discovery
  - standard and custom agent create/delete paths
  - workspace registry for external/custom agents
  - stream-json partial message/tool/result/token parsing
  - permission mode/model passthrough
- Provider settings parity:
  - safer availability diagnostics for Codex/Claude/Hermes
  - model/auth status display data
  - no secret leaks in safe config endpoints

### Risks

- Approval UI changes can duplicate cards or split state between legacy interaction IDs and new approval IDs.
- Codex progress cleanup recently fixed by MCP can regress if reference progress code is copied directly.
- Claude Code native agent creation can write to real `~/.claude/agents` or workspace paths during tests if fixtures are not isolated.
- Settings UI merge can reintroduce hardcoded English strings or remove local `data-i18n` behavior.
- Whole-file replacement of `server.py`, `chat.js`, or provider modules can break project execution return shape, meeting blockers, `modifiedFiles`, `threadId`, `turnId`, and active operation semantics.

### Non-Goals

- Do not remove local `app/provider_app_server.py`, `app/providers/codex_app_server.py`, `app/providers/codex_bridge.py`, or `app/provider_execution.py`.
- Do not replace local i18n files, archive-room implementation, meeting implementation, project execution state machine, or scheduled-task implementation.
- Do not require real Codex/Claude/Hermes authentication for automated tests.
- Do not archive or mark the broader provider-runtime migration as done in Phase 13; this phase is a focused parity follow-up.


## Phase 13 Completion - Reference Bottom-Layer Parity Follow-Up

Completed at 2026-06-28T19:08:00+08:00.

### Merged Or Adapted

- Codex chat approval UI now polls `/api/codex/approval/pending`, renders reload-safe localized approval cards, and responds through `/api/codex/approval/respond` while preserving legacy `/api/codex/interaction`.
- Codex app-server approval mapping now shares one reference-style response path for command execution, file changes, permissions, and legacy patch/exec approvals.
- Claude Code runtime now routes non-main profiles through their workspace/custom registry and passes `--agent <profile>` where appropriate; stream-json parser now handles JSON argument deltas.
- Provider settings diagnostics remain on the local UI/config surface with safe `/config/providers` payloads and localized approval strings.

### Preserved

- Local `ProviderRunBridge`, `JsonlAppServerRuntime`, `providers/codex_app_server.py`, `providers/codex_bridge.py`, and `provider_execution.py` remain authoritative.
- Local meeting, project, archive, scheduled, i18n, and VO styling surfaces were not whole-file replaced by the reference branch.
- Codex terminal progress cleanup remains preserved: completed run history has user request plus one assistant reply and no `codex-progress`.

### Deferred Or Not Merged

- The reference branch's monolithic Codex provider loop was not merged because it conflicts with the local layered bridge/runtime design.
- Destructive reference changes that delete local docs, tests, archive-room, i18n, project, meeting, or scheduled behavior remain intentionally not merged.
- Chrome MCP browser control was attempted but unavailable because the shared MCP Chrome profile was already locked by an existing browser instance. Equivalent isolated HTTP/SSE/history E2E was run against the same current-code service; artifacts were written to `/tmp/phase13-codex-http-e2e.json` and `/tmp/phase13-claude-settings-http-e2e.json`.

### Verification

- `python3 -m py_compile app/server.py app/providers/hermes.py app/providers/codex_app_server.py app/providers/codex.py app/providers/claude_code.py app/provider_app_server.py app/provider_execution.py`
- `.venv/bin/python tests/test_codex_bridge.py`
- `.venv/bin/python tests/test_codex_server.py`
- `.venv/bin/python tests/test_codex_provider.py`
- `.venv/bin/python tests/test_codex_runs_sse.py`
- `.venv/bin/python tests/test_claude_code_provider.py`
- `.venv/bin/python tests/test_claude_code_server.py`
- `.venv/bin/python tests/test_claude_code_runs_sse.py`
- `.venv/bin/python tests/test_hermes_api_client.py`
- `.venv/bin/python tests/test_hermes_server_native_api.py`
- `.venv/bin/python tests/test_provider_runtime_config.py`
- `.venv/bin/python tests/test_provider_execution_contract.py`
- `.venv/bin/python tests/test_provider_app_server_runtime.py`
- `.venv/bin/python tests/test_project_execution.py`
- `.venv/bin/python tests/test_meeting_request_blocks_task.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase1.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase4.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase6.py`
- `.venv/bin/python tests/test_agent_workspace_project_context.py`
- `node tests/check_codex_approval_ui.mjs`
- `node tests/check_codex_runs_bridge.mjs`
- `node tests/check_claude_code_runs_sse.mjs`
- `node tests/check_provider_runtime_settings_ui.mjs`
- `node tests/check_agent_workspace_project_context_readonly.mjs`
- `node tests/check_project_meeting_records_ui.mjs`
- `node tests/check_sidebar_meeting_direct_detail.mjs`
- `git diff --check`
- Isolated E2E service `http://127.0.0.1:8149`: Codex `/api/codex/runs` + SSE + history passed with no `codex-progress`; Claude Code `/api/claude-code/runs` + SSE + conversation history passed with no `claude-code-progress`; provider settings `/config/providers` exposed Codex/Claude/Hermes diagnostics.


## Phase 14 Review - Final Reference Bottom-Layer Closure

Requested at 2026-06-28T20:50:00+08:00 after another comparison against `eliautobot/main` `eb119493`. This phase is intended to be the final provider-runtime parity phase: absorb every remaining reference bottom-layer behavior that is safe to merge, then explicitly close the rest as intentionally not merged.

### Current Difference Summary

- The local branch has already absorbed most reference provider behavior, but the implementation is intentionally layered instead of reference-monolithic.
- Reference Codex still concentrates app-server protocol, run-state, approval, and CLI fallback code in `app/providers/codex.py`; local Codex behavior is split across `provider_app_server.py`, `providers/codex_app_server.py`, `providers/codex_bridge.py`, `providers/codex.py`, and `provider_execution.py`.
- Reference chat/server code includes useful approval history side effects and provider event reporting, but whole-file merge would overwrite local meeting, project, archive, scheduled, i18n, and VO styling behavior.
- Reference Claude Code provider still has useful facade conventions such as explicit progress callback style and native profile assumptions; local implementation already adds disabled/replyText/fixture behavior needed for tests and local VO operation.

### Final Merge Targets

Phase 14 should do all remaining safe bottom-layer merges in one pass:

- Codex approval respond side effects:
  - Persist an approval result message when `/api/codex/approval/respond` succeeds, with duplicate protection.
  - Emit `gateway_presence.set_provider_event(..., "approval.responded", ...)` with approval/thread/turn metadata.
  - Preserve UI/history cleanup and do not reintroduce stale `codex-progress`.
- Codex app-server protocol polish:
  - Re-audit and align item/tool normalization for command execution, file changes, MCP tool calls, dynamic tools, web search, reasoning, token usage, terminal errors, and final turn status.
  - Preserve local `CodexAppRunState`, `JsonlAppServerRuntime`, and `ProviderRunBridge`; do not move protocol code back into monolithic `providers/codex.py`.
- Claude Code final facade parity:
  - Add any missing reference-compatible progress callback facade behavior without breaking current `/api/claude-code/runs` SSE and history persistence.
  - Verify native profile workspace, `--agent`, model, permission mode, stream-json text/tool/result/usage/error/interrupt behavior as the final closure.
- Provider diagnostics final pass:
  - Fold in remaining safe reference diagnostics for native provider availability/auth/model/permission without leaking secrets or replacing local UI.
- Final closure report:
  - Produce a final merged/adapted/preserved/not-merged map and identify only permanent architectural differences, not pending work.

### Final Non-Merge Boundaries

- Do not whole-merge reference `server.py`, `chat.js`, `game.js`, `projects.js`, `models.html`, or `setup.html`.
- Do not delete or replace local `.cosh-docs`, tests, archive-room, i18n, meeting, project, scheduled, or VO UI behavior.
- Do not remove local provider layering or shared bridge abstractions.
- Do not require real Codex/Claude/Hermes authentication for automated tests; real E2E can run opportunistically, with fixture-backed fallback.

### Expected End State

After Phase 14, there should be no remaining reference bottom-layer behavior that is both safe and worthwhile to merge. Any remaining differences should be documented as permanent local architecture/product boundaries rather than future phases.

## Phase 14 Completion - Final Reference Bottom-Layer Closure

Completed at 2026-06-28T23:49:30+08:00.

### Merged Or Adapted From Reference

- Codex approval response behavior:
  - Added reference-style approval choice normalization.
  - Added approval result message construction with resolved `approved`/`cancelled` status.
  - Persisted exactly one approval result communication history event per approval id and conversation.
  - Emitted `gateway_presence.set_provider_event(..., "approval.responded", ...)` with provider, approval id, thread id, turn id, choice, status, and conversation metadata.
- Claude Code progress facade:
  - Added provider-level `on_progress` callback support for replyText and stream-json execution.
  - Progress snapshots include reply, status, tools, token usage, sessionId/runId, model, error, provider path, and conversation id.
  - Existing `/api/claude-code/runs` SSE/history behavior remains authoritative and non-duplicated.
- Test hardening:
  - Added Codex approval respond history/presence duplicate-protection regression coverage.
  - Added Claude Code progress callback regression coverage.
  - Isolated Codex provider tests from the host's real Codex auth state.

### Re-Audited And Preserved

- Codex app-server item/tool/context normalization already covers command execution, file changes, MCP tool calls, dynamic tool calls, web search, reasoning, token usage, terminal errors, threadId, turnId, modifiedFiles, and final reply through `CodexAppRunState`.
- Local architecture remains layered:
  - `app/provider_app_server.py` owns generic JSONL app-server transport.
  - `app/providers/codex_app_server.py` owns Codex protocol semantics.
  - `app/providers/codex_bridge.py` remains compatibility shim.
  - `app/providers/codex.py` remains office-facing provider facade.
  - `app/provider_execution.py` remains the shared office execution result contract.
  - `ProviderRunBridge` remains the common run/SSE distribution layer.
- Meeting, project, archive, scheduled, i18n, and VO UI surfaces were not replaced by reference whole-file changes.

### Permanent Non-Merge Boundaries

- The reference branch's monolithic Codex provider loop is intentionally not merged because it would undo the local shared bridge/runtime architecture.
- Reference changes that replace local `server.py`, `chat.js`, `game.js`, `projects.js`, `models.html`, or `setup.html` wholesale remain intentionally not merged.
- Reference-side destructive deletion or simplification of local docs, tests, archive-room, meeting/project state machines, scheduled workflows, and localized VO UI remains out of scope.
- Remaining differences after Phase 14 are permanent architecture/product-boundary decisions, not pending future phases.

### Verification Summary

- Provider/runtime tests passed for Codex, Claude Code, Hermes, provider app-server runtime, provider execution contract, and provider runtime config.
- Office workflow regressions passed for project execution, meeting blocker/phase coverage, and source-level project/meeting UI checks.
- Chrome MCP E2E passed against temporary local service `http://127.0.0.1:8152` for Codex run SSE/history and Claude Code run SSE/history.
- `git diff --check` passed.
- Temporary service was stopped after E2E.

## Phase 15 Review - Codex Native App-Server Core Merge

Requested at 2026-06-30T16:18:00+08:00 after the user asked whether the reference branch's complete native Codex app-server implementation can be merged on top of the current local implementation.

### Review Conclusion

This is feasible and should be implemented as a bottom-layer merge, not a whole-file replacement.

The reference branch still has useful native Codex implementation details concentrated in `app/providers/codex.py`, especially `CodexAppServerClient`, app-server stdio JSON-RPC lifecycle handling, approval request/response mapping, `CodexAppRunState`, and tool/reasoning/token usage parsing. The local branch should absorb these semantics into the current layered implementation:

- `app/provider_app_server.py` for generic JSONL app-server transport.
- `app/providers/codex_app_server.py` for Codex app-server protocol semantics.
- `app/providers/codex_bridge.py` as compatibility shim.
- `app/providers/codex.py` as the office-facing provider facade.
- `app/provider_execution.py` for the normalized office execution result contract.
- `ProviderRunBridge` for run/SSE distribution.

### Key Technical Constraints

- Do not overwrite `app/providers/codex.py` with the reference file; that would regress local `codex-local`, fixture, provider facade, meeting/project, and bridge semantics.
- Preserve office-facing return fields relied on by project execution and chat:
  - `reply`
  - `threadId`
  - `turnId`
  - `modifiedFiles`
  - `tools`
  - `thinking`
  - `tokenUsage`
  - `approval`
  - `status`
  - active operation/busy state metadata
- Keep approval compatibility across both local legacy interaction fallback and reference-style app-server approval requests.
- Keep current run/SSE/history cleanup guarantees, including no stale `codex-progress` residue and no duplicate final status cards/messages.
- Keep project/meeting/archive/scheduled behavior local-authoritative.

### Main Risks

- Approval request handling can break if reference app-server server-request semantics are merged without mapping to local approval IDs and pending approval stores.
- Tool parsing can become duplicated or inconsistent if reference run state and local `CodexAppRunState` both emit tool items for the same event.
- Token usage/model/context parsing can regress the chat model bar if usage fields are renamed without compatibility mapping.
- Project execution can regress if result shape changes or `modifiedFiles`, `threadId`, `turnId`, and active operation fields are dropped.
- Real Codex app-server behavior may vary by Codex CLI version, so tests need fixture coverage plus opportunistic real smoke where available.

### Recommended Implementation Strategy

1. Build a reference/local diff map focused on Codex app-server core only.
2. Add fixture tests for currently missing reference event shapes before changing behavior.
3. Merge missing transport lifecycle behavior into `provider_app_server.py` only if it is provider-neutral.
4. Merge missing Codex protocol/run-state behavior into `providers/codex_app_server.py`.
5. Keep `providers/codex.py` as facade and only add compatibility methods if tests prove a gap.
6. Re-run Codex provider/server/run-SSE, provider execution, project execution, meeting blocker, and MCP/browser smoke checks.

### Checklist Status

Phase 15 checklist is drafted and requires user confirmation before implementation.


## Phase 15 Completion - Codex Native App-Server Core Merge

Completed at 2026-06-30T17:05:00+08:00.

### Merged Or Adapted From Reference

- `JsonlAppServerRuntime` now carries reference-style stderr diagnostics and propagates app-server exit context into pending request failures.
- Codex app-server initialization now includes the reference experimental API capability while keeping the local runtime abstraction.
- Codex server-request handling now supports command/file/permissions approval, legacy exec/apply-patch approval, user input, and MCP elicitation through the same local pending interaction store.
- Approval metadata is profile-aware and works through both direct interaction response and reference-style `pending_approval` / `respond_approval`.
- Codex run-state/result handling now preserves reply, tools, thinking, token usage, `threadId`, `turnId`, `sessionId`, `runId`, timeout/cancel/error state, and modified files from `path`, `file`, or `uri` shapes.

### Preserved Boundaries

- The reference monolithic `app/providers/codex.py` was not whole-file merged.
- Local `ProviderRunBridge`, `JsonlAppServerRuntime`, `CodexAppRunState`, `provider_execution`, Codex facade, server APIs, and meeting/project/archive/scheduled workflows remain authoritative.

### Verification Summary

Fixture-backed Codex app-server tests, provider/server/SSE tests, provider execution contract, project execution, meeting blocker, source checks, and `git diff --check` passed. Real Codex/Chrome MCP E2E was not run for this slice; the merged core behavior is covered by the app-server fixture and existing SSE/history regressions.


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

## Phase 16 Review - Final Reference Feature Closure

Requested at 2026-06-30T19:05:00+08:00 after the user clarified that the next phase should be the last merge phase and should bring in all remaining safe details from `eliautobot/main`.

### Review Conclusion

Phase 16 is feasible, but it must be handled as a feature-by-feature closure pass rather than a text merge. The remaining reference diff is still large because the local branch intentionally diverged into a layered VO architecture while the reference branch keeps more provider behavior directly in broad files such as `app/server.py`, `app/chat.js`, and `app/providers/codex.py`.

The correct approach is:

1. Treat the reference branch as the source for missing bottom-layer/provider details.
2. Treat the local branch as authoritative for architecture, VO workflows, and UI style.
3. Produce a final audited diff matrix so future comparisons are explainable and do not create another open-ended phase.

### Current Difference Map

High-priority merge candidates:

- Codex provider details:
  - auth/status diagnostics
  - startup/recovery edge cases
  - approval request metadata and response shapes
  - reasoning/tool/token parsing edge cases
  - compact/resume/cancel/status behavior
  - CLI/app-server availability reporting
- Claude Code provider details:
  - native profile/agent metadata
  - stream-json event edge cases
  - run status, cancellation, and auth diagnostics
  - provider roster/create/delete/edit behavior
  - progress/history compatibility with `ProviderRunBridge`
- Hermes provider details:
  - native API settings/status diagnostics
  - API-vs-CLI fallback behavior
  - run/SSE progress and history metadata
- Server API helpers:
  - provider runtime config exposure
  - model/native provider status endpoints
  - approval and progress-history helper parity
  - discovery/gateway presence event metadata
- UI parity:
  - chat provider progress and completion rendering
  - approval and pending interaction controls
  - native provider setup/model cards
  - localized labels and VO-style dialogs
  - no duplicate completion/status cards
- Config/docs/tests:
  - `.env.example` and `vo-config` provider runtime examples
  - provider adapter docs
  - reference tests that validate merged behavior

Likely intentional boundaries:

- Reference-side wholesale rewrites of `server.py`, `chat.js`, `game.js`, `models.html`, and `setup.html`.
- Reference product semantics that conflict with local meeting/project/archive/scheduled behavior.
- Reference UI copy/style that is not localized or not VO-style.
- Peripheral README/LICENSE/website/docker changes unrelated to provider runtime.
- Reference deletions or simplifications of local docs/tests/state-machine coverage.

### Technical Risks

- A broad server merge could silently break project execution return values, meeting blockers, scheduled task dispatch, or archive-room records.
- A broad chat UI merge could reintroduce issues already fixed locally: disappearing user messages, inconsistent history reload, duplicate completion cards, status-only thinking bubbles, and non-VO dialogs.
- Provider bottom-layer changes can break real Codex app-server runs if run serialization, timeout recovery, or approval response mapping regresses.
- Claude Code and Hermes parity work can accidentally bypass the shared `ProviderRunBridge`, losing progress/history consistency.
- Test-only reference imports can conflict with local fixture paths and environment assumptions.

### Required Safeguards

- Start with a fresh diff inventory and annotate every remaining feature gap before editing.
- Prefer copying/adapting reference functions or parsing logic into local architecture over rewriting from scratch.
- Add tests before or alongside each risky bottom-layer merge.
- Run targeted provider tests after each provider group, then full workflow regressions before E2E.
- Use Chrome MCP for final E2E if available; otherwise use HTTP/SSE plus source-level UI checks and document the limitation.
- Stop any temporary local service and release MCP/Chrome resources after validation.

### Review Decision

No blocking product or technical ambiguity remains. The checklist below should be confirmed before creating the Phase 16 todolist.


## Phase 16 Completion - Final Reference Feature Closure

Completed at 2026-06-30T19:31:55+08:00.

### Final Closure Matrix

| Feature Area | Status | Notes |
| --- | --- | --- |
| Codex native app-server transport | Already covered | Phase 15 merged the safe reference behavior into `JsonlAppServerRuntime` and `app/providers/codex_app_server.py`: JSON-RPC stdio lifecycle, stderr diagnostics, initialize, timeout recovery, compact/resume/cancel, and app-server restart/retry. |
| Codex run state and event parsing | Already covered | `CodexAppRunState` preserves final reply, reasoning/thinking, tools, token usage, `threadId`, `turnId`, `modifiedFiles`, cancellation/error state, and no duplicate final message. |
| Codex approval and pending interactions | Already covered | Reference-style app-server approval requests and legacy interaction fallback both route through the local pending approval store, approval response mapping, duplicate-protected history, and provider presence events. |
| Real Codex CLI behavior | Verified | Final HTTP/SSE E2E executed a real Codex run and persisted history with real `threadId=019f184a-9859-77d1-9641-d0f608effc24`, `turnId=019f184a-af84-7e23-8648-de531b22b804`, and `modifiedFiles=[]`. |
| Claude Code native profile workspace | Merged | Native Claude user-agent discovery now uses the profile workspace as the default workspace, matching the reference branch's native provider semantics. |
| Claude Code VO agent discovery | Adapted | VO office-agent discovery now requires `office-agent.json`, so empty workspace directories do not shadow native Claude agents. This preserves local VO agent semantics while closing the reference metadata gap. |
| Claude Code run/SSE/history | Already covered and verified | `ProviderRunBridge` remains the shared run/SSE layer. Final HTTP/SSE E2E verified Claude Code run lifecycle and history persistence. |
| Hermes native API run/SSE | Merged | Hermes visible thinking is now derived from the completed run result during stream event payload generation, fixing native chat/SSE result handling while preserving CLI fallback. |
| Provider config and status APIs | Already covered | Existing `/config/providers`, setup/model native provider surfaces, and secret-preserving config behavior cover the safe reference metadata requirements. |
| Gateway presence/provider events | Already covered | Provider activity, approval, completion, failure, and stop metadata remain routed through the local gateway presence and progress history implementation. |
| Chat progress/history/approval UI | Already covered | Local fixes for disappearing user messages, close/reopen history reload, stale progress cleanup, duplicate completion cards, status-only thinking filtering, VO dialogs, and localization remain authoritative. |
| Models/setup native provider UI | Already covered | Local native provider settings and diagnostics remain in place and are verified by source/UI checks. |
| Game/project/meeting/archive/scheduled UI | Local boundary | Reference-side broad UI/state-machine changes are intentionally not merged because the local branch contains later VO behavior for meetings, projects, archive room, scheduled tasks, and localized dialogs. |
| Reference whole-file `server.py`, `chat.js`, `game.js`, `models.html`, `setup.html` rewrites | Local boundary | These are not safe to merge textually; safe provider behavior has been copied or adapted into local modules instead. |
| Reference monolithic `app/providers/codex.py` | Local boundary | The local split between `provider_app_server.py`, `codex_app_server.py`, `codex_bridge.py`, `codex.py`, and `provider_execution.py` is intentional and now feature-complete for the safe provider-runtime scope. |

### Phase 16 Code Changes

- `app/providers/claude_code.py`
  - Native user-agent discovery now passes the profile workspace into native agent descriptors.
  - VO office-agent directory discovery now filters on `office-agent.json`.
- `app/server.py`
  - Hermes chat no longer references a result before the result exists.
  - Hermes stream event payloads compute provider-visible thinking from the completed result.
- `tests/test_claude_code_provider.py`
  - Added coverage proving native Claude user agents inherit profile workspace semantics.

### Verification Summary

Passed provider/runtime tests:

- `.venv/bin/python tests/test_claude_code_provider.py`
- `.venv/bin/python tests/test_claude_code_server.py`
- `.venv/bin/python tests/test_claude_code_runs_sse.py`
- `.venv/bin/python tests/test_provider_runtime_config.py`
- `.venv/bin/python tests/test_codex_provider.py`
- `.venv/bin/python tests/test_codex_bridge.py`
- `.venv/bin/python tests/test_hermes_server_native_api.py`
- `.venv/bin/python tests/test_hermes_api_client.py`
- `.venv/bin/python tests/test_provider_app_server_runtime.py`
- `.venv/bin/python tests/test_codex_server.py`
- `.venv/bin/python tests/test_codex_runs_sse.py`
- `.venv/bin/python tests/test_provider_execution_contract.py`

Passed VO workflow regressions:

- `.venv/bin/python tests/test_project_execution.py`
- `.venv/bin/python tests/test_meeting_request_blocks_task.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase1.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase4.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase5.py`
- `.venv/bin/python tests/test_meeting_for_ai_phase6.py`

Passed Node/source checks:

- `node tests/check_codex_runs_bridge.mjs`
- `node tests/check_claude_code_runs_sse.mjs`
- `node tests/check_codex_approval_ui.mjs`
- `node tests/check_provider_runtime_settings_ui.mjs`
- `node tests/check_codex_app_server_split.mjs`
- `node --check app/chat.js`
- `node tests/test_i18n_integrity.js`
- `node tests/check_project_meeting_records_ui.mjs`
- `node tests/check_project_execution_start_payload.mjs`
- `git diff --check`

Final HTTP/SSE E2E passed against temporary latest-code service `http://127.0.0.1:8156`:

- `/health` returned OK.
- `/config/providers` exposed native provider metadata for Hermes, Codex, and Claude Code without secret exposure.
- Claude Code `/api/claude-code/runs` emitted `run.started`, `message.delta`, and `run.completed`; `/api/claude-code/history?agentId=claude-code-local&conversationId=phase16-claude` persisted both the user request and assistant reply with no stale progress message.
- Real Codex `/api/codex/runs` emitted `run.started`, `provider.activity`, and `run.completed`; `/api/codex/history?agentId=codex-local&conversationId=phase16-codex` persisted both the user request and assistant reply `OK_phase16_codex`.
- Temporary service was stopped after verification.

### Known Non-Blocking Noise

- `tests/test_project_execution.py` logged expected OpenClaw gateway failures and one background temporary-directory cleanup message after assertions had passed.
- Meeting phase tests logged expected gateway connection failures in the fixture environment.
- Chrome/CDP browser automation was unavailable for this final slice, so final E2E used HTTP/SSE plus existing Node/source UI checks. Earlier phases already validated the same provider run/SSE/history user flows with Chrome MCP.

### Final Decision

Phase 16 closes the safe reference feature merge. Remaining branch differences are intentional architecture or product-boundary differences, not pending provider-runtime feature gaps.

### Chrome MCP E2E Follow-Up

Completed at 2026-06-30T19:50:20+08:00 after the user explicitly asked whether real MCP end-to-end validation had been run.

- Temporary latest-code service: `http://127.0.0.1:8158`.
- Chrome MCP opened the VO app page and executed browser-context provider requests.
- `/config/providers` returned native provider metadata for Hermes, Codex, and Claude Code without secret exposure.
- Claude Code:
  - Browser-context `/api/claude-code/runs` completed.
  - History for `conversationId=phase16-mcp-claude` persisted exactly `phase16 mcp claude hello` and `Claude MCP OK phase16`.
  - No progress residue remained in history.
- Codex:
  - Browser-context `/api/codex/runs` started `runId=codex-1782820036161-cd8ad5f7`.
  - SSE returned `run.started`, `provider.activity`, keepalives, and `run.completed`.
  - Final output reply was `OK_phase16_mcp_codex_2`.
  - History for `conversationId=phase16-mcp-codex-2` persisted exactly the user request and assistant reply with `threadId=019f185a-e306-7e72-9466-1477e056af99`, `turnId=019f185b-2230-77b3-b624-38ae2cfda6d2`, `modifiedFiles=[]`, and no progress residue.
- Temporary service was stopped after the MCP check.
- Non-blocking browser noise: `/pc-metrics` returned 502 because the metrics backend is not present in this fixture.
