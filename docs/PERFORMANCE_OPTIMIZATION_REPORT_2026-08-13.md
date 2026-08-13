# Backend performance optimization report — 2026-08-13

## Scope

This report covers the two persistence paths migrated from JSON to SQLite:

- Agent/Codex activity events.
- Meeting-domain state and event append operations.

The raw, machine-readable result is in [`performance/performance-store-benchmark-2026-08-13.json`](performance/performance-store-benchmark-2026-08-13.json). The benchmark is reproducible with:

```bash
.venv/bin/python tests/performance_store_benchmark.py \
  --runs 50 \
  --warmups 5 \
  --output docs/performance/performance-store-benchmark-2026-08-13.json
```

The latest figures below are the median of 50 measured operations after five warmups, using local temporary directories. The old Agent baseline uses its cached JSON read plus bounded whole-file rewrite. The old Meeting baseline reproduces cached deep-copy snapshots, validation, synchronous whole-file replacement and directory sync. The SQLite side runs the production typed repository APIs; it no longer uses a full-store compatibility snapshot.

## Results

### Agent event hot paths

| Retained events | Append JSON → SQLite | Change | Scoped query JSON → SQLite | Change |
|---:|---:|---:|---:|---:|
| 100 | 0.798 ms → 1.979 ms | 0.40× / fixed-cost regression | 0.0050 ms → 0.0016 ms | 3.12× faster |
| 1,000 | 3.908 ms → 2.362 ms | 1.65× faster | 0.0240 ms → 0.0037 ms | 6.49× faster |
| 4,000 | 13.301 ms → 3.916 ms | 3.40× faster | 0.0920 ms → 0.0108 ms | 8.52× faster |

Agent events show the intended scaling improvement. SQLite has fixed transaction overhead at 100 records, but it avoids rewriting an increasingly large JSON file and wins from 1,000 records onward. The in-process per-scope index also prevents scoped reads from scanning the retained global list.

### Meeting-domain hot paths

| Meetings / initial events | Event append JSON → SQLite | Change | Full JSON snapshot → typed detail read | Change |
|---:|---:|---:|---:|---:|
| 1 / 20 | 0.927 ms → 2.156 ms | fixed-cost regression | 0.104 ms → 2.080 ms | fixed-cost regression |
| 20 / 400 | 4.008 ms → 2.186 ms | 1.83× faster | 0.660 ms → 2.062 ms | fixed-cost regression |
| 100 / 2,000 | 16.369 ms → 2.242 ms | 7.30× faster | 3.080 ms → 2.120 ms | 1.45× faster |

The typed cutover removes the former dominant whole-domain copy/validation cost. At 20 Meetings, event append is 45.5% lower latency; at 100 Meetings it is 86.3% lower. A one-Meeting database remains slower because opening and committing SQLite has a fixed cost, but its absolute median is about 2.2 ms. The detail-read crossover appears above 20 Meetings and is 31.2% faster at 100. Runtime projections also batch Meeting/event reads through one connection, avoiding an N+1 connection pattern.

### Storage footprint

SQLite uses more disk space at these sizes because of pages and indexes. Examples:

- Agent events, 4,000 records: JSON 1.31 MiB; SQLite 2.07 MiB.
- Meetings, 100 meetings / 2,000 initial events: JSON 570 KiB; SQLite 776 KiB.

The WAL was checkpointed when measured, so the reported WAL size was zero. Runtime WAL size can temporarily grow between checkpoints.

## Functional and migration verification

- Full Python regression: 3,028 passed; two pre-existing UI typography assertions remain red because the dirty worktree uses non-pixel fonts.
- Meeting/Prompt/migration focused regression: 218 passed.
- Agent/Meeting migration rehearsals: 1, 20 and 100 Meeting fixtures passed validation, apply, integrity check and idempotent repeat.
- Agent append regression verifies one event insert rather than a full-table rewrite.
- Meeting append regression verifies one new event-row write with no deletion/rebuild of prior events.
- Static gates verify the extracted Agent and Meeting workflow modules do not import or hydrate `server.py` globals.
- Provider and Meeting generated inventories reproduce exactly.

## Conclusion

The Agent event migration is a measured performance improvement for retained histories of 1,000–4,000 events. Meeting is now also a measured scaling improvement: typed row-scoped transactions replace the generic full-domain mutation path, while projection reads batch Meetings and event streams on one connection.

Runtime `snapshot/update`, split-store load/save views and dual reads were removed. Full-domain export remains only as the explicitly named offline migration verifier. The remaining low-cardinality regression is bounded SQLite connection/transaction overhead; it is the tradeoff for durable atomic writes and does not grow with the full domain size.
