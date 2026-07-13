# Section 3 whole-group code review

## Verdict

Section 3 is accepted for progression to Section 4. Codex and Claude Code run ownership has moved to `ProviderRunCoordinator`; provider-native parsing and protocol calls remain in their adapters/handlers. Atomic reservation, terminal fencing, cancellation, timeout, compatibility projection, and bounded diagnostics have focused and compatibility coverage.

## Ownership and behavior review

- `ProviderRunRepository` remains the only run/idempotency authority; the coordinator reserves before launch and never calls a slow adapter while holding a repository lock.
- Codex and Claude Code starts use `RunCommand` plus capability-checked adapters. Their legacy response fields, provider paths, queues, polling, SSE, history/native identifiers, and unmanaged-run fallbacks remain available through compatibility delegates.
- Same-scope concurrent starts launch exactly one adapter. Different scopes run concurrently. Completion, cancellation, timeout, and late adapter results share one fenced terminal path and publish exactly one terminal event.
- Provider failures and diagnostics are bounded and sanitized. Explicit adapters lacking background-run capability fail before creating partial repository state.

## Confirmed findings resolved

1. **Legacy run queues missed coordinator events.** Coordinator publication now projects canonical journal events into the existing per-run queue without making that queue an authority.
2. **Cancellation failure could be mislabeled as cancellation.** Failed provider cancellation now commits `run.failed`; it cannot claim a successful cancelled terminal.
3. **Explicit adapters bypassed capability validation.** All resolved or directly supplied adapters now require matching provider kind/path and background-run capability before reservation.
4. **A blocking provider cancel hook could delay a timeout terminal indefinitely.** Timeout now commits its fenced failure first and invokes provider cleanup asynchronously. A failing-before-style blocking-cancel regression proves the run becomes terminal within its deadline and late results remain fenced.
5. **Generated ownership evidence could become stale after migration.** Current evidence is regenerated deterministically before the reproducibility gate; the frozen baseline remains unchanged.

## Regression evidence

- Python compatibility group: **467 passed**, with two existing third-party deprecation warnings.
- JavaScript/static compatibility checks: **11/11 passed**.
- Characterization manifest: **21/21 passed**.
- Coordinator unit/concurrency tests: **12/12 passed**, including duplicate starts, independent scopes, cancel-vs-complete, cancellation failure, timeout, blocking cancellation, late-result fencing, launch/capability failure, and bounded diagnostics.
- Fixed coordinator performance: 1/20/100 runs produced exactly 1/20/100 launches, registered runs, terminal runs, and terminal events; all active handle counts returned to zero. Total fixture time was approximately 1.45/4.70/20.06 ms in the recorded run.
- Generated inventory reproducibility passed after refresh.
- `git diff --check` passed.
- `openspec validate extract-provider-services-and-finish-modularization --strict` passed.

## Non-blocking observations

- Two warnings originate in `lark_oapi` (`utcfromtimestamp` deprecation and event-loop lookup) and are unrelated to this migration.
- The first broad regression observed a temporary-directory cleanup race in a Project Execution test; its isolated rerun passed, and the clean full rerun subsequently passed all 467 tests.
