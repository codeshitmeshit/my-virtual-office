## Phase 7 complete regression

Date: 2026-07-13

### Automated evidence

- Python: all files matching `tests/test_*.py`, excluding only `tests/test_workflow_e2e.py`, passed: **583 passed**, one third-party protobuf deprecation warning, 46.07 seconds.
- Root `test_review_parser.py`: its standalone import-time suite reported **85 passed, 0 failed**. It cannot be collected by pytest because it calls `sys.exit(0)` during import and collides by module name with `tests/test_review_parser.py`.
- JavaScript: every `tests/check_*.mjs` script passed; `node --test tests/test_*.js` passed **12/12**.
- Meeting characterization manifest: **10/10** exact scenario nodes passed; machine-readable output is `characterization-result.json`.
- Meeting performance: `tests/meeting_baseline_harness.py` completed fixed 1/20/100 fixtures; raw output is `performance-final.json` and analysis is `performance-result.md`.
- OpenSpec: `openspec validate extract-meeting-and-collaboration-services --strict` passed.
- Static/build: `python -m compileall -q app scripts tests` and `git diff --check` passed.

The Python suite covers migration malformed/symlink/source-race/rollback cases, unified repository persistence and concurrency, lifecycle/occupancy, Project Execution, Provider contracts, Feishu notification/callback behavior, SSE/WebSocket route contracts, security canaries, and performance artifact gates.

### Confirmed defects corrected

- Late targeted Agent responses could commit after an intervention because they lacked a durable event-sequence compare token.
- Two forced Meetings could silently choose one Agent occupancy owner during rebuild.
- Request-to-Meeting conversion could lose the rebuilt occupancy mapping when a temporary unified view replaced its dictionary.
- Callback replay restarted an already converted Meeting; persistent callback replay is now a true no-op.
- Action-item retry after Project success could duplicate projection without a stable Project key.
- Archived Project performance tests referenced the former active OpenSpec path and failed after valid archival.
- Notification sanitization initially changed tuple-shaped detail payloads; tuple compatibility is now preserved.

### Manual-only / deferred to Phase 8

- `tests/test_workflow_e2e.py`, `tests/test_crud_projects.sh`, Chrome/CDP scripts, and UI acceptance require a running application. They will be executed only after starting via `start.sh`, per the confirmed acceptance constraint.
- Real Feishu delivery and non-reversible external Agent effects remain best-effort/manual because credentials and external systems are not part of deterministic local regression.
