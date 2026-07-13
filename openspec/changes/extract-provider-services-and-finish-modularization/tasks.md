## 1. Provider baseline and ownership inventory

- [x] 1.1 Inventory every OpenClaw, Codex, Claude Code, Hermes API/Desktop/Platform run, event, conversation, native-ID, approval, cancellation, idempotency, retention, progress, history, HTTP, SSE, Project Execution, Meeting, Feishu, and compatibility reader/writer; generate a checked-in caller/writer map, Provider path capability matrix, event-alias manifest, approval-queue bound report, and final transport-only delegate candidate list.
- [x] 1.2 Add exact characterization fixtures for route/request/response/status behavior, run start/poll/terminal/failure/timeout, conversation continuation/reset/isolation, approval registration/decision/replay, cancel-vs-complete, SSE `Last-Event-ID`/`after`/heartbeat/recovery, unavailable providers, old histories/native mappings, and concurrent scopes; capture fixed 1/20/100 run plus 10/1,000/4,000 event performance baselines and call/lock/retention counts.
- [x] 1.3 Run the complete baseline-focused Python/JavaScript/static manifest, verify generated artifacts reproduce exactly, and perform one whole-section CR covering correctness, security, consistency, test validity, and baseline sufficiency before Section 2.

## 2. Unified run repository and event journal

- [x] 2.1 Implement `provider_registry.py` with immutable/deep-copy snapshots, one in-process run/idempotency authority, atomic start reservation, generation/version tokens, terminal/cancel/cleanup compare-and-set, existing ten-minute retention, bounded pruning, and concurrency tests for duplicate scopes, independent scopes, launch failure, late completion, cancel races, and stale cleanup.
- [x] 2.2 Implement `provider_events.py` with allowlisted/bounded canonical events, global monotonic IDs, the existing 4,000-event journal bound, eviction-consistent run/conversation indexes, replay/wait queries, terminal dedupe, malformed/oversized/sensitive payload handling, and fixed 0/1/4,000/4,001 event tests without HTTP/SSE types.
- [x] 2.3 Move `ProviderRunBridge`, Claude compatibility maps/queues, Codex/provider idempotency helpers, and current event publishers behind repository/event delegates without dual authority; run all run-registry/SSE/provider tests and performance comparisons, then complete one whole-section CR and resolve every blocking finding before Section 3.

## 3. Shared run coordinator, Codex, and Claude Code

- [x] 3.1 Implement `provider_ports.py` and `provider_runs.py` with capability-aware adapter resolution, atomic reserve-before-launch, short-lock worker orchestration, normalized progress, launch/failure/timeout cleanup, terminal fencing, cooperative/provider cancellation, idempotent duplicate responses, bounded diagnostics, and fake-adapter unit/concurrency tests.
- [x] 3.2 Migrate Codex app-server/bridge run start, progress/tool/reasoning/metrics events, conversation/native thread linkage, completion, idempotency, polling, SSE query, approval hooks, cancellation, and retention to the shared coordinator while preserving exact response/event/provider-path behavior and old history/session compatibility.
- [x] 3.3 Migrate Claude Code CLI/native run start, progress/tool/reasoning/metrics events, session/conversation linkage, completion, idempotency, polling, SSE query, interruption/cancellation, history cleanup, and retention to the shared coordinator while preserving exact behavior and keeping concrete CLI parsing inside the adapter.
- [x] 3.4 Run the Codex/Claude/provider-run/SSE/Project Execution/Meeting compatibility and fixed performance suites, exercise same/different-scope concurrency and cancel-vs-complete, and complete one whole-section CR before Section 4.

## 4. Hermes runs, paths, approvals, and cancellation

- [x] 4.1 Migrate Hermes API run lifecycle, Desktop fallback/active-run projection, Gateway Platform capability routing, native session/run linkage, tool/reasoning/message events, presence/progress projection, completion/failure/timeout, idempotency, retention, and cancellation to the shared coordinator without changing path precedence or fallback/error semantics.
- [x] 4.2 Implement `provider_approvals.py` with `TrustedApprovalContext`, bounded/redacted pending records, queue ordering/bounds, provider-Agent-profile-session-run linkage, idempotent registration, decision token fencing, supported once/session/always/deny semantics, retry/replay outcomes, Feishu notification intents, and failure/crash/concurrent-delivery tests.
- [x] 4.3 Migrate Hermes API/CLI/Desktop/Feishu approval and cancellation callers to the services, keeping authenticity/card parsing and native continuation in adapters; verify forged/stale/cross-run/repeated decisions, notification degradation, approval-vs-cancel/complete races, Provider failure isolation, and old pending-record compatibility.
- [x] 4.4 Run all Hermes native/API/Desktop/Platform/approval/Feishu/provider-stream tests and performance checks, then complete one whole-section CR and resolve findings before Section 5.

