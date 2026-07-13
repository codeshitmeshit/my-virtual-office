## Context

Virtual Office currently supports OpenClaw, Codex, Claude Code, and Hermes through several provider-specific adapters, but provider-neutral orchestration remains concentrated in `app/server.py`. The server owns run reservation, two partially overlapping idempotency maps, `ProviderRunBridge`, background workers, event normalization, SSE replay, conversation mapping, provider progress projection, cancellation, and parts of Hermes/Codex approval handling. `ProviderRunBridge` alone owns a mutable run map, a global monotonic cursor, a 4,000-event deque, provider/run filtering, SSE framing, keepalives, and compatibility queues.

This creates three concrete problems:

- business state, provider protocol logic, and HTTP/SSE transport rules cannot be tested independently;
- Codex, Claude Code, Hermes API/Desktop, and platform paths repeat start/worker/terminal/cancel/idempotency orchestration with subtly different race behavior;
- provider work is difficult to optimize because slow adapter calls and shared mutable registry state are interleaved in one module.

The preceding Project and Meeting changes are archived. This final phase must preserve all public behavior while making provider orchestration the last major backend domain to have a clear service owner. Existing runtime facts are compatibility constraints: event retention is bounded to 4,000 global events, run/idempotency cleanup is approximately ten minutes, provider history/native identifiers have provider-specific storage, active in-process runs are not durable across server restart, and acceptance starts the application only through `start.sh`.

Stakeholders are HTTP/SSE callers, Project Execution, Meeting execution, the office chat UI, Feishu approval callbacks, and maintainers of the four provider adapters.

## Goals / Non-Goals

**Goals:**

- move provider-neutral registry, run lifecycle, event, conversation, approval, cancellation, and cleanup decisions into directly testable services;
- keep one in-process authority for run metadata, event cursors, idempotency reservations, terminal compare-and-set, and retention;
- preserve every route, field, status, event name, replay rule, provider path, native continuation identifier, approval decision, and cancellation result;
- shorten locks so provider processes, native APIs, filesystem history, notifications, and SSE writes execute outside registry critical sections;
- make provider failures isolated and bounded, and prevent late completion/cancellation/approval results from overwriting a newer owner;
- finish the module dependency direction and remove obsolete parallel orchestration after each provider slice passes compatibility regression;
- establish fixed capacity/performance evidence and an isolated release/rollback rehearsal.

**Non-Goals:**

- no provider selection, UI, chat workflow, approval policy, credential/authentication, or model-management redesign;
- no change to OpenClaw, Codex, Claude Code, Hermes CLI/API/Desktop, Gateway, or Feishu protocols;
- no durable recovery of active provider processes after server restart; existing history/native-session recovery remains unchanged;
- no new database, queue, daemon, process boundary, or third-party dependency;
- no attempt to force OpenClaw queued Gateway messaging into background-run/SSE semantics it does not currently expose;
- no frontend performance work and no intentional public compatibility break.

## Decisions

### 1. Separate provider-neutral services from provider adapters and transport

Create service-owned modules under `app/services/`:

- `provider_registry.py`: immutable run snapshots, atomic reservations, idempotency, compare tokens, terminal state, cancellation claims, retention, and bounded event journal;
- `provider_runs.py`: validation-independent run orchestration, adapter launch/cancel ports, worker completion, failure cleanup, and progress coordination;
- `provider_events.py`: canonical event names, allowlisted/bounded payload normalization, tool/reasoning/message/metrics/approval/terminal projection, and replay queries;
- `provider_conversations.py`: provider/Agent/profile/conversation scoping, native continuation mapping, bounded context/history ports, reset, and isolation rules;
- `provider_approvals.py`: trusted approval commands, pending queue ownership, decision idempotency, run/session linkage, resolution, and notification intents;
- `provider_ports.py`: typed provider-neutral commands/results and adapter protocols without importing concrete provider modules.

Concrete implementations in `app/providers/` retain command construction, subprocess/native API/Desktop/Gateway calls, provider authentication handoff, raw stream parsing, native session/run IDs, and provider-specific cancellation. `app/server.py` retains body/query parsing, management/authenticity checks, HTTP status/header selection, SSE framing, and compatibility response assembly.

Alternative considered: move each existing server function into a provider-specific service. Rejected because it preserves duplicated lifecycle and race logic and does not establish a provider-neutral boundary.

