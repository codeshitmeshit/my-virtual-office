## Task 7.3 Final Local Verification

Date: 2026-07-16

### Full Python regression

The raw command below was attempted first:

```bash
.venv/bin/python -m pytest -q tests
```

Collection stopped in the existing live `tests/test_workflow_e2e.py` because the running VO instance requires a management token. No test body ran in that attempt.

All non-live Python test modules were then run:

```bash
.venv/bin/python -m pytest -q $(rg --files tests -g 'test_*.py' | rg -v 'tests/test_workflow_e2e.py')
```

Final result after reconciliation: **725 passed in 56.93s**.

The first pass had two failures:

1. A Project test failed only while `TemporaryDirectory` was removing a directory still receiving a background write; its isolated rerun passed (`1 passed`). The final full rerun also passed it.
2. Provider generated inventory was stale because this change added Provider call edges and shifted source locations. It was refreshed with the repository generator, then verified exactly reproducible. The provider baseline suite passed `7/7`; the final full rerun passed it.

### Provider generated evidence and boundaries

```bash
.venv/bin/python tests/generate_provider_inventory.py --check
.venv/bin/python -m pytest -q \
  tests/test_provider_baseline_inventory.py \
  tests/test_provider_service_boundaries.py \
  tests/test_provider_execution_contract.py
```

Result: inventory verified for 5 artifacts; **20 passed in 12.72s**.

### Node worker

```bash
cd integrations/feishu-channel-worker
npm test
```

Result: **23 passed, 0 failed**. The expected injected reconnect test emitted one redacted `ENOTFOUND open.feishu.cn` warning and passed.

### Static JavaScript

All static `tests/check_*.mjs` and `tests/test_*.js` files except two known baseline failures were run; **34 passed**.

The two exclusions both fail at the pre-change reviewed commit and are unrelated to group chat:

- `tests/check_codex_runs_bridge.mjs`: current Codex success path contains the `loadHistory` call forbidden by that static assertion.
- `tests/test_weather_location_test_ui.js`: current `index.html` cache-busting token lacks the expected `weather-form-layout` suffix.

Feishu/history-specific static checks, `app/chat.js` syntax, and `tests/chat_history_ui_e2e.mjs` syntax passed.

### OpenSpec

```bash
openspec validate enable-feishu-group-chat --type change --strict --no-interactive --json
```

Result: **valid=true**, zero issues.

### Environment-gated checks

- `tests/test_workflow_e2e.py` requires a valid management token for the running VO instance.
- The in-app browser could initially open the local app, but repeated navigation/reload timed out; the deterministic browser acceptance was added and syntax-checked but was not reported as executed.
- Task 7.2 real-tenant Feishu group acceptance remains pending until the server is restarted on this change and a disposable trusted group is identified.

No change-caused local regression remains. The change is not ready for the test-result confirmation gate until Task 7.2 is completed.

The final review also fixed the settings rollback trap: selecting `legacy-python` now clears and disables a previously checked group switch, so saving the private-only rollback configuration does not fail on stale UI state.
