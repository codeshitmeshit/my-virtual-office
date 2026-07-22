## Context

Virtual Office currently has two conversation projections over the same Provider executions:

- Standard chat uses `GET /api/chat/history` for paged durable history, `ProviderEventJournal` SSE for live events, and `ChatHistoryStore` for client reconciliation. Provider-history parsing, stable identity, merge, paging, and source caching still live in `app/server.py`; live events are interpreted again in `app/chat.js`.
- Project Execution resolves an active task/attempt in `_handle_workflow_chat()`, then uses `_wf_get_task_session_messages()`. That function has independent Hermes and Codex branches, a second Codex reasoning accumulator, and a hand-written OpenClaw JSONL parser. It has no Claude Code branch, so a Claude Code attempt can fall through to an unrelated OpenClaw session lookup.

This creates multiple authorities for message identity, reasoning visibility, lifecycle status, tool projection, ordering, and recovery. Known drift includes Claude Code project history absence, completed Hermes reasoning appearing live, incomplete OpenClaw structured-content handling, and duplicated Codex `replace`/`boundary` aggregation.

The repository already has focused Provider services (`provider_conversations.py`, `provider_events.py`, `provider_runs.py`) and a provider-neutral paged history contract, but no service owns the canonical display timeline. The new owner must fit those boundaries, must not import `server.py`, and must leave `server.py` as composition/transport compatibility code. Existing Provider files, communication JSONL, Codex activity fast path, Provider event journal, public routes, and frontend presentation remain in place.

The change is a read/projection migration. It adds no external dependency, database, durable write authority, authentication path, or Provider invocation. Transient events remain recoverable only to the extent guaranteed by their existing Provider contract.

## Goals / Non-Goals

**Goals:**

- Establish one canonical timeline model and one normalization/reconciliation implementation for Codex, Claude Code, Hermes, and OpenClaw.
- Make standard chat and Project Execution chat consume the same canonical semantics for overlapping scope and time windows.
- Preserve strict Provider, Agent/profile, conversation, project, task, attempt, and review isolation.
- Normalize durable history and eligible live progress without duplicating, reordering, or fabricating activity.
- Preserve existing route paths and compatible response fields while removing duplicate Provider interpretation after migration.
- Correct reproducible in-scope defects with failing-before regression coverage.
- Keep reads bounded, content-safe, independently testable, and failure-isolated.

**Non-Goals:**

- Unify chat and project visual components, styling, truncation presentation, or interaction design.
- Make Providers expose equal reasoning detail or persist transient data they do not currently guarantee.
- Change Provider execution, approval, cancellation, credentials, native history formats, or conversation continuation policy.
- Add durable indexing, search, a new message store, or cross-process cache coherence.
- Repair unrelated defects discovered outside timeline selection, normalization, reconciliation, recovery, or compatibility delegates.

## Decisions

### 1. Add a focused, read-only conversation timeline service

Create `app/services/conversation_timeline.py` as the sole owner of canonical timeline normalization, status mapping, identity, reasoning accumulation, tool transitions, merge/deduplication, ordering, and paging. The module will expose typed application inputs and outputs such as:

- `TimelineScope(provider_kind, agent_id, profile, conversation_id, session_key)`
- `TimelineQuery(limit, before, include_live)`
- `TimelineItem` represented as a bounded public dictionary at compatibility boundaries
- `TimelinePage(messages, next_cursor, has_more, session)`
- `ConversationTimelineService.read(scope, query, sources)`

The service is stateless with respect to durable conversations. It accepts explicit source ports/callables and a clock/hash policy; it does not read global server state, resolve HTTP queries, open arbitrary paths supplied by a client, or mutate Provider history.

`ProviderConversationService` remains the authority for conversation state mutation and native continuation IDs. `ProviderEventJournal` remains the bounded live-event authority. The timeline service is a read model over those authorities, not a replacement coordinator.

Alternatives considered:

