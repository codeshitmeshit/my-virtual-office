# Task 6 — Push-Gate Corrections

Date: 2026-07-16

The pre-push Coco-fallback and Codex reviews reported three possible defects. Main-agent verification found all three root problems reachable, with one refinement: the recovery-off live-drain issue is guaranteed when a retained same-chat head predates a new event; normal same-chat SDK callbacks themselves are serialized.

## 6.1 Uncertain provider dispatch after VO restart

Correction:

- New processing indexes persist `executionPhase=claimed` before provider dispatch.
- Immediately before invoking the Agent provider, VO atomically changes the phase to `dispatching`.
- A new VO process may reclaim only `claimed` work.
- `dispatching` and legacy phase-less processing indexes return non-durable `processing` and never invoke the Agent again merely because the owner process changed.
- A failure to persist the dispatch boundary fails closed before provider invocation.

This closes the proven duplicate-provider path. It does not claim a cross-system transaction with external providers: an uncertain `dispatching` outcome remains retained and warning-visible for operator reconciliation.

Focused command:

```bash
VO_STATUS_DIR="$(mktemp -d)" .venv/bin/python -m pytest -q tests/test_feishu_notifications.py -k 'worker_processing_ack or worker_reclaims_stale_processing or does_not_redispatch_uncertain'
```

Result: PASS — 3 selected tests.

## 6.2 Ordered live drain with recovery disabled

Correction:

- When recovery is disabled and a new live message is behind older retained work in the same chat, the live handler attempts each retained head in order through the new source message.
- The first failed head stops the drain. Failed head and unattempted tail remain durable.
- Recovery-enabled behavior remains coordinator-owned.

Focused result: PASS — successful order `old → new` with an empty spool, and failure retention with only the old head attempted.

## 6.3 Quiet backlog warning

Correction:

- The five-second worker heartbeat republishes processing health as well as `heartbeatAt`.
- Warning age therefore crosses its threshold without a new message, callback attempt, or enabled recovery timer.

Focused result: PASS — a recovery-off backlog transitions from `warning=false` to `warning=true` on heartbeat after its cached oldest age crosses the threshold.

## Complete regression

```bash
cd integrations/feishu-channel-worker && node --test --test-reporter=dot
```

PASS — 47 tests.

```bash
.venv/bin/python -m pytest -q tests/test_feishu_notifications.py
```

PASS — 71 tests.

```bash
node tests/check_feishu_processing_status_ui.mjs
node tests/check_feishu_group_chat_config_static.mjs
node --check app/game.js
```

PASS.

```bash
.venv/bin/python scripts/rehearse-feishu-channel-rollout.py
```

PASS — all 16 redacted rollout/rollback checks true.

```bash
openspec validate recover-feishu-chat-after-vo-outage --strict
git diff --check
```

PASS.

The previous push review snapshot ended at `17f8a72` and is invalidated by these corrections. A fresh two-route pre-push review is required before any push.
