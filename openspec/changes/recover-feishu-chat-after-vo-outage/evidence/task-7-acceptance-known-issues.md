# Final Acceptance — Deferred Known Issues

Date: 2026-07-16

## Decision

The requirement owner accepted the implemented Feishu callback-recovery behavior and control-panel processing status. Functional acceptance is **PASS**.

The latest two-route pre-push review found the issues below. The requirement owner assessed them as non-blocking for this acceptance and requested that they be recorded for later remediation. This decision preserves the review findings; it does not claim that the findings were fixed or that the code review gate passed.

## Deferred issues

### 1. Per-chat retained backlog is not capped by the lane limit

- The `maxPerChatQueue=20` check applies to jobs submitted to the in-memory execution lane.
- Messages retained behind a failed same-chat spool head can return `queued` without entering that lane, so the retained per-chat count can exceed 20.
- The global spool remains bounded at 1,000 entries or 50 MiB. A single pathological chat can therefore consume global capacity and eventually affect intake for other chats.
- Follow-up: enforce the per-chat limit atomically at spool admission and add a Worker-level test covering a failed head followed by more than 20 same-chat messages.

### 2. Empty numeric environment values use minimum bounds

- Numeric configuration currently applies `Number(value)` before checking for a blank string.
- An explicitly empty environment value becomes zero and is clamped to the setting's minimum instead of using the documented fallback.
- Unset values continue to use the intended defaults.
- Follow-up: treat `undefined`, `null`, and trim-empty strings as absent and cover every numeric recovery setting with blank-value tests.

### 3. Public dependency diagnostics lose specificity

- The public worker-status whitelist omits `incompatible_node_runtime` and `incompatible_channel_sdk`, folding them into `error`.
- The projection also removes dependency-repair `action` text while the UI still supports rendering it.
- This degrades operator diagnosis but does not change callback retention or recovery execution.
- Follow-up: enumerate every preflight status and generate fixed, status-specific, secret-safe repair guidance on the server.

## Acceptance boundary

- Core callback recovery, retained-message ordering, uncertain-dispatch fail-closed behavior, heartbeat warning refresh, processing-health projection, and control-panel status remain accepted.
- Existing regression evidence remains valid because this acceptance update changes documentation only.
- This acceptance does not authorize a push. The documentation commit changes the reviewed HEAD, so any later push request must follow the repository's push-gate workflow for the new snapshot.