- Reusing `_handle_chat_history_page()` directly from Project Execution was rejected because it keeps business rules in `server.py`, does not fully own live projection, and cannot express project attempt ownership safely.
- Extending `ProviderConversationService` was rejected because mixing read projection with conversation mutation would broaden its responsibility and lock scope.
- A new durable timeline store was rejected because it introduces dual-write consistency and migration problems without being required for bounded local histories.

### 2. Separate scope resolution from timeline projection

Create `app/services/project_workflow_chat.py` to resolve the selected project's active execution scope from injected project/workflow readers. It returns either a validated `ProjectTimelineScope` or the existing compatible empty/not-found result. It owns project/task/attempt/review selection rules but does not parse Provider history.

The HTTP handlers become thin delegates:

```text
GET /api/chat/history
  -> validate public chat scope
  -> ConversationTimelineService.read(...)
  -> existing paged response

GET /api/projects/{id}/workflow/chat
  -> ProjectWorkflowChatService.resolve_scope(...)
  -> ConversationTimelineService.read(...)
  -> existing workflow response adapter
```

The project adapter retains `agent`, `taskId`, `phase`, and `sessionActive`. Canonical `status` is mapped to the legacy `reasoningStatus` field where the current project client expects it; additive `id`, `providerKind`, `conversationId`, and canonical `status` fields may be returned without changing the existing renderer contract.

Alternatives considered:

- Passing a project ID into the timeline service was rejected because it would couple provider-neutral projection to project persistence.
- Keeping project scope resolution and Provider parsing in one service was rejected because it recreates the current mixed responsibility in a new file.

### 3. Use injected Provider source readers with one canonical raw-record boundary

The composition root constructs a `TimelineSources` bundle from existing trusted readers:

- bounded Provider history for Codex, Hermes, and Claude Code;
- exact OpenClaw session history resolved from an internal session key;
- office communication history filtered by Agent and conversation;
- Codex activity/fast-path records and Provider event-journal progress scoped to the same conversation;
- session metrics and active-session state.

Provider source readers may translate native field aliases into a bounded raw-record envelope, but they do not decide final visible identity, status, ordering, or reasoning aggregation. OpenClaw structured content uses the same content-block parser for both surfaces. Claude Code uses its conversation-scoped history reader and never enters the OpenClaw reader. Hermes and Claude Code placeholder filtering is applied by the same visibility policy used for live and durable records.

The ports return snapshots; they do not trigger Provider work or write history. A malformed or unavailable source produces an explicitly classified empty/partial/error contribution according to the existing endpoint contract, without broadening scope or affecting another Provider.

Alternatives considered:

- One large `if provider_kind` block inside the service was rejected because it would make the supposedly provider-neutral owner depend on native formats.
- Letting each consumer choose source combinations was rejected because source selection is part of the consistency guarantee.

### 4. Define one canonical item and lifecycle contract

The public canonical item preserves the existing normalized history fields:

```json
{
  "id": "stable-within-scope",
  "version": "render-affecting-version",
  "providerKind": "claude-code",
  "conversationId": "attempt-id",
  "providerRunId": "native-or-vo-run-id",
  "itemKind": "message|reasoning|tool|approval|run",
  "role": "assistant",
  "text": "",
  "thinking": "provider supplied text",
  "tools": [],
  "status": "queued|running|done|failed|cancelled",
  "epochMs": 0,
  "sequence": 0,
  "source": "claude-code"
}
```

Compatibility responses may embed reasoning and tools in an assistant message, but they are produced from the same canonical item state. The service maps Provider aliases into the five lifecycle states; UI-specific labels such as “实时” and “完成” are not part of the service.

Identity preference order is:

1. trusted source message/event/tool/approval ID scoped by Provider, Agent, and conversation;
2. run/turn/item identity for live activity;
3. a deterministic fallback fingerprint over scope, item kind, role/sender, source, normalized timestamp, and bounded content signature, plus stable source ordinal only when unavoidable.

