# Project Execution Performance Progress

## Group 2 — Repository and project commands

- Measured revision: `4e2d37378a582537a944606e63ce2014124e85b4+group2-fixed-worktree`
- Harness command: `.venv/bin/python tests/project_performance_harness.py --scales small,medium,large --warmups 3 --runs 20 --revision-label "$(git rev-parse HEAD)+group2-fixed-worktree" --output /tmp/project-performance-group2-fixed.json`
- Method: 3 warmups and 20 timed runs per operation/fixture. Peak memory is a separate `tracemalloc` run, so instrumentation does not distort latency samples.
- Result: operation counts were stable across all runs and fixture sizes. No median or p95 regression exceeded the 30% rollback threshold; the only increase was small-fixture provider-completion p95 at +4.2%.

| Scale | Operation | Baseline median / p95 (ms) | Group 2 median / p95 (ms) | Change median / p95 | Peak KiB |
| --- | --- | ---: | ---: | ---: | ---: |
| small | start prepare | 0.916 / 1.124 | 0.872 / 0.906 | -4.8% / -19.4% | 209.4 |
| small | provider completion | 2.546 / 3.365 | 2.248 / 3.505 | -11.7% / +4.2% | 246.2 |
| small | review start | 0.905 / 1.027 | 0.916 / 1.006 | +1.2% / -2.0% | 209.3 |
| small | acceptance | 7.606 / 7.993 | 6.696 / 7.266 | -12.0% / -9.1% | 609.9 |
| small | Cron dispatch | 1.183 / 1.308 | 1.159 / 1.184 | -2.0% / -9.5% | 264.7 |
| medium | start prepare | 42.564 / 45.295 | 38.903 / 42.434 | -8.6% / -6.3% | 8603.8 |
| medium | provider completion | 57.919 / 60.387 | 52.954 / 56.208 | -8.6% / -6.9% | 8608.8 |
| medium | review start | 43.068 / 45.313 | 38.749 / 40.176 | -10.0% / -11.3% | 8603.3 |
| medium | acceptance | 67.949 / 70.288 | 61.569 / 63.213 | -9.4% / -10.1% | 8605.4 |
| medium | Cron dispatch | 56.568 / 59.146 | 53.987 / 57.266 | -4.6% / -3.2% | 10939.6 |
| large | start prepare | 420.740 / 442.449 | 365.078 / 370.027 | -13.2% / -16.4% | 67810.8 |
| large | provider completion | 558.819 / 574.769 | 482.972 / 495.365 | -13.6% / -13.8% | 67815.9 |
| large | review start | 417.759 / 442.455 | 379.155 / 413.803 | -9.2% / -6.5% | 67810.6 |
| large | acceptance | 590.105 / 599.681 | 499.922 / 513.147 | -15.3% / -14.4% | 67812.6 |
| large | Cron dispatch | 569.216 / 596.642 | 495.755 / 525.443 | -12.9% / -11.9% | 86075.3 |

| Operation | Baseline load/save | Group 2 load/save | Result |
| --- | ---: | ---: | --- |
| start prepare | 1 / 1 | 1 / 1 | unchanged |
| provider completion | 2 / 1 | 2 / 1 | unchanged |
| review start | 1 / 1 | 1 / 1 | unchanged |
| acceptance | 2 / 1 | 2 / 1 | unchanged |
| Cron dispatch | 2 / 1 | 2 / 1 | unchanged |

The performance-improvement claim remains open because application-operation counts have not yet strictly improved. Group 2 establishes coordinated writes and prevents lost updates without a measured latency regression. The identified two-load paths belong to later lifecycle, acceptance, and schedule slices; at least one must strictly improve before final acceptance.

## Group 3 — Execution lifecycle

- Measured revision: `c4408c9c926d5e814fed3555dbb65669b7a3bd88+group3-final-post-cr`, after the conditional-merge, O(1) revision, external-watcher, and concurrency CR fixes.
- Harness command: `.venv/bin/python tests/project_performance_harness.py --scales small,medium,large --warmups 3 --runs 20 --revision-label "$(git rev-parse HEAD)+group3-final-post-cr" --output /tmp/project-performance-group3-final-post-cr.json`.
- Real Markdown revision command: `.venv/bin/python tests/project_revision_benchmark.py --scales small,medium,large --warmups 3 --runs 20 --output /tmp/project-revision-group3-final.json`.
- Auditable raw results: `performance-group3-final.json` and `revision-group3-final.json` in this change directory.
- All five scenarios retained their baseline load/save/provider/notification/gateway/Git-scan counts. Start prepare remains `1 load / 1 save / 1 Git scan`; provider completion remains `2 loads / 1 save / 1 Provider / 1 Git scan`.
- Against the original fixed baseline, final small p95 changes were `-3.1%` to `+28.5%`, medium `-1.2%` to `+5.3%`, and large `+5.2%` to `+13.1%`; every operation remained below the 30% rollback threshold. The lifecycle scenarios recorded the new O(1) revision port explicitly: start performed 4 revision checks and provider completion 3, without adding a store read/write or external call.
- On real Markdown trees, request-path `revision()` p95 was `0.001 ms` for all fixtures. The 500ms quick watcher p95 was `0.267 / 0.356 / 1.361 ms` for small/medium/large. The off-path 5-second fallback scan covered `55 / 2,550 / 20,200` files with p95 `3.004 / 26.610 / 159.783 ms`; it is not executed by request handlers and prevents in-place external edits from remaining hidden indefinitely.
- The repository coherent snapshot prevents the extracted atomic start path from increasing durable store reads: the no-snapshot smoke measured `3 loads`, while the coherent run measured the baseline `1 load`. Compatibility repair still runs when a store adapter is ingested and after every successful write; namespace changes invalidate the snapshot.

