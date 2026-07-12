# Project Execution Full Regression — Final Section 8 confirmation

## Automated Python suite

Command:

```bash
rg --files tests -g 'test_*.py' \
  | rg -v 'tests/test_(chat_sessions|review_parser|workflow_e2e)\.py$' \
  | xargs .venv/bin/python -m pytest -q
```

Final post-CR result: **505 passed**, 2 dependency deprecation warnings, 0 failed. The suite covers project persistence and writer races, Provider adapters, execution lifecycle, Review/acceptance/notifications, Feishu, Meeting, Artifact, Cron, SSE, WebSocket route contracts, dashboard realtime behavior, and the static/security/performance gates. Section 8, overall-CR, and push-gate additions cover the documentation contract, concurrent compatibility work-log/project updates, attempt-workspace binding, Provider-enforced read-only native review, Cron occurrence retry after unexpected exceptions, Gateway/binding compensation/retry failures, and fail-closed missing/relative Artifact roots.

The first Section 8 run was `497 passed, 1 failed`: the reviewer-provider matrix replaced the Claude handler but did not restore it, so a later usage-ledger test observed the fake success response. Restoring the fourth patched handler removed the order dependency. A later full run exposed an existing test-fixture cleanup race after rework; that fixture now tracks and joins its launched threads. After the overall CR and push-gate fixes, the final complete suite passed 505/505.

## Script-style Python suites

These files call `sys.exit` during import and therefore must not be collected by pytest.

| Command | Result |
| --- | --- |
| `.venv/bin/python tests/test_chat_sessions.py` | 20 checks passed |
| `.venv/bin/python tests/test_review_parser.py` | 16/16 passed |
| `VO_MANAGEMENT_TOKEN=<test-token> .venv/bin/python tests/test_workflow_e2e.py` | 20/20 passed; server started via `./start.sh` |
| `.venv/bin/python test_review_parser.py` | 85/85 passed |
| `node tests/test_management_token_dialog.js` | modal, shared prompt, and domain-403 pass-through checks passed |

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
- Dedicated Schedule/Cron files: 39/39; includes persisted capacity reservations, lease renewal, same-occurrence replay protection, distinct-occurrence execution, exception retry, and update/delete compensation. Writer/performance suites add further Schedule coverage in the 504-test total.

## Remaining manual-only coverage

`node tests/chat_history_performance.mjs` requires Chrome DevTools at `127.0.0.1:9224`; CDP was not available in this environment. Task 8.2 instead used the in-app browser to confirm that the startup-script instance rendered the Virtual Office shell and project navigation. This change has no frontend interaction or layout scope; all 23 deterministic frontend/static scripts passed.

## Final release evidence

- Manual acceptance: `manual-acceptance.md` — project/task, execution, Review/rework/acceptance, Artifact, Cron degraded behavior, Git failure, concurrency, and token boundary.
- Rollout rehearsal: `rollout-rehearsal.md` — fixed medium fixture, active write, drain, rollback, backup restore, and exact counts/digests.
- Scenario traceability: `scenario-evidence.md` — every confirmed OpenSpec scenario mapped to implementation and executable/manual evidence.
- Bits remote UT was checked because the final gate requested tests; it is inapplicable because this repository has no `go.mod` or `.codebase/pipelines/ci.yaml` and is not a Go/Bits pipeline project.
