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

## Enable trusted group chat

Group chat is a separate, default-off capability. It is available only on `channel-sdk-node`; `legacy-python` is intentionally private-only. Enable it in the Feishu Chat App settings or with:

```bash
export VO_FEISHU_CHAT_TRANSPORT=channel-sdk-node
export VO_FEISHU_GROUP_CHAT_ENABLED=true
./start.sh
```

Adding the bot to a group is the trust grant: every human member of that group can invoke the representative Agent by explicitly mentioning the bot. There is no VO group allowlist or per-member binding. Use only disposable/test groups during acceptance, then only groups whose full membership and Agent tool permissions are trusted. Ordinary non-mentioned group traffic, `@all`, bots, system/anonymous senders, files, and unsupported content do not enter Agent context.

Each group receives one shared `feishu-group:*` conversation, isolated from private chat and other groups. Group audit records are durable but `visibleInOffice=false`; they are excluded from VO history, legacy chat merging, public communication-history APIs, and Feishu SSE publish/replay. Private Feishu chat retains its existing history and SSE behavior.

To stop new group intake without affecting private chat:

```bash
export VO_FEISHU_GROUP_CHAT_ENABLED=false
./start.sh
```

An already-running group turn may finish and record its Agent/delivery outcome. Reconcile `processing` source IDs under `VO_STATUS_DIR/feishu-source-message-index` before deleting spool state or rolling code back.

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

Group-specific observability is returned as `groupMetrics` by the Chat configuration/status API:

- `counters.accepted`, `completed`, and `duplicates`: accepted source turns, terminal outcomes, and durable source-ID replays.
- `counters.ignored.*`: VO-side group policy outcomes such as disabled group chat, invalid mention, unsupported transport, or non-human sender.
- `counters.agentFailures` / `deliveryFailures`: the Agent result and Feishu delivery result are separate; delivery failure never erases the Agent outcome.
- `pressure.queue`, `pressure.spool`, and `pressure.callback`: current worker bounds. Investigate a rising queue, `spool.pressure=true`, or a sustained callback backlog before broadening rollout.
- Worker `counters.policyRejectedByReason.*`, `queuePressure`, `queueRejected`, and `spoolFull`: SDK policy and capacity decisions. These counters intentionally contain no message text or member table.

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

For group rollout, first disable `VO_FEISHU_GROUP_CHAT_ENABLED` and allow in-flight turns to settle. Then reconcile source index states with `feishu-channel-records.jsonl` and the communication ledger. A code rollback or `legacy-python` override automatically returns to private-only behavior; group audit/source-index files may remain in place and must not be projected into VO chat history.

Run the offline rehearsal before a rollout:

```bash
.venv/bin/python scripts/rehearse-feishu-channel-rollout.py
```

## Real-tenant acceptance gate

Before enabling the intended trusted groups, validate with redacted test-tenant credentials: handshake, private text, mentioned group text/rich-post image, non-mentioned traffic, another-member mention, `@all`, bot sender, multiple humans/groups, private/group interleaving, topic reply, duplicate/replay, rapid same-group order, representative-Agent switch, provider failure, outbound failure, reconnect, process restart, status/history/SSE absence, notification isolation, switch disablement, and legacy rollback. Stop or roll back on unexplained loss/duplication, group content in VO history/SSE, sustained pressure, reconnect loops, secret leakage, notification regression, or uncertain single-worker ownership.
