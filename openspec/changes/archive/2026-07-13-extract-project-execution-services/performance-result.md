# Project Execution Performance Result

## Reproduction

- Baseline SHA: `065d565e173a56789b2c54cb7429d95997ffd54f`
- Final measured code: `a42882e24ad4e8a13d39420b33cf3230cb19b816+section7-worktree`
- Final label: `section7-final-worktree-confirmation-2`
- Fixtures: small `5×10`, medium `50×50`, large `200×100`
- Method: 3 warmups and 20 measured runs per operation and scale
- Raw result: `performance-group6-final.json`

```bash
.venv/bin/python tests/project_performance_harness.py \
  --scales small,medium,large \
  --warmups 3 \
  --runs 20 \
  --revision-label section7-final-worktree-confirmation-2 \
  --output openspec/changes/extract-project-execution-services/performance-group6-final.json
```

The harness uses deterministic counted adapters and an in-memory project store. Operation counts are the release gate; elapsed time is secondary regression evidence rather than a production-latency claim.

## Stable operation counts

Counts were identical in all 20 measured runs and all three fixture sizes.

| Operation | Baseline load/save | Final load/save | Provider | Notification | Gateway | Git scan | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| start prepare | 1 / 1 | 1 / 1 | 0 | 0 | 0 | 1 | unchanged |
| provider completion | 2 / 1 | 2 / 1 | 1 | 0 | 0 | 1 | unchanged |
| review start | 1 / 1 | 1 / 1 | 0 | 0 | 0 | 0 | unchanged |
| acceptance | 2 / 1 | 2 / 1 | 0 | 0 | 0 | 0 | unchanged |
| Cron archived dispatch | 2 / 1 | **1 / 1** | 0 | 0 | 0 | 0 | **one redundant load removed** |

No measured operation increased project-store reads, durable writes, Provider calls, notifications, Gateway calls, or Git scans. Cron dispatch provides the required strict backend improvement: one project-store load is eliminated while the durable history write remains.

## Final latency and baseline comparison

| Scale | Operation | Baseline median / p95 ms | Final median / p95 ms | p95 change |
| --- | --- | ---: | ---: | ---: |
| small | start prepare | 0.916 / 1.124 | 1.268 / 1.494 | +32.9% |
| small | provider completion | 2.546 / 3.365 | 2.869 / 2.961 | -12.0% |
| small | review start | 0.905 / 1.027 | 1.180 / 1.264 | +23.1% |
| small | acceptance | 7.606 / 7.993 | 7.996 / 8.860 | +10.8% |
| small | Cron dispatch | 1.183 / 1.308 | 1.227 / 1.350 | +3.2% |
| medium | start prepare | 42.564 / 45.295 | 43.169 / 45.511 | +0.5% |
| medium | provider completion | 57.919 / 60.387 | 59.586 / 62.060 | +2.8% |
| medium | review start | 43.068 / 45.313 | 43.787 / 44.567 | -1.6% |
| medium | acceptance | 67.949 / 70.288 | 70.352 / 79.032 | +12.4% |
| medium | Cron dispatch | 56.568 / 59.146 | 44.563 / 46.298 | -21.7% |
| large | start prepare | 420.740 / 442.449 | 420.409 / 440.737 | -0.4% |
| large | provider completion | 558.819 / 574.769 | 568.123 / 592.914 | +3.2% |
| large | review start | 417.759 / 442.455 | 413.937 / 434.903 | -1.7% |
| large | acceptance | 590.105 / 599.681 | 555.047 / 567.428 | -5.4% |
| large | Cron dispatch | 569.216 / 596.642 | 405.999 / 421.225 | -29.4% |

The final all-scale run has one ratio above 30%: small-fixture start prepare is +32.9%, an absolute `0.370 ms` increase. Two additional small-only confirmation artifacts are retained as `performance-small-confirmation-a.json` and `performance-small-confirmation-b.json`; they demonstrate that sub-2ms p95 is sensitive to local scheduling noise, while operation counts remain identical. This small timing is not claimed as an optimization and must not be used as the staging release fixture. The confirmed staging fixture is medium, where every p95 remains below the 30% rollback threshold; large also remains below it. Medium and large Cron dispatch improve materially.

## Decision

The backend performance goal is satisfied:

1. No stable store or external-call count regressed.
2. Cron dispatch strictly improved from two project-store loads to one.
3. Compatibility, writer-race, schedule concurrency, security, and broad Python regression suites passed on the same `a42882e+section7-worktree` implementation measured by the raw artifact.
