# Feishu Agent Chat Channel Worker Runbook

This runbook covers the `@larksuite/channel` transport used only by the Feishu Agent Chat App. The separate Feishu notification/card-action application remains on its Python runtime and configuration.

## Install and verify dependencies

The supported local startup command installs the locked production dependencies when they are absent:

```bash
./start.sh
```

For a manual repair:

```bash
cd integrations/feishu-channel-worker
npm ci --omit=dev --ignore-scripts --no-audit --no-fund
npm run preflight
```

The worker requires Node.js 18 or newer and exactly `@larksuite/channel` 0.4.0 from the committed npm lockfile. Do not use a global install or `npm update`. An SDK upgrade requires source review, an explicit dependency/lockfile change, the Node/Python contract suite, and real-tenant acceptance.

## Select a transport

The effective transport follows this precedence:

1. `VO_FEISHU_CHAT_TRANSPORT`
2. saved `feishu.chatApp.transportImplementation`
3. `channel-sdk-node`

Supported values are `channel-sdk-node` and `legacy-python`.

Rollout starts safely with:

```bash
export VO_FEISHU_CHAT_TRANSPORT=legacy-python
./start.sh
```

After verifying the existing path, switch only the Chat App worker:

```bash
export VO_FEISHU_CHAT_TRANSPORT=channel-sdk-node
./start.sh
```

Do not run both implementations for the same App credentials. The VO supervisor owns one direct child, rotates the worker instance/token at start, stops the current child before changing implementation, and rejects stale status from another instance.

## Status interpretation

The existing Feishu Chat configuration/status API preserves `enabled`, `running`, `status`, `startedAt`, `lastEventAt`, and `lastError`. Additive fields include `transport`, `workerInstanceId`, `heartbeatAt`, `sdk`, `reconnect`, `callback`, `command`, `queue`, `spool`, and `counters`.

Important states:

- `missing_node_runtime` / `incompatible_node_runtime`: install Node.js 18+; VO and notifications remain available.
- `missing_channel_sdk` / `dependency_install_failed`: run the locked `npm ci` command above.
- `starting` / `connected` / `reconnecting`: normal lifecycle states.
- `authentication_failure`: verify only the Chat App ID/Secret and Feishu permissions; never paste secrets into logs.
- `callback_failure`: Python callback was unavailable or did not return a durable acknowledgement; the spool entry is retained.
- `command_failure`: an SDK-backed outbound operation failed; the Agent result and VO history remain authoritative.
- `inbox_pressure`: spool usage reached 80%; restore callback throughput and inspect slow Agent providers.
- `inbox_full`: the 1,000-entry or 50-MiB limit was reached and the worker disconnected to avoid unbounded intake.
- `orphaned_parent_exited`: the owner process disappeared; restart VO instead of launching the worker manually.

## Pressure and spool recovery

Pending envelopes live in `VO_STATUS_DIR/feishu-channel-inbox` as mode-0600 JSON files. They are transport recovery state, not an independent conversation history.

1. Stop the Chat App worker or set the legacy override before manual inspection.
2. Restore the Python callback/provider bottleneck and ensure disk permissions/capacity are healthy.
3. Restart VO. The Node worker replays pending files with the original `sourceMessageId`.
4. Confirm `spool.entries` falls and `counters.replayed` / `counters.callbackAcknowledged` rise.
5. Reconcile remaining files against VO `feishu-channel-records.jsonl` and the communication ledger. Never delete an entry unless a durable VO terminal record exists.

## Rollback

```bash
export VO_FEISHU_CHAT_TRANSPORT=legacy-python
./start.sh
```

Verify the status reports `transport=legacy-python`, only one child is running, representative-Agent/bindings are unchanged, historical Feishu turns remain visible, and notification/card actions still work. No history migration is needed. Preserve the Node spool until its source message IDs are reconciled through VO idempotency.

Run the offline rehearsal before a rollout:

```bash
.venv/bin/python scripts/rehearse-feishu-channel-rollout.py
```

## Real-tenant acceptance gate

Before removing the legacy rollout override, validate with redacted test-tenant credentials: handshake, private text, group rejection, image/file resource, duplicate/replay, rapid same-chat order, representative-Agent switch, provider failure, outbound failure, reconnect, process restart, status/history, notification isolation, and rollback. Stop or roll back on unexplained loss/duplication, sustained pressure, reconnect loops, secret leakage, notification regression, or uncertain single-worker ownership.