Alternative considered: one large `provider_service.py`. Rejected because registry locking, event normalization, conversation storage, and approval trust have different invariants and test surfaces.

### 2. Use one in-process registry authority with compatibility delegates

`ProviderRunRepository` becomes the only owner of active run metadata, global event IDs, retained event records, run/idempotency scopes, terminal versions, cancel claims, and cleanup deadlines. The existing `ProviderRunBridge`, Claude compatibility maps, Codex idempotency helpers, and server delegates temporarily forward to this repository and are deleted after all callers migrate.

The repository returns deep-copy `RunSnapshot`/event data. Mutable dictionaries and queues are not exposed to callers. Legacy per-run queues remain a compatibility projection during migration only; the repository owns their publication and removes the projection in the final slice after static and browser tests prove it unused.

The repository remains in memory. Provider histories, conversation mappings, and native session IDs continue using their existing provider-specific persistence ports. No JSON/Markdown migration or online dual authority is introduced.

Alternative considered: persist active runs/events in a new Store. Rejected because it expands scope, cannot restore native processes after restart, and changes current recovery semantics.

### 3. Reserve idempotency and run ownership atomically before launching adapters

`reserve_start(command)` validates a bounded idempotency key and atomically performs:

1. prune expired idempotency entries;
2. look up `(providerKind, agentId, conversationId, idempotencyKey)`;
3. return the existing active/completed compatible response or allocate a run ID;
4. store an active run with `version`, `generation`, `terminal=false`, `cancelState=none`, and cleanup deadline;
5. commit the idempotency reservation before any worker starts.

Codex's legacy scope is migrated to the same four-part scope while preserving its existing response fields and ten-minute behavior. Commands without an idempotency key preserve current non-deduplicated semantics.

The service launches the adapter only after reservation succeeds. Launch failure enters the same terminal failure compare-and-set path, so a duplicate request never observes a permanently active reservation without a terminal result.

Alternative considered: check idempotency and register in separate operations. Rejected because concurrent requests can launch duplicate provider work.

### 4. Fence asynchronous results and terminal races with run generation/version tokens

Every worker receives `(runId, generation, expectedVersion)`. Event publication verifies run ownership; state-changing progress updates compare generation. `complete`, `fail`, and `cancel_complete` use one terminal compare-and-set:

- the first valid terminal command records the result and terminal event;
- later completion, failure, cancellation, approval continuation, or timeout commands return a stale/idempotent result without mutation;
- cleanup removes a run only when the scheduled generation still owns it.

Cancellation first atomically claims `cancelState=requested` and snapshots adapter/native IDs. The slow adapter stop runs outside the lock, then commits only if the run generation and cancel claim still match. If normal completion wins, cancellation returns the existing terminal outcome and publishes no second terminal event.

Alternative considered: rely on thread ordering and `done` flags. Rejected because stop, completion, timer cleanup, provider callbacks, and approval continuation can race.

### 5. Keep locks short and define lock order

Repository locks protect only bounded dictionary/deque operations and copy/compare/commit. The following never execute while a registry lock is held: provider subprocess/native API/Desktop/Gateway work, history reads/writes, Project/Meeting calls, Feishu notification, adapter cancellation, SSE socket writes, JSON serialization, or thread joins.

Cross-domain order is:

1. reserve/snapshot provider state and release the provider lock;
2. call adapter or Project/Meeting/notification port;
3. re-enter provider compare-and-commit;
4. perform transport output after all domain locks are released.

Provider registry code never acquires Project, Meeting, filesystem-history, or transport locks. Adapter-specific locks may serialize one provider Agent/profile but cannot be held while acquiring the provider repository lock.

### 6. Normalize canonical events before publication; keep SSE transport outside services

Adapters emit `AdapterEvent` values containing provider kind, native type, native IDs, bounded provider-neutral fields, and an optional sanitized diagnostic. `provider_events.py` maps these to the existing public set, including `run.started`, `message.delta`, `reasoning.available`, `tool.started`, `tool.completed`, `tool.failed`, `session.metrics`, `approval.required`, `approval.request`, `run.completed`, `run.failed`, and `run.cancelled`.

The event journal assigns one global monotonic `eventId` under its lock and retains at most the established 4,000 events. It maintains bounded per-run and `(provider, agent, conversation)` indexes so replay does not scan unrelated payloads; eviction removes index entries with the same journal operation. Payload fields and text are allowlisted and bounded before entering the journal.

