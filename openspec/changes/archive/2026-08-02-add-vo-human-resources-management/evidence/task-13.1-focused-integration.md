# Task 13.1 — Focused Human Resources Integration Evidence

- Date: 2026-07-19 (Asia/Shanghai)
- Baseline commit: `73c8f50411a5c4800f12e94ae6751d1a8c27bb53`
- Environment: local workspace Python virtual environment and Node.js 20.20.2
- Scope: shared system-Agent lifecycle plus HR lifecycle, repository, directory, introduction, skill/grant, reporting, assessment, scheduler, governance, application APIs, HTTP boundary, runtime wiring, and UI helpers/static contracts

## Python integration suite

Command:

```text
.venv/bin/python -m pytest -q tests/test_hr*.py tests/test_system_agent*.py
```

Result:

```text
547 passed in 8.50s
real 8.94s
```

This run includes migration and transaction tests, concurrent claim/grant/access-log tests, disclosure-negative tests, scheduler and DST tests, application/HTTP security tests, lifecycle compatibility tests, and HR UI shell static assertions. No assertion was skipped or weakened.

## Node.js UI/static suite

Commands executed in sequence:

```text
node tests/check_hr_browser_acceptance_static.mjs
node tests/check_hr_ui_i18n.mjs
node tests/test_hr_accessibility_ui.mjs
node tests/test_hr_overview_ui.mjs
node tests/test_hr_detail_ui.mjs
node tests/test_hr_controls_ui.mjs
```

Result:

```text
6/6 scripts passed
144 HR locale keys verified in English and Chinese
real 0.19s
```

The Node suite verifies the deterministic browser fixture contract, localization completeness, focus trap/Escape/focus return, overview prioritization and degraded reads, stale detail response rejection, independent pagination merge, command confirmation, and data retention after command failure.

## Outcome

All focused integration suites passed. Live CDP execution and screenshots are intentionally tracked separately by task 13.3; this evidence does not claim that development-machine OpenClaw integration has run.
