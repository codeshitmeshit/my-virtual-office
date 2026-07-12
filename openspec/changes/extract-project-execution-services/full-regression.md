# Project Execution Full Regression — Section 7

## Automated Python suite

Command:

```bash
rg --files tests -g 'test_*.py' \
  | rg -v 'tests/test_(chat_sessions|review_parser|workflow_e2e)\.py$' \
  | xargs .venv/bin/python -m pytest -q
```

Final post-CR result: **496 passed**, 2 dependency deprecation warnings, 0 failed. The suite covers project persistence and writer races, Provider adapters, execution lifecycle, Review/acceptance/notifications, Feishu, Meeting, Artifact, Cron, SSE, WebSocket route contracts, dashboard realtime behavior, and the new static/security/performance gates.

The first pre-CR run collected 497 tests and was `496 passed, 1 failed`: the failed assertion was `TemporaryDirectory` cleanup racing a finishing background workflow writer in `test_skipped_review_waits_for_acceptance_when_required`. The fixture now tracks and joins every launched execution thread before restoring globals and cleaning the directory. A name-only AST “coverage matrix” was also removed during CR because it did not execute behavior, leaving 496 real tests; the final complete command passed 496/496.

## Script-style Python suites

These files call `sys.exit` during import and therefore must not be collected by pytest.

| Command | Result |
| --- | --- |
| `.venv/bin/python tests/test_chat_sessions.py` | 20 checks passed |
| `.venv/bin/python tests/test_review_parser.py` | 16/16 passed |
| `.venv/bin/python tests/test_workflow_e2e.py` | 20/20 passed |
| `.venv/bin/python test_review_parser.py` | 85/85 passed |

## JavaScript/static suite

Command:

```bash
rg --files tests -g 'check_*.mjs' | sort | xargs -n1 node
```

Result: **23 scripts passed**, including project execution request payloads, Meeting blockers/records, Provider/Codex/Claude SSE bridges, dashboard realtime behavior, chat history/navigation/store, deduplication, frontend performance, and browser-script static safety.

## Syntax and specification gates

| Command | Result |
| --- | --- |
| `.venv/bin/python -m compileall -q app tests` | passed |
| `openspec validate extract-project-execution-services --strict` | valid |
| `git diff --check` | passed |

## Dedicated release gates

- Static Service dependency and persistence-coordinator tests: 24/24 with repository/writer regressions.
- Trusted-entry and sensitive-data command (project HTTP boundary, Meeting command, execution/review, Artifact, Feishu, Cron, Codex and Claude Provider adapters): 236/236 with canary-secret, Basic/Bearer/Cookie/JSON credentials, POSIX/Windows/UNC paths, logger, and notifier coverage.
- Performance artifact gates: 3/3; all stable call counts are non-regressing and Cron strictly improves project-store loads.
- Final Section 6 Schedule suite: 40/40; includes persisted capacity reservations, lease renewal, same-occurrence replay protection, and distinct-occurrence execution.

## Remaining manual-only coverage

`node tests/chat_history_performance.mjs` requires Chrome DevTools at `127.0.0.1:9224` and correctly failed fast because CDP was not running. The `chat_history_ui_e2e.mjs` and `chrome_*.mjs` suites have the same live-browser prerequisite. They are deferred to task 8.2, where the application and agent browser must be started through the repository startup script; they are not treated as automated failures in this headless Section 7 gate.