The overall strict operation-count improvement remains open for later review/acceptance or schedule slices. Group 3's verified result is no call-count regression while adding persist-before-launch and conditional attempt-result commit safety.

## Group 4 — Review, rework, and acceptance

- Measured revision: `f9d7745674569012c04564d937e03f2570ac0254+group4-review-acceptance-post-cr` with the final Group 4 CR fixes.
- Harness command: `.venv/bin/python tests/project_performance_harness.py --scales small,medium,large --warmups 3 --runs 20 --revision-label group4-review-acceptance-post-cr --output /tmp/project-performance-group4-post-cr.json`.
- Auditable raw result: `performance-group4-final.json` in this change directory.
- Review start retained `1 load / 1 save / 0 external calls`; acceptance retained `2 loads / 1 save / 0 external calls`. Counts were stable for all 20 runs at all fixture sizes, so the extraction introduced no store or external-call regression.
- Against the post-CR Group 3 measurement, final acceptance p95 changed `-11.0% / +20.4% / +7.3%` for small/medium/large. Review-start p95 changed `+29.7% / +23.5% / -2.3%`; the small result is the confirmation run (`1.291 ms`, versus `0.995 ms`) and remains below the 30% rollback threshold. The all-scale small sample was `1.477 ms`, so the sub-millisecond absolute variance was independently repeated rather than used to claim improvement.
- External notification delivery now happens only after the awaiting-acceptance business state and stable local intent are durable. A failed sender adds no business-state rollback and no extra synchronous call to the measured acceptance command.

The strict overall operation-count improvement remains open. Group 4 proves compatibility and failure isolation without increasing load/save/external-call counts.

## Group 6 — Project Schedule

- Measured revision: `9f7ccb8e46cd9ab005656897ee8f71da8b1d4243+group6-project-schedule-final-reviewed` with the final Group 6 worktree and all concentrated Section 6 CR fixes.
- Harness command: `.venv/bin/python tests/project_performance_harness.py --scales small,medium,large --warmups 3 --runs 20 --revision-label group6-project-schedule-final-reviewed --output openspec/changes/extract-project-execution-services/performance-group6-final.json`.
- Auditable raw result: `performance-group6-final.json` in this change directory.
- Cron dispatch improved from `2 loads / 1 save` to `1 load / 1 save` at every fixture size by using the Repository coherent snapshot and atomic history append. Gateway, Provider, notification, and Git-scan counts stayed at zero for the archived-dispatch fixture; counts were stable across all runs.
- Against the final Group 4 measurement, Cron dispatch p95 changed approximately `+1.4% / -17.0% / -30.7%` for small/medium/large (`1.490 / 55.855 / 426.968 ms`). No latency increase approaches the 30% rollback threshold. A first CR-fix run exposed `2.679 ms` small p95 because even statically archived callbacks wrote and released a dispatch claim; moving archived/paused prechecks before the persisted claim restored the final small result while executable paths still require the atomic persisted claim.
- Concentrated Section 6 regression command: `.venv/bin/python -m pytest -q tests/test_project_schedule_service.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_project_scheduled_cron_phase4.py tests/test_project_scheduled_cron_phase5.py tests/test_project_cron_idempotent_defect.py tests/test_project_writer_characterization.py` — `40 passed`.
- Broad Python regression command (excluding the three import-and-exit script tests `test_chat_sessions.py`, `test_review_parser.py`, and `test_workflow_e2e.py`): `rg --files tests -g 'test_*.py' | rg -v 'tests/test_(chat_sessions|review_parser|workflow_e2e)\\.py$' | xargs .venv/bin/python -m pytest -q` — `488 passed`, 2 dependency deprecation warnings. Script tests remain separate inputs to the final Section 7 full-regression matrix.
- Section 6 security/concurrency regressions cover same-Cron CRUD serialization, Gateway/binding convergence, runtime-field-preserving merges, persisted dispatch claims with lease renewal, run-now monotonic occurrence IDs with an O(1) completed high-water mark, distinct-occurrence execution, atomic persisted binding-capacity reservations and compensation, project-linked agents, delivery mode restrictions, binding/history limits, and sanitized Gateway/execution/history/log results.

This is the first strict operation-count improvement required by the backend performance goal: one redundant project-store load was removed from every measured Cron dispatch while preserving one durable history save.
