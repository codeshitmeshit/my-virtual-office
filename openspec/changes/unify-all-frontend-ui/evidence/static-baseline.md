# Task 1.1 · Static UI-system baseline

- Date: 2026-08-09 (Asia/Shanghai)
- Command: `.venv/bin/pytest -q tests/test_frontend_ui_system_contract.py`
- Result: expected baseline failure, `5 failed, 1 passed`
- Production files changed: none

## Confirmed baseline gaps

1. `app/ui-system.css` does not exist.
2. No frontend entry point loads the canonical foundation.
3. `app/style.css` references undefined `--text-primary` and `--ui-text-dim` without a fallback.
4. `app/fonts.css`, `app/project-orchestration.css`, and `app/window-controls.css` declare competing feature/font `:root` blocks.
5. `app/setup.html`, `app/models.html`, and `app/cron.html` embed standalone static stylesheets.
6. Recorded inline-style ceilings are: main `125`, setup `96`, models `15`, cron `35`, website `17`. The enforcement test rejects increases while later migration reduces the standalone counts.

These failures are the intended pre-implementation evidence for tasks 2.1, 2.2, 5.1, and 5.3. They must be resolved at the owning production layer rather than allowlisted away.
