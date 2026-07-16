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

## Callback recovery controls

Message-processing recovery is enabled by default for `channel-sdk-node`. These environment variables are read when the worker starts:

| Variable | Default | Validation and effect |
| --- | ---: | --- |
| `VO_FEISHU_CHAT_PROCESSING_RECOVERY_ENABLED` | `true` | Enables background spool replay. `false` retains files and keeps normal immediate delivery enabled. |
| `VO_FEISHU_CHAT_CALLBACK_ATTEMPT_TIMEOUT_MS` | `45000` | One callback attempt; clamped to 1–55 seconds. |
| `VO_FEISHU_CHAT_PROCESSING_RECOVERY_BASE_DELAY_MS` | `1000` | Initial retry delay; clamped to the configured maximum. |
| `VO_FEISHU_CHAT_PROCESSING_RECOVERY_MAX_DELAY_MS` | `30000` | Exponential-backoff cap. Maximum plus jitter is always below 60 seconds. |
| `VO_FEISHU_CHAT_PROCESSING_RECOVERY_JITTER_MS` | `5000` | Bounded jitter, capped at 10 seconds. |
| `VO_FEISHU_CHAT_PROCESSING_RECOVERY_CONCURRENCY` | `4` | Concurrent recovery chats, capped by global callback concurrency. |
| `VO_FEISHU_CHAT_MAX_CONCURRENT_CALLBACKS` | `16` | Live plus recovery callback capacity, clamped to 1–64. |
| `VO_FEISHU_CHAT_PROCESSING_WARNING_THRESHOLD_MS` | `60000` | Pending-age threshold for the operator warning. |

Retries are indefinite while the worker runs. A retained envelope is removed only after VO returns a terminal durable acknowledgement. A `processing` acknowledgement, timeout, network/HTTP failure, or malformed acknowledgement keeps the envelope. Per-chat lanes attempt only the oldest retained source message, while other chats can use bounded parallel capacity.

## Status interpretation

The Feishu Chat configuration/status response preserves `enabled`, `running`, `status`, `startedAt`, `lastEventAt`, `heartbeatAt`, and a secret-safe `lastError`. Additive public fields include `transport`, `workerInstanceId`, `sdk`, `reconnect`, `callback`, `command`, `queue`, `spool`, and `processing`. The server projects a strict allowlist: callback URLs, credentials, message content, raw exceptions, local paths, command ports/tokens, and arbitrary worker fields are never returned.

Important states:

- `missing_node_runtime` / `incompatible_node_runtime`: install Node.js 18+; VO and notifications remain available.
- `missing_channel_sdk` / `dependency_install_failed`: run the locked `npm ci` command above.
- `starting` / `connected` / `reconnecting`: normal lifecycle states.
- A connected SDK with `processing.state=degraded` means Feishu intake is connected but VO callback processing is unavailable or waiting for retry; the spool entry is retained.
- A rising public `command.failures` count means an SDK-backed outbound operation failed; the Agent result and VO history remain authoritative.
- `spool.pressure=true`: spool usage reached 80%; restore callback throughput and inspect slow Agent providers.
- `inbox_full`: the 1,000-entry or 50-MiB limit was reached and the worker disconnected to avoid unbounded intake.
- `orphaned_parent_exited`: the owner process disappeared; restart VO instead of launching the worker manually.

Group-specific observability is returned as `groupMetrics` by the Chat configuration/status API:

- `counters.accepted`, `completed`, and `duplicates`: accepted source turns, terminal outcomes, and durable source-ID replays.
- `counters.ignored.*`: VO-side group policy outcomes such as disabled group chat, invalid mention, unsupported transport, or non-human sender.
- `counters.agentFailures` / `deliveryFailures`: the Agent result and Feishu delivery result are separate; delivery failure never erases the Agent outcome.
- `pressure.queue`, `pressure.spool`, and `pressure.callback`: current worker bounds. Investigate a rising queue, `spool.pressure=true`, or a sustained callback backlog before broadening rollout.

The dedicated processing status bar is independent of the long-connection line:

| Field | Operator meaning |
| --- | --- |
| `state` | `healthy`, `recovering`, or `degraded`; a legacy worker has no `processing` object and is shown as unavailable. |
| `backlog` / `blocked` | Valid retryable envelopes and corrupt/unreadable retained entries. |
| `oldestPendingAt` | Source/receive time used for pending age and warning evaluation. |
| `lastAckAt` / `lastFailureAt` | Latest terminal acknowledgement and callback failure timestamps. |
| `nextRetryAt` / `recoveryActive` | Scheduled wake-up and whether a replay pass is running. |
| `consecutiveFailures` | Current backoff progression; it resets after durable progress. |
| `warning` | Pending or blocked work exceeded the configured warning threshold. |
| `lastErrorCategory` | Stable redacted category such as `callback_timeout` or `callback_network_error`. |

## Diagnosis and automatic spool recovery

Pending envelopes live in `VO_STATUS_DIR/feishu-channel-inbox` as mode-0600 JSON files. They are transport recovery state, not an independent conversation history.

1. Compare the two control-panel lines. If the long connection is healthy but processing is degraded, investigate VO/Agent callback health rather than reconnecting Feishu.
2. Check backlog, blocked count, oldest age, next retry, and error category. Restore the VO process/provider bottleneck and verify disk permissions/capacity.
3. Leave the worker running. Recovery is independent of new Feishu traffic, WebSocket reconnects, configuration edits, and process restarts; the next attempt starts within one minute under default/validated settings.
4. Confirm backlog falls, `lastAckAt` advances, and state returns to `healthy`. A failed chat may remain ordered behind its oldest source while unrelated chats continue.
5. If `blocked` is non-zero or the spool is full, stop intake before manual inspection. Reconcile retained source IDs against terminal VO records. Never edit or delete an entry merely to clear the warning.

## Staged rollout

1. Deploy the VO callback/index changes first so active work returns non-durable `processing` and only terminal persisted outcomes return durable acknowledgements.
2. Deploy the worker and UI with `VO_FEISHU_CHAT_PROCESSING_RECOVERY_ENABLED=false`. Verify immediate delivery, retained spool compatibility, redacted status, and the legacy/unavailable UI state during mixed versions.
3. Run the offline fault matrix and a disposable-tenant check. Require no unexplained loss/duplicate, deterministic same-chat order, unrelated-chat progress, retry start under one minute, bounded callback concurrency, and no status leakage.
4. Enable recovery for the intended worker and restart VO once to apply the environment setting. Observe backlog/oldest age through at least one induced callback outage and recovery.
5. Stop rollout on persistent warnings, blocked entries, uncertain single-worker ownership, reconnect loops, notification/card-action regression, or any non-idempotent Agent outcome.

## Rollback

The first rollback action is to disable background replay without changing transport:

```bash
export VO_FEISHU_CHAT_PROCESSING_RECOVERY_ENABLED=false
./start.sh
```

This never deletes retained files and does not disable immediate delivery. Reconcile the spool before code rollback. If transport rollback is also required:

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