Ordering preference is Provider sequence/lifecycle order, then normalized timestamp, item-kind rank for related records, and stable ID. Timestamp alone is never allowed to reverse known Provider order. Merge prefers the record with stronger identity and later lifecycle version; office communication attribution may enrich a Provider record but cannot attach it to another conversation.

Reasoning state tracks event IDs, accumulated text, pending boundary, lifecycle, and source identity. `replace`, `boundary`, and duplicate semantics move out of `_codex_reasoning_events_to_chat_messages()` and `codex-reasoning.js` into the service. Status-only placeholders are removed by one visibility policy. Empty reasoning remains empty; a run-status item may still communicate truthful progress.

### 5. Project live and durable data through the same service

`ConversationTimelineService.read()` merges a bounded durable snapshot with eligible scoped live records. A live record and its later durable form settle the same canonical item when they share source/run/item identity. The service does not persist transient records or attempt to reconstruct them after failure.

The Provider SSE route keeps all current event names and payload fields. During migration it adds a bounded `timelineItem` field produced by the same projector. `ChatHistoryStore` consumes that canonical item for model reconciliation; Provider-specific handlers may continue to control visual run/tool/approval presentation but must not independently derive history identity, status, reasoning text, or merge order. After parity coverage is complete, the old `mergeLiveHistoryRecord()` mappings and Codex reasoning accumulator are removed.

Project Execution continues its current bounded polling contract but receives service-projected items, including eligible live activity. It does not need a second event accumulator. Repeated polling is read-only and idempotent.

Alternatives considered:

- Making Project Execution open a second SSE connection was rejected because UI transport is not required for semantic consistency and would expand frontend scope.
- Keeping client-side canonicalization as a fallback permanently was rejected because it would retain two authorities. A temporary compatibility fallback is allowed only during migration and is removed before completion.

### 6. Preserve bounds, caches, and failure isolation

The service preserves the current response maximum of 50 items per page, the existing maximum of 1,000 bounded source candidates, the 32-entry/64 MiB read-through source cache, and bounded Provider event/activity retention. It normalizes only candidates needed for the requested window plus overlap required for deduplication and live settlement. No Provider invocation or history write occurs on a timeline read.

Existing cache locking remains limited to cache lookup/update. File reads, normalization, hashing, merging, and JSON serialization occur outside Provider registry, project store, and event-journal locks. The service returns copied public data so one consumer cannot mutate cached state observed by another.

Performance acceptance records source candidate count, normalized item count, dedupe count, cache hit/miss, elapsed time, and response bytes for fixed small/medium/large fixtures. Diagnostics contain scope digests and counts only; they exclude message, reasoning, tool arguments/results, credentials, raw Provider payloads, and unrestricted paths. Repeated malformed-source diagnostics are rate limited.

### 7. Keep compatibility and security at transport boundaries

No route, method, required request field, status code, SSE event name, cursor format, Provider invocation contract, or stored history schema is intentionally removed. The standard history DTO remains backward compatible. The project workflow response retains its existing envelope and message fields.

Scope inputs are validated before source selection. Client-controlled values never become filesystem paths. OpenClaw session files are resolved only through existing trusted session metadata. Timeline records pass existing payload bounding/redaction before public serialization; native transcripts and secrets are not logged for parity analysis.

No new authorization is introduced. Existing route trust and project access rules remain authoritative, and the timeline service receives only already-authorized application scopes.

### 8. Treat confirmed defects as explicit compatibility changes

Before migration, freeze characterization fixtures for current correct behavior and failing-before fixtures for known defects. A defect is fixed in this change only if it is reproducible, belongs to the migrated timeline slice, and its expected result follows the confirmed specification. Each fix is named in tests and verification evidence.

The initial expected corrections are:

- Claude Code Project Execution history selects Claude Code conversation history instead of OpenClaw session storage.
- completed Hermes reasoning normalizes to a terminal state;
- OpenClaw supported structured blocks are parsed once for both consumers;
- Codex reasoning replacement, boundary, filtering, and terminal settlement have one owner.

