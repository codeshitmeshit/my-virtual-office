# Task 9.1 Evidence: Deterministic Concurrency Regressions

## Scope

- Added `tests/test_project_orchestration_concurrency.py` as a focused regression suite for marked project orchestration races.
- Covered duplicate project start with two concurrent callers against the same repository lock.
- Covered duplicate terminal callbacks and simultaneous parallel completions advancing the stage exactly once.
- Covered completion-versus-pause so a pausing project never starts a later stage.
- Covered skip-approval-versus-completion so reconciliation advances once and stale callbacks are ignored.
- Covered stale auto-save losing to the authoritative current revision without mutation.
- Covered recovery-versus-live execution so live attempts are preserved and missing reserved attempts are resubmitted once.

## Key Contracts

- Duplicate starts produce one `stage_started` result and one `orchestration_not_startable` result.
- Concurrent terminal reconciliation produces one `stage_advanced` result and stale/idempotent duplicates.
- Pause wins block advancement while preserving later stages unstarted.
- Skip approval can satisfy a stage, but a later completion callback for the old run is stale.
- Stale modal auto-save returns `orchestration_revision_conflict` and preserves stored state.
- Startup recovery does not duplicate live attempts or duplicate recovered submissions.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_concurrency.py
```

Result: `6 passed in 0.22s`

```bash
.venv/bin/python -m pytest -q tests/test_project_stage_dispatch.py tests/test_project_orchestration_pause.py tests/test_project_orchestration_skip.py tests/test_project_orchestration_recovery.py tests/test_project_orchestration_commands.py
```

Result: `59 passed in 0.70s`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result before task status update: `Change 'add-project-task-orchestration' is valid`

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result after task status update: `Change 'add-project-task-orchestration' is valid`
