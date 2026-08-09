## Why

Warm, continued Codex chats can delay visible Agent activity because Virtual Office performs avoidable synchronous work, persistence, and cross-conversation serialization around the Provider event path. The product needs a measurable Codex-only fast path that makes activity visible promptly without weakening durable chat, approval, or terminal-state guarantees.

## What Changes

- Establish explicit warm-chat latency SLOs: working feedback p95 at or below 200 ms and the first native Agent event p95 at or below 1 second.
- Make the first live fragment immediately eligible for display and permit later high-frequency transient fragments to be adaptively coalesced within a 33-100 ms window.
- Prevent unrelated Codex conversations from waiting on Virtual Office-wide execution or persistence serialization while preserving same-conversation ordering and bounded Provider capacity.
- Enable the Codex fast path by default with a bounded default capacity of eight active turns, while preserving explicit flag-off rollback to the legacy single-turn posture.
- Classify user messages, approvals, key lifecycle events, and final results as durable state while allowing transient reasoning and delta activity to remain non-recoverable after process failure.
- Add stage-level measurement and deterministic acceptance fixtures for warm continued chat, concurrency isolation, event ordering, durability, and compatibility.
- Preserve public chat APIs, critical event semantics, final content, history behavior, cancellation, approval, and terminal outcomes.

## Capabilities

### New Capabilities

- `codex-chat-fast-path`: Defines the user-visible latency, concurrency isolation, transient-event handling, durability, observability, and compatibility requirements for warm continued Codex chats.

### Modified Capabilities

None.

## Impact

- Affects the Codex chat request path, Codex app-server coordination, Provider event journal/SSE delivery, Codex activity persistence, and focused chat performance instrumentation and tests.
- Applies to Codex requests from both Web and Feishu entry points, but does not redesign Feishu transport or cover other Providers, Project or Meeting execution, model inference performance, or Codex installation/authentication.
- No public route, request/response schema, critical event contract, or durable history semantic is intentionally broken.
