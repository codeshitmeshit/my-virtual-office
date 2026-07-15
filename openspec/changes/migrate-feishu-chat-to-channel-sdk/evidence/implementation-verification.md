# Channel SDK Migration Implementation and Verification

Recorded: 2026-07-16 (Asia/Shanghai)

## Delivered

- Isolated Node 18+ ESM worker with `@larksuite/channel@0.4.0` pinned by lockfile and actionable Chat-only preflight states.
- Strict versioned inbound, command, and durable-ack protocols; authenticated loopback command port; atomic mode-0600 status and spool files.
- SDK-backed inbound lifecycle, normalized identity/thread/resource envelopes, durable replay, bounded concurrency/queues/spool, reconnect and parent-liveness behavior.
- SDK-backed send, reply, reactions, recall, and streamed resource downloads with safe attachment paths and classified failures.
- Python adapter and owned-child supervisor with `environment > saved config > channel-sdk-node` selection plus `legacy-python` rollback.
- Settings UI/status projection, supported startup dependency installation, Docker packaging, observability counters, redaction, operator runbook, and offline rollout rehearsal.
- Existing notification/card-action and provider/history behavior remains isolated and covered by regression tests.

## Reproducible verification

```text
cd integrations/feishu-channel-worker
npm test
# 22 passed, 0 failed

npm run preflight
# dependencies_ready; Node 20.20.2; channel SDK 0.4.0

npm ls @larksuite/channel --depth=0
# @larksuite/channel@0.4.0

cd ../..
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests -q --ignore=tests/test_workflow_e2e.py
# 712 passed

VO_TEST_URL=http://127.0.0.1:8090 VO_MANAGEMENT_TOKEN=<ephemeral> \
  .venv/bin/python tests/test_workflow_e2e.py
# 20/20 passed against an isolated local server

.venv/bin/python test_review_parser.py
# 85 passed, 0 failed

.venv/bin/python scripts/rehearse-feishu-channel-rollout.py
# ok=true; legacy -> Node -> missing-SDK injection -> legacy rollback;
# history preserved and VO startup isolated

openspec validate migrate-feishu-chat-to-channel-sdk --strict
# valid

python -m py_compile app/server.py app/feishu_chat_channel.py
node --check app/game.js
bash -n start.sh
git diff --check
# all succeeded
```

The provider baseline inventory was regenerated with its deterministic repository generator after `app/server.py` changed, then its reproducibility test passed.

The acceptance-discovered duplicate chat bubble was added as task 5.4. Exact `idempotencyKey` reconciliation now replaces the optimistic request with its authoritative history record and removes the matching live-layer node without collapsing same-text requests under different keys. Detailed evidence is recorded in `task-5.4-optimistic-history-reconciliation.md`.

## Activation gate

Automated implementation, offline rollout, local browser, and authorized real-tenant acceptance gates are complete. The user accepted the workspace behavior on 2026-07-16 after validating the SDK connection, private text/reply synchronization, image delivery, SSE live refresh, restart recovery, duplicate rendering fix, and bottom-follow behavior. Fault, capacity, notification-isolation, and rollback cases remain backed by deterministic automated tests and the offline rollout rehearsal rather than being represented as manual tenant observations.
