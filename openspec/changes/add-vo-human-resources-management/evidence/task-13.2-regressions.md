# Task 13.2 Regression Evidence

Date: 2026-07-19

## Scope and result

All required regression groups passed. The provider inventory was regenerated from a clean `HEAD` export so unrelated, uncommitted Codex launch-policy work in the shared working tree was neither incorporated nor staged.

| Regression group | Command summary | Result |
| --- | --- | --- |
| Archive Room Phase 1-8 and archive-manager Phase 4 | `.venv/bin/python -m pytest -q tests/test_archive_room_*.py tests/test_archive_manager_*.py` | 48 passed in 1.97s |
| Agent communication, managed skill/routing, project assignment/actor | `.venv/bin/python -m pytest -q tests/test_agent_communication_*.py tests/test_vo_agent_directory_skill.py tests/test_managed_skills.py tests/test_project_actors.py tests/test_project_execution_actor_eligibility.py tests/test_system_agent_project_policy_wiring.py tests/test_agent_workspace_project_context.py` | 62 passed in 0.82s |
| Meeting lifecycle and HR/service boundaries | `.venv/bin/python -m pytest -q tests/test_meeting*.py tests/test_hr_meeting_policy.py` | 155 passed in 9.34s |
| Provider compatibility and service boundaries | `.venv/bin/python -m pytest -q tests/test_provider*.py tests/test_codex_provider.py tests/test_claude_code_provider.py tests/test_chat_command_provider_controls.py` | 155 passed in 17.39s |
| Management-token HTTP contracts and static service boundaries | `.venv/bin/python -m pytest -q tests/test_project_authoring_http_management.py tests/test_project_authoring_http_contract.py tests/test_provider_service_boundaries.py tests/test_project_execution_service_boundary.py tests/test_project_service_static_boundaries.py tests/test_meeting_service_boundaries.py` | 57 passed in 15.34s |
| Management-token browser contract | `node tests/test_management_token_dialog.js` | passed |
| Full i18n integrity | `node tests/test_i18n_integrity.js` | 2429 keys and 1192 static references verified |
| Static modularity/UI checks | eight `check_*_static.mjs` and HR i18n/browser checks listed below | all passed |

Static checks executed:

- `node tests/check_agent_guide_static.mjs`
- `node tests/check_dashboard_realtime_static.mjs`
- `node tests/check_frontend_performance_static.mjs`
- `node tests/check_meeting_action_dedup_static.mjs`
- `node tests/check_project_action_dedup_static.mjs`
- `node tests/check_hr_ui_i18n.mjs`
- `node tests/check_hr_browser_acceptance_static.mjs`
- `node tests/check_chrome_cdp_scripts_static.mjs`

## Provider inventory correction

The first provider run reported one reproducibility failure because the checked-in ownership/event inventory predated the committed modularization and HR modules. A clean archive of `HEAD` was used to run `tests/generate_provider_inventory.py --write`; the two deterministic generated artifacts were refreshed and committed separately. The complete provider group then passed in that clean archive. This avoids treating unrelated working-tree files as accepted baseline input.

## Review notes

- No regression assertion was weakened or skipped.
- The initial shell glob for nonexistent `tests/test_management_token*.py` was rejected by zsh before Python ran; the intended exact management-token and boundary files were then executed explicitly and passed.
- Existing unrelated working-tree modifications remained unstaged.