An ambiguous issue or product-policy change stops implementation and returns to the specification gate.

## Risks / Trade-offs

- **[Identity collision or wrong live/durable match]** → Prefer trusted native IDs, include full scope in every key, use conservative fallback matching, and add collision/overlap fixtures. Never merge solely on text.
- **[Event sequence differs from timestamp order]** → Preserve Provider sequence and lifecycle relations ahead of timestamps; test equal/missing timestamp cases.
- **[Transient activity disappears after restart]** → Preserve existing durability semantics and never claim transient recovery; verify durable terminal/message survival independently.
- **[A shared service becomes another large conditional module]** → Keep Provider-native parsing behind injected source readers and split project scope resolution into its own module; enforce static dependency checks.
- **[Standard chat live behavior regresses while client mappings are removed]** → Add `timelineItem` additively, run old/new canonical projection comparisons, migrate one Provider at a time, and remove fallback only after parity fixtures pass.
- **[Project polling becomes slower by merging more sources]** → Maintain current bounds/cache, avoid full-file scans, record candidate counts and latency, and reject any slice that exceeds the frozen baseline without justified evidence.
- **[Malformed history from one Provider fails the shared endpoint]** → Classify source failures, return only contract-compatible partial/empty/error results, and isolate readers by scope/provider.
- **[Sensitive native data enters the canonical DTO or diagnostics]** → Reuse allowlisting, bounding, and redaction before serialization; test secrets, absolute paths, oversized values, and malformed nested payloads.
- **[Temporary dual projections drift during migration]** → Use shadow comparison only for read-only outputs, never dual-write or dual-launch Provider work, and set an explicit task to delete the legacy project/Codex/client canonicalizers.
- **[Rollback after response additions]** → Additive fields are ignored by old clients; no storage migration exists. Before legacy removal, rollback selects the prior read delegate. After final cleanup, rollback is a code rollback with unchanged history files.

## Migration Plan

1. Freeze current route/DTO/cursor/SSE fixtures and four-Provider source fixtures. Add failing-before tests for the confirmed Claude Code, Hermes, OpenClaw, and Codex defects.
2. Add the pure timeline model/service and source-port contract in new focused modules. Verify normalization, status, identity, ordering, dedupe, paging, bounds, sanitization, and failure isolation without starting the HTTP server.
3. Extract existing standard-history normalization and OpenClaw structured-content parsing behind injected source readers. Delegate `GET /api/chat/history` to the service while preserving exact compatible output.
4. Add project execution scope resolution and delegate workflow chat to the same service. Switch Provider slices individually: Claude Code, Hermes, OpenClaw, then Codex activity/reasoning.
5. Add canonical `timelineItem` projection to existing Provider SSE payloads and migrate `ChatHistoryStore` reconciliation to consume it. Keep visual Provider handlers, but remove their canonical history/status/reasoning decisions.
6. Run shadow comparisons using only IDs, versions, statuses, counts, order signatures, and content digests; do not log content. Investigate every unexplained mismatch.
7. Remove `_wf_get_task_session_messages()` Provider parsing, `_codex_reasoning_events_to_chat_messages()`, duplicated OpenClaw parsing, client `mergeLiveHistoryRecord()` mappings, and client Codex reasoning aggregation after all parity and compatibility gates pass.
8. Run focused and full regression, performance comparison, static dependency checks, malformed/sensitive payload tests, restart recovery, and rollback rehearsal. No durable migration or backfill is required.

Rollback during steps 3–6 switches the affected read delegate back to the characterized legacy path; because projection is read-only, no compensation is required. A failed Provider slice rolls back independently. Once step 7 removes the temporary delegates, rollback uses the prior application revision; existing Provider histories, communication logs, and session metadata remain readable.

## Open Questions

No blocking design questions remain. Exact baseline thresholds, test file partitioning, and Provider migration task boundaries will be derived from measured characterization and recorded in `tasks.md`; they must not weaken the confirmed behavioral requirements.
