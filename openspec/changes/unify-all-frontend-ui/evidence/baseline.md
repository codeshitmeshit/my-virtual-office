# Task 1.2 · Frontend behavior baseline

- Date: 2026-08-09 (Asia/Shanghai)
- Change: `unify-all-frontend-ui`
- Production files changed: none

## Python frontend/UI characterization

Command:

```text
.venv/bin/pytest -q tests/test_agent_management_ui.py tests/test_hr_ui_shell.py tests/test_meeting_center_ui.py tests/test_project_orchestration_css.py tests/test_project_orchestration.py tests/test_mcp_registry_ui_contract.py tests/test_branch_agent_selector_ui.py tests/test_archive_room_phase_1_3.py tests/test_archive_room_phase_8.py
```

Result: `60 passed`.

Human-decision continuation imports require both repository and `app/` roots in `PYTHONPATH` because the current module graph mixes `app.services.*` and `services.*` imports:

```text
PYTHONPATH=.:app .venv/bin/pytest -q tests/test_human_decision_meeting_continuation.py
```

Result: `3 passed`. The initial collection error without this environment is an existing test-environment requirement, not a product failure.

## Browser JavaScript characterization

All of the following passed when run individually with `node`:

- `tests/test_settings_modal_ui.js`
- `tests/test_settings_save_feedback.js`
- `tests/test_settings_save_transport.js`
- `tests/test_main_menu_settings_save.js`
- `tests/test_meeting_center_mobile_layout.js`
- `tests/test_meeting_center_runtime.js`
- `tests/test_meeting_history_card_layout.js`
- `tests/test_skill_library_organization_ui_states.js`
- `tests/test_skill_library_organization_ui_static.mjs`
- `tests/test_personal_assets_availability.mjs`
- `tests/test_personal_assets_i18n.mjs`
- `tests/test_office_branding.js`

The baseline therefore covers settings save behavior, settings feedback/transport, management, HR, project orchestration, meeting runtime and mobile layout, archive room, human-decision continuation, Skills organization, MCP/branch selection, Personal Assets, and office branding.

## Local routes and visual capture

- `http://127.0.0.1:8090/` -> HTTP 200
- `http://127.0.0.1:8090/setup` -> HTTP 200
- `http://127.0.0.1:8090/models` -> HTTP 200
- `http://127.0.0.1:8090/cron` -> HTTP 404 (the current page is exposed by a different route; production HTML still exists at `app/cron.html`)
- OpenSpec dashboard -> HTTP 200

Headless Google Chrome was available but did not finish screenshot capture in this environment (`Trying to load the allocator multiple times` followed by a hung browser process). No screenshot file was produced. This is recorded as a tooling limitation; task 6.2 must use the available interactive browser or a working screenshot runner for final visual acceptance.
