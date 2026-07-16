# Task 5.3 — Final Verification and Offline Rollout Rehearsal

Date: 2026-07-16

Branch: `codex/recover-feishu-chat-after-vo-outage`

All commands ran from the isolated development worktree. Outputs below omit credentials, callback URLs, message content, raw exceptions, and local temporary paths.

## Node worker and fault matrix

Command:

```bash
cd integrations/feishu-channel-worker
node --test --test-reporter=dot
```

Result: PASS — 44 tests, 0 failures.

Coverage includes callback classification/timeouts, single-flight indefinite scheduling, bounded jitter and sub-minute wake, per-chat ordering, cross-chat capacity, spool ordering/corruption/full state, automatic recovery without a new event or reconnect, processing-health transitions, accepted-but-unresponsive callback, long Agent `processing`, terminal-response loss, worker restart, and recovery switch off/on.

The pre-change red loop is now green through:

- `processing recovery drains a failed callback after VO returns without a new event or reconnect`;
- `accepted-but-unresponsive callback times out and recovers without socket reconnect or a new event`.

Both retain the original source envelope after failure, make VO available without sending another Feishu event, and assert that recovery removes the retained entry after a terminal durable acknowledgement. The connection counter remains one.

## VO callback and Feishu regression suite

Command:

```bash
.venv/bin/python -m pytest -q tests/test_feishu_notifications.py
```

Result: PASS — 70 tests, 0 failures.

This covers active-source `processing` acknowledgements, stale owner reclaim after VO restart, terminal ignored/rejected indexing, durable duplicate behavior, worker status projection/redaction, Chat/notification isolation, group/private behavior, and existing outbound/card-action contracts.

Focused pytest selection must set a temporary `VO_STATUS_DIR` before importing `server`; otherwise an ambient container `/data` value can make an isolated selection fail before tests run. The full suite initializes its own temporary directory and passed. Reproducible focused form:

```bash
VO_STATUS_DIR="$(mktemp -d)" .venv/bin/python -m pytest -q tests/test_feishu_notifications.py -k 'worker_processing_ack or worker_reclaims_stale_processing or public_worker_status'
```

Result: PASS — 3 selected tests, 0 failures.

## Control-panel checks

Commands:

```bash
node tests/check_feishu_processing_status_ui.mjs
node tests/check_feishu_group_chat_config_static.mjs
node --check app/game.js
```

Result: PASS.

The focused UI check covers the dedicated processing element, healthy/degraded/recovering/legacy copy, `textContent`-only rendering, five-second visible-panel polling, and timer cleanup on close/visibility loss.

## Offline rollout and rollback rehearsal

Command:

```bash
.venv/bin/python scripts/rehearse-feishu-channel-rollout.py
```

Result: PASS — `ok=true`, with all 16 checks true:

- recovery-off retention mode and recovery-on enablement;
- callback timeout at or below 55 seconds and max retry wake below one minute;
- Node selection, isolated dependency failure, and legacy restoration;
- restart reconciliation, history preservation, no migration, group default-off/enable/disable, and classified delivery failure.

The rehearsal emits `statusDir=<temporary>` and synthetic identifiers only.

## Specification and repository checks

Commands:

```bash
openspec validate recover-feishu-chat-after-vo-outage --strict
git diff --check
```

Result: PASS — change valid; no whitespace errors.

## Acceptance conclusion

- No test observed an unexplained source-message loss or duplicate Agent execution.
- Same-chat retained messages remained source ordered; an unavailable chat did not block another chat.
- A terminal durable acknowledgement is the only worker deletion condition.
- Processing recovery remains independent from the Feishu WebSocket lifecycle.
- Public processing status contains only the documented allowlist and stable error categories.
- Disabling recovery preserves spool files and immediate delivery, providing a no-migration rollback control.

Local/offline verification is complete. Real-tenant enablement remains an operational gate and is not performed by this change.
