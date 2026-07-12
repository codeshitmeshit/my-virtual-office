# Project Execution Performance Baseline

## Reproduction

- Baseline SHA: `065d565e173a56789b2c54cb7429d95997ffd54f`
- Harness: `tests/project_performance_harness.py`
- Runtime: repository `.venv/bin/python`
- Warmups per operation/scale: 3
- Measured runs per operation/scale: 20
- Primary gate: stable application-operation counts
- Secondary evidence: wall-clock median and p95 from the in-memory deterministic fixture

```bash
.venv/bin/python tests/project_performance_harness.py \
  --scales small,medium,large \
  --warmups 3 \
  --runs 20 \
  --revision-label 065d565e173a56789b2c54cb7429d95997ffd54f \
  --output /tmp/project-performance-baseline.json
```

The harness replaces project persistence with a deep-copying in-memory store and replaces Provider, notification, Gateway, Git and thread dependencies with counted deterministic adapters. This isolates application orchestration cost from local disk variance. Absolute timings are not production latency claims.

## Fixtures

| Scale | Projects | Tasks per project | Total tasks |
| --- | ---: | ---: | ---: |
| small | 5 | 10 | 50 |
| medium | 50 | 50 | 2,500 |
| large | 200 | 100 | 20,000 |

## Stable operation counts

Counts were identical across all 20 runs and all three fixture sizes.

| Operation | Load | Save | Provider | Notification | Gateway | Git scan |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| start prepare | 1 | 1 | 0 | 0 | 0 | 1 |
| provider completion commit | 2 | 1 | 1 | 0 | 0 | 1 |
| review start | 1 | 1 | 0 | 0 | 0 | 0 |
| acceptance | 2 | 1 | 0 | 0 | 0 | 0 |
| Cron dispatch (archived skip + history) | 2 | 1 | 0 | 0 | 0 | 0 |

`provider completion`, `acceptance`, and `Cron dispatch` are the initial evidenced redundant-read candidates because each performs two project loads for one durable state commit.

## Wall-clock evidence

### Small fixture

| Operation | Median ms | p95 ms |
| --- | ---: | ---: |
| start prepare | 0.916 | 1.124 |
| provider completion commit | 2.546 | 3.365 |
| review start | 0.905 | 1.027 |
| acceptance | 7.606 | 7.993 |
| Cron dispatch | 1.183 | 1.308 |

### Medium fixture

| Operation | Median ms | p95 ms |
| --- | ---: | ---: |
| start prepare | 42.564 | 45.295 |
| provider completion commit | 57.919 | 60.387 |
| review start | 43.068 | 45.313 |
| acceptance | 67.949 | 70.288 |
| Cron dispatch | 56.568 | 59.146 |

### Large fixture

| Operation | Median ms | p95 ms |
| --- | ---: | ---: |
| start prepare | 420.740 | 442.449 |
| provider completion commit | 558.819 | 574.769 |
| review start | 417.759 | 442.455 |
| acceptance | 590.105 | 599.681 |
| Cron dispatch | 569.216 | 596.642 |

## Acceptance rules for the result report

1. No measured path may increase store or external-operation counts.
2. At least one of the three identified two-load paths must strictly reduce project-store reads before the change may claim a backend performance improvement.
3. `performance-result.md` must use the same SHA-labelled harness command, fixtures, warmups and run count.
4. Timing changes without stable operation-count evidence are informative only and cannot independently prove improvement.
