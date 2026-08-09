# Task 12.15 — Remove Legacy HR Authorization Storage

Date: 2026-07-20

## Scope

- Removed `access_grants` from the final HR schema and management export allowlist.
- Removed `skill_readiness` and `grant_readiness` from Agent persistence and records.
- Removed all access-grant repository records, rotation, revocation, lookup, digest validation, and tests.
- Added transactional schema migration v3. Existing development databases lose the obsolete grant table, readiness columns, and stored grant rows while retaining Agent and HR domain records.
- Updated OpenSpec design, tasks, and review text so no compatibility promise remains for obsolete authorization data.

## Verification

| Scope | Command | Result |
|---|---|---|
| Schema migration, repository, governance, directory, trusted identity, team sync, management API, and HTTP contracts | `.venv/bin/python -m pytest -q tests/test_hr_repository_schema.py tests/test_hr_repository_governance.py tests/test_hr_repository_diagnostics.py tests/test_hr_directory_projection.py tests/test_hr_agent_auth.py tests/test_hr_team_sync.py tests/test_hr_management_api.py tests/test_hr_http_contract.py` | 105 passed in 2.22s |
| Complete HR Python plus VO communication regression | `.venv/bin/python -m pytest -q $(rg --files tests \| rg '/test_hr_.*\\.py$') tests/test_vo_agent_hr_skill.py tests/test_agent_communication_routing.py tests/test_agent_communication_skill.py tests/test_vo_agent_communication_service.py` | 469 passed in 9.74s |
| HR/Agent Guide Node static and pure-helper checks | explicit seven-script HR/Agent Guide list | 7 scripts passed; 167 locale keys validated |
| Python compilation | `.venv/bin/python -m compileall -q app/services` | passed |
| Broad Python regression excluding environment-bound workflow E2E and Claude Code provider suites | `.venv/bin/python -m pytest -q tests --ignore=tests/test_workflow_e2e.py --ignore=tests/test_claude_code_provider.py` | 1693 passed; 6 known unrelated baseline failures (Codex SSE, three Feishu state-isolation cases, reusable project validation, provider generated baseline) |
| OpenSpec | `openspec validate add-vo-human-resources-management --strict` | valid |

Development-machine acceptance tasks 13.4–13.10 remain open.
