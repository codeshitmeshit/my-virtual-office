# Section 1 whole-section CR

## Verdict

Pass. The Provider baseline is sufficient to begin the repository/event extraction. No blocking correctness, security, consistency, or test-validity finding remains.

## Scope reviewed

- deterministic caller/writer, route, state-authority, capability, event-alias, approval-bound, and transport-delegate evidence;
- exact ProviderRunBridge HTTP/SSE compatibility fixtures;
- Codex, Claude Code, Hermes, OpenClaw/chat-session, Project Execution, Meeting, and Feishu characterization commands;
- fixed 1/20/100 run and 10/1,000/4,000 event capacity/performance evidence;
- OpenSpec artifacts and task traceability.

## Findings and resolution

1. **Resolved — Meeting test used the wrong execution mode.** Direct script execution could not resolve the `app` package. The checked-in manifest now uses the repository virtual environment and pytest module execution; the complete manifest passes.
2. **Resolved — cancel-vs-complete was described but not exercised.** Added a barrier-based concurrent fixture that reproducibly exposes the current two-terminal race. Sections 2–4 must change this fixture to prove a single fenced terminal winner.
3. **Accepted baseline risk — approval authorities are unbounded.** Hermes and Codex aggregate pending approval collections have no explicit count cap. This is documented, tested as a required final-state gap, and assigned to Section 4.
4. **Accepted baseline risk — replay scans the global journal.** Current run/conversation replay examines the retained global deque. The exact 4,000 bound and scan count are recorded; Section 2 must add eviction-consistent scope indexes.
5. **Accepted baseline risk — mutable run snapshots.** `ProviderRunBridge.get` exposes its internal mutable dictionary. Section 2 must replace this with copied/immutable snapshots.

## Review dimensions

- **Correctness:** 21/21 manifest commands pass; route/result, lifecycle, history/native IDs, approval, cancellation, SSE replay/recovery, provider isolation, downstream ports, and capacity are represented.
- **Security:** generated evidence contains relative source locations and bounded fake-test output only; credential/private-key/absolute-user-path scan found no match. Cross-agent/session and notification redaction tests are included.
- **Consistency:** the inventory is generated from current source and `--check` reproduces all five artifacts exactly. Capability and event alias artifacts are separately asserted.
- **Test validity:** the known terminal race has a failing-before behavioral fixture instead of only a source assertion. Performance primary gates are counts/capacity; machine-sensitive latency is explicitly secondary evidence.
- **Baseline sufficiency:** current 4,000-event and 600,000-ms retention facts, provider path capabilities, state owners, transport candidates, and four known gaps are explicit and traceable to later tasks.

## Verification evidence

- `.venv/bin/python -u tests/run_provider_characterization_manifest.py --write-result` → 21/21 commands passed.
- `.venv/bin/python tests/test_provider_characterization.py` → 8/8 passed.
- `.venv/bin/python -m unittest tests.test_provider_baseline_inventory -v` → 7/7 passed.
- `.venv/bin/python tests/provider_baseline_harness.py --check` → passed.
- `.venv/bin/python tests/generate_provider_inventory.py --check` → 5 artifacts reproduced.
- `openspec validate extract-provider-services-and-finish-modularization --strict` → valid.
- `git diff --check` → no whitespace error in tracked diffs; all Section 1 files were also syntax-compiled below before advancing.

## Gate to Section 2

Proceed only with one repository/event authority behind compatibility delegates. Do not preserve any known baseline defect as desired behavior: the race, unbounded approvals, global replay scan, and mutable snapshots are explicit migration targets.