Services expose `events_after(scope, cursor)` and a condition/wait port. The HTTP adapter alone writes SSE headers, `id/event/data` frames, ten-second heartbeats/keepalives, missing-run responses, and broken-connection handling. Initial provider snapshots, pending approval projection, recovered progress, `Last-Event-ID`, and `after` semantics remain compatible.

Alternative considered: keep HTTP handlers inside `ProviderRunBridge`. Rejected because it reverses the service dependency and makes registry tests require sockets.

### 7. Model provider adapters as capability ports rather than a lowest-common-denominator API

The adapter registry resolves a provider by kind/path and exposes declared capabilities such as background run, streaming events, cancel, conversation continuation, approval continuation, attachments, desktop fallback, and queued Gateway delivery. Services branch on capabilities and preserve stable provider-specific fallback/error behavior.

OpenClaw remains a conversation/queued-delivery adapter unless the existing caller already uses background-run semantics. Hermes API, Desktop, and Gateway Platform remain distinct paths under one Hermes adapter family; fallback order is preserved. Codex app-server/bridge and Claude Code CLI/native session handling remain adapter responsibilities.

Alternative considered: require all adapters to implement every capability. Rejected because synthetic cancellation/streaming/approval behavior would change public semantics.

### 8. Preserve conversation storage and native identifiers behind scoped ports

`ConversationKey` is `(providerKind, agentId, profile, conversationId)`. The service decides scope, continuation/reset commands, bounded context selection, and cross-scope rejection. Adapters/history ports own native thread/session/run IDs and existing files/state formats.

Reads return copies and apply current history limits. Writes compare the conversation key/native mapping captured before slow provider work so a reset or newer continuation cannot be overwritten by a stale worker. Attachments are validated by existing transport/security code before entering the service and are passed to adapters as bounded descriptors, not raw HTTP state.

No history file is renamed or migrated. Old histories and missing conversation IDs retain current recovery/new-conversation behavior.

### 9. Extract approval state with trusted entry context and fenced resolution

`provider_approvals.py` receives `TrustedApprovalContext` after HTTP/Feishu authenticity and actor extraction. Pending approval identity includes provider, Agent/profile, session, run, and approval ID. Queue registration is idempotent; stored DTOs are bounded/redacted and keep current ordering/retention.

Resolution atomically claims an approval with a unique decision token, releases the lock, calls the adapter continuation/deny port, and commits only when the token and linkage still match. Repeated delivery returns the persisted compatible outcome. Unsupported decisions, mismatched linkage, and resolved/missing approvals fail closed. Notification intent persists after approval registration and delivery failure never removes the pending business state.

Alternative considered: keep Feishu card and provider retry logic in one handler. Rejected because transport authenticity and trusted application decisions are separate boundaries.

### 10. Preserve capacity bounds and establish fixed performance gates

Defaults remain compatible unless a failing-before safety test proves a defect:

- global retained event journal: 4,000 events;
- run/idempotency retention: existing approximately ten-minute window;
- event text/provider diagnostic limits: existing per-provider limits, never enlarged by normalization;
- no unbounded worker queue, subscriber buffer, approval queue, history scan, or registry scan is added.

Fixed 1/20/100 concurrent-run and 10/1,000/4,000 event fixtures measure registry update/replay, retained bytes, lock hold duration, adapter launches, terminal events, and idempotency results. Adapter launch and terminal-event counts must not increase. Provider calls, notification calls, Project/Meeting calls, and history writes are primary gates; median/p95 are secondary evidence. The final implementation must eliminate whole-journal scans from run-scoped and conversation-scoped replay or document an equivalent bounded cost.

### 11. Use compatibility-first provider slices and one owner per migrated command

Implementation order is:

1. inventory every run/event/conversation/approval/cancel reader and writer; freeze characterization and performance baselines;
2. extract repository/event journal beneath `ProviderRunBridge` while keeping its public delegates;
3. extract shared run/idempotency/terminal/cancel coordinator and migrate Claude Code and Codex;
4. migrate Hermes API/Desktop/Platform run and approval orchestration;
5. migrate provider conversation/history/native-ID coordination, including OpenClaw boundaries;
6. migrate provider-level SSE snapshot/replay queries and leave framing in transport;
7. remove obsolete registries, queues, helpers, and compatibility delegates; enforce static dependency checks;
8. run complete regression, `start.sh` acceptance, capacity rehearsal, and rollback rehearsal.

