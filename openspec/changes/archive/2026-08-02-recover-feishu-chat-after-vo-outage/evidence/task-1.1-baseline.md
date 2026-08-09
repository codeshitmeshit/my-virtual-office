# Task 1.1 — Isolated Worktree and Pre-Change Baseline

## Development isolation

- Worktree: `/Users/bytedance/cosh/my-virtual-office-recover-feishu-chat`
- Branch: `codex/recover-feishu-chat-after-vo-outage`
- Base revision: `1d530e2d5350d73519f0fc35fd9c09cecaf4cc83`
- Confirmed OpenSpec artifacts were copied into the worktree before any business or test-code edit.

## OpenSpec validation

Command:

```bash
openspec validate recover-feishu-chat-after-vo-outage --json
```

Result: PASS (`1` change passed, `0` failed, no issues).

## Existing focused suite

Command:

```bash
cd integrations/feishu-channel-worker && npm test
```

Result: PASS (`24` tests passed, `0` failed).

## Deterministic red feedback loop

The one-shot Node harness creates a worker with a fake connected Feishu channel and a callback that fails for `om_pending`, then marks VO healthy and successfully delivers `om_after_recovery`. It finally asserts that the durable spool is empty.

Command shape:

```bash
cd integrations/feishu-channel-worker
node --input-type=module - <<'NODE'
// Instantiate FeishuChannelWorker with a failure-first callback.
// Deliver om_pending, recover VO, then deliver om_after_recovery.
// Assert worker.spool.stats().entries === 0.
NODE
```

Observed output:

```text
{"delivered":["om_pending","om_after_recovery"],"remaining":1}
AssertionError: VO recovered and accepted a new callback, but the older spooled event was never replayed
1 !== 0
```

Result: EXPECTED FAIL. The harness reaches the real worker callback/spool path, deterministically proves the reported failure, and can become the final green recovery check after implementation.
