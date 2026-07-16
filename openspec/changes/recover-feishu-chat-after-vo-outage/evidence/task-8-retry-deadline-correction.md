# Retry-Start Deadline Correction

Date: 2026-07-16

## Verified defect

The recovery coordinator previously computed its bounded backoff only after a recovery pass completed. A callback attempt could therefore consume the 45-second default transport timeout and then add the full 35-second maximum default backoff, producing an approximately 80-second gap between recovery-pass starts.

## Correction

- The coordinator captures the absolute start time of each recovery pass.
- Backoff now represents the target interval between recovery-pass starts.
- After the pass completes, elapsed callback and execution time is subtracted from that target.
- If the pass already consumed the target interval, the next wake is scheduled immediately.
- Explicit coalesced wake-ups remain immediate, and existing single-flight behavior is unchanged.

## Deterministic verification

The recovery fake clock is monotonic and can advance during an injected recovery run. The focused test proves:

- a 45-second attempt with a 35-second target schedules the next wake at `0ms` instead of adding another 35 seconds;
- a 10-second attempt with a 35-second target schedules only the remaining `25,000ms`;
- the resulting retry-start deadline remains below one minute.

```bash
cd integrations/feishu-channel-worker
node --test test/recovery.test.mjs
```

PASS — 6/6 tests.

## Complete Worker regression

```bash
cd integrations/feishu-channel-worker
node --test --test-reporter=tap
```

PASS — 48/48 tests, 0 failures.

```bash
openspec validate recover-feishu-chat-after-vo-outage --strict
git diff --check
```

Both commands pass after the evidence and task update.