## 5. Conversation continuity and OpenClaw boundaries

- [x] 5.1 Implement `provider_conversations.py` with `(providerKind, agentId, profile, conversationId)` scoping, provider history/native-ID ports, bounded context selection, validated attachment descriptors, continuation/reset compare tokens, copy-on-read, stale-write rejection, and tests for missing/foreign IDs, concurrent reset/continuation, history failure, old records, and cross-conversation isolation.
- [x] 5.2 Migrate Codex, Claude Code, and Hermes conversation/history/session mapping callers to the service without renaming or dual-writing existing history/state files; preserve provider-native recovery and exact chat payloads.
- [x] 5.3 Migrate OpenClaw conversation/queued Gateway delivery ownership to the capability boundary without inventing background-run/SSE semantics; preserve Gateway session candidates, history visibility, delivery errors, authentication handoff, and Project/Meeting caller behavior.
- [x] 5.4 Run the complete conversation/history/OpenClaw/Codex/Claude/Hermes/attachment/security compatibility suite, prove unrelated conversations and providers remain parallel, and complete one whole-section CR before Section 6.

## 6. SSE transport separation, recovery, and failure isolation

- [x] 6.1 Replace service-side HTTP/SSE framing with transport adapters consuming repository snapshot/replay/wait APIs; preserve missing-run responses, headers, `id/event/data` frames, `Last-Event-ID`, `after`, initial provider snapshot, pending approval, recovered history/progress, ten-second heartbeat/keepalive, terminal replay, disconnect handling, and frontend event contracts.
- [x] 6.2 Add restart/recovery and isolation coverage proving active in-memory runs retain existing non-durable semantics, persisted histories/native IDs remain visible, late callbacks cannot recreate expired runs, malformed/unavailable/timeout behavior affects only the targeted provider, and sensitive payload canaries never enter events, approvals, notifications, diagnostics, or logs.
- [x] 6.3 Run HTTP/SSE/WebSocket/browser-static/provider recovery/security/load tests, compare replay scans and lock duration to baseline, and complete one whole-section CR before Section 7.

## 7. Final dependency cleanup, performance, and full regression

- [x] 7.1 Remove obsolete ProviderRunBridge business logic, parallel registries/idempotency maps, legacy queues, provider orchestration helpers, and unused delegates after caller inventory reaches zero; add static checks forbidding service imports of `server.py`/HTTP/SSE/concrete adapters, adapter mutation of repository internals, direct second authorities, and non-transport logic in the approved delegate whitelist.
- [x] 7.2 Re-run fixed 1/20/100 run and 10/1,000/4,000 event fixtures; document adapter launches, terminal events, idempotency results, provider/notification/Project/Meeting/history calls, replay scans, retained bytes, lock-held duration, median and p95, and prove no call-count increase, unbounded scan, duplicate terminal, or unrelated-provider serialization.
- [x] 7.3 Run the complete Python, standalone/script Python, JavaScript, static, Provider, Project Execution, Meeting, Feishu, approval, cancellation, conversation, persistence, SSE/WebSocket, workflow, security, concurrency, performance, OpenSpec strict, compile, and diff regression; document scenario traceability, intentional defect corrections, compatibility exceptions, warnings, and manual-only coverage.
- [x] 7.4 Perform one final whole-section CR across the complete implementation, fix all confirmed correctness/security/data/consistency findings, re-run affected and full regression, and produce a clean commit-ready candidate before release readiness.

## 8. Documentation, start.sh acceptance, and release rehearsal

- [x] 8.1 Update architecture/service-boundary/operator documentation for adapter capabilities, run repository/event authority, idempotency scope, generation/terminal/cancel/approval tokens, conversation/native-ID storage, retention/capacity, SSE replay, sensitive data, observability, failure isolation, and the final transport-only delegate list.
- [x] 8.2 Start the application only through `start.sh` and complete candidate acceptance for Provider availability/isolation, Codex/Claude/Hermes/OpenClaw happy and failure paths, conversation continuation/reset, SSE reconnect/replay/heartbeat/terminal, approval/replay/notification degradation, cancellation races, management authorization, Project Execution, and Meeting provider integration; use fake/local adapters where external credentials are unavailable and record manual-only gaps.
- [x] 8.3 Execute an isolated release/rollback rehearsal: stop new runs, drain or cancel active work, record run/approval/idempotency/event/conversation/native-ID/history state and external effects, start exactly one candidate through `start.sh`, exercise every available Provider path, stop and restore prior code/config, restart through `start.sh`, verify unchanged histories/native mappings/API/event behavior, and document Provider/Feishu reconciliation.
- [x] 8.4 Run release-focused regression and one whole-section CR of documentation/evidence/rollback safety, resolve findings, strictly validate OpenSpec, and present complete test and rehearsal evidence for final user confirmation.