At no time may old and new coordinators both launch the same provider command. Each slice switches one caller set to one service owner and keeps rollback as a code revert with unchanged data formats.

### 12. Add service-boundary, observability, and release evidence

Static tests forbid provider services from importing `server.py`, `OfficeHandler`, HTTP/SSE handler types, or concrete provider modules. They also forbid adapters from mutating repository internals. Compatibility delegates are counted and must shrink to the explicitly documented transport-only set.

Diagnostics use bounded fields: operation, provider kind/path, run/conversation ID digest, state, event name/count, idempotency result, stale token, duration, retained counts/bytes, cancellation/approval outcome, and error category. Credentials, raw provider payloads, unrestricted prompts/transcripts, and absolute paths are excluded.

Release evidence includes scenario traceability, full Python/JavaScript/static/provider/browser regression, fixed performance artifacts, startup through `start.sh`, provider-by-provider smoke tests, SSE reconnect, approval/cancel races, and an isolated rollback rehearsal. External provider/Feishu effects are recorded and reconciled rather than assumed reversible.

## Risks / Trade-offs

- **[Compatibility drift across four provider paths]** → Freeze route/JSON/SSE/native-ID fixtures before extraction; migrate one provider slice at a time and compare exact response/event traces.
- **[One common abstraction erases provider capabilities]** → Use capability ports and provider-path adapters; do not synthesize unsupported behavior.
- **[Duplicate provider work during idempotency migration]** → Reserve scope and run ownership atomically before launching; never dual-run old/new coordinators.
- **[Late completion overwrites cancel or approval continuation]** → Use generation/version and decision/cancel claim tokens for every asynchronous commit.
- **[Event replay becomes slower or loses events]** → Preserve global monotonic IDs/4,000-event bound and maintain eviction-consistent scope indexes; gate fixed replay fixtures.
- **[Registry lock blocks slow provider work or SSE clients]** → Copy/snapshot under lock; adapter calls, waits, serialization, and socket writes stay outside it; measure lock hold time.
- **[In-memory state loss is mistaken for new recovery support]** → Explicitly retain current restart semantics; only persisted histories/native mappings recover.
- **[Approval extraction weakens trust boundary]** → Accept only trusted adapter context, validate full linkage, fence resolution, and keep signature/card parsing in transport adapters.
- **[Sensitive raw provider data enters common events]** → Allowlist/bound/redact before journal persistence or notification; add credential/path/prompt canaries for every adapter.
- **[Timer cleanup removes a newer run generation]** → Cleanup compares run generation and terminal deadline before deletion.
- **[Rollback after external provider/Feishu effects]** → Stop new mutations, preserve run/event/approval diagnostics, reconcile external effects, and restore prior code without transforming history files.
- **[Final cleanup removes a still-used delegate]** → Generate call inventory, add static/runtime compatibility tests, and delete only after zero live callers plus complete regression.

## Migration Plan

1. Record baseline call inventory, exact provider route/event fixtures, active registry/idempotency/approval/history writers, and fixed performance results.
2. Land repository/event services behind existing delegates with no caller behavior change; run all provider/SSE tests.
3. Migrate one provider/coordinator slice at a time. After each slice, run focused compatibility, concurrency, cancellation, approval, security, and performance tests; complete a large-task CR before continuing.
4. Keep storage/history formats unchanged. Do not copy or dual-write provider history; no data migration script is required.
5. Remove old authority only after the last caller migrates. Static checks must prove one owner and no reverse dependency.
6. Start one isolated candidate only through `start.sh`; exercise Codex, Claude Code, Hermes, OpenClaw, conversation continuation, SSE reconnect, approval and cancellation with fake/local adapters where real credentials are unavailable.
7. For release, stop new runs and wait for or explicitly cancel active work. Record active runs, pending approvals, idempotency scopes, event counts/cursors, conversation/native IDs, and external effects.
8. Rollback by stopping the candidate, restoring prior code/config (history files are unchanged), restarting through `start.sh`, and validating conversation/history visibility and provider availability. Reconcile non-reversible Provider/Feishu effects from recorded run and approval evidence.

## Open Questions

No blocking product decision remains. During task planning, the inventory must confirm the exact transport-only delegate list, current approval queue bounds, and every provider-specific event alias before deletion. These are implementation evidence items, not permission to change behavior.
