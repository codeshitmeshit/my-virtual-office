## Meeting-domain performance result

Measured on 2026-07-13 with `tests/meeting_baseline_harness.py`: three warmups and twenty measured runs for each fixed 1/20/100 Meeting fixture. Raw evidence is in `performance-final.json`; the original pre-unification evidence remains in `performance-baseline.json`.

| Meetings | Unified bytes | Load p95 | Save p95 |
|---:|---:|---:|---:|
| 1 | 3,266 | 0.0283 ms | 3.7892 ms |
| 20 | 58,750 | 0.5382 ms | 10.9507 ms |
| 100 | 292,710 | 2.3392 ms | 35.8034 ms |

The real manual-confirm conversion path performs exactly one unified Meeting-domain update, zero Provider calls, and one notification coordination call. The pre-unification characterization observed four Meeting-domain durable writes across the executable/request compatibility stores. Whole-file save cost grows with Store size as expected; all slow Provider and notification calls remain outside the repository lock.

