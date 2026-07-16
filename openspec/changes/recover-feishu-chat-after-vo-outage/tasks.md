## 1. Isolated Development Baseline

- [x] 1.1 Before any implementation or test-code edit, create an isolated Git worktree on `codex/recover-feishu-chat-after-vo-outage`, transfer the confirmed OpenSpec artifacts into that worktree, run OpenSpec validation, and record the deterministic callback-outage/no-replay baseline under the change evidence directory.

## 2. Safe VO Callback Contract

- [x] 2.1 Extend the VO source-message index and inbound callback contract to distinguish active `processing` ownership from terminal durable outcomes, return fast non-durable processing acknowledgements, reclaim work after a VO process restart, index terminal ignored/rejected outcomes, and add focused Python tests for concurrent duplicates, restart reclaim, terminal uniqueness, and secret-safe responses.
- [x] 2.2 Add a single-attempt callback-client API with a bounded transport deadline and stable classifications for network failure, timeout, HTTP failure, invalid acknowledgement, non-terminal processing, and terminal durable acknowledgement while preserving the existing API until coordinator integration; verify it with deterministic Node tests.
- [x] 2.3 Extend the inbound spool with deterministic source ordering and one bounded snapshot containing valid, blocked, size, pressure/full, and oldest-pending metadata; verify ordering tie-breakers, corrupt-entry retention, limits, and mode-safe persistence with Node tests.

## 3. Independent Processing Recovery

- [x] 3.1 Implement an injectable single-flight processing recovery coordinator with capped exponential backoff, bounded jitter, sub-minute maximum wake-up delay, indefinite retries, success reset, coalesced wake-ups, feature-switch shutdown, and deterministic clock/random tests.
- [x] 3.2 Implement a shared per-chat execution-lane scheduler for live delivery and replay that attempts only the oldest retained message per chat, prevents duplicate active message IDs, preserves same-chat order, permits bounded cross-chat progress, and reuses the global callback capacity; verify ordering, starvation isolation, and queue-pressure behavior.
- [x] 3.3 Integrate callback attempts, ordered spool replay, per-chat lanes, and the processing coordinator into worker startup, immediate delivery, callback failure/success, SDK reconnect, spool pressure/full, and shutdown; keep connection recovery separate, expose validated environment controls, and prove automatic recovery without a new Feishu event, reconnect, configuration change, or restart.

## 4. Processing Health and Control Panel

- [x] 4.1 Add the additive worker `processing` health state, counters, warning threshold, retry/ack timestamps, blocked/backlog metadata, and server-side public status whitelist; verify healthy/degraded/recovering transitions and canary redaction for credentials, message content, callback URLs, errors, and local paths.
- [x] 4.2 Add the localized Feishu message-processing status bar beside the existing connection status, render healthy/degraded/recovering/legacy states with backlog and age/progress details, poll only while the management panel is visible, and add focused DOM/static tests for state transitions, escaping, missing legacy data, and poll cleanup.

## 5. Integrated Verification and Rollout

- [x] 5.1 Add integrated fault-injection coverage for connection refusal, accepted-but-unresponsive callbacks, long Agent turns, VO restart during processing, terminal response loss, same-chat backlog, cross-chat concurrency, corrupt/full spool, worker restart, and recovery switch off/on; prove sub-minute retry start, no unexplained loss/duplicate, and deterministic order.
- [x] 5.2 Document the new recovery controls, processing-health fields, operator warning/diagnosis flow, server-first recovery-off rollout, enablement gates, and rollback procedure without exposing internal endpoints or secrets.
- [x] 5.3 Run the focused Node and Python suites, relevant Feishu regression coverage, control-panel checks, OpenSpec validation, and an offline rollout/rollback rehearsal; save reproducible commands and redacted results under the change evidence directory for the test-results confirmation gate.

## 6. Push-Gate Corrections

- [x] 6.1 Persist a pre-dispatch versus dispatch-uncertain source phase, reclaim only work proven not dispatched, fail closed for legacy/uncertain processing owners after VO restart, and verify that restart replay cannot invoke the Agent twice.
- [x] 6.2 Preserve event-triggered ordered live delivery when background recovery is disabled by draining older same-chat heads through the newly received message, stopping on the first failed head; verify success order and failure retention.
- [x] 6.3 Recompute processing warning age on heartbeat so a quiet recovery-off backlog crosses the operator threshold; add deterministic status coverage, rerun complete Node/Python/UI/OpenSpec/rehearsal checks, and record push-gate correction evidence.
