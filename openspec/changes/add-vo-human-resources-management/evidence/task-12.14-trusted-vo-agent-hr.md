# Task 12.14 — Trusted VO Agent HR Evidence

Date: 2026-07-20

## Scope

- Renamed the canonical built-in skill from `vo-agent-directory` to `vo-agent-hr`.
- Removed runtime grant issuance, delivery, Provider allowlisting, and authorization-readiness projection.
- Kept legacy database grant schema and rows inert for upgrade compatibility.
- Required originless loopback, `X-VO-Agent-Action: human-resources`, and a registered active `X-VO-Agent-Id` for Agent HR reads.
- Preserved server-side public/self/full projection rules and atomic best-effort cross-Agent access logging.

## Verification

| Scope | Command | Result |
|---|---|---|
| Focused trusted identity, Provider-neutral team sync, HTTP, disclosure, UI management detail, and Skill contracts | `.venv/bin/python -m pytest -q tests/test_hr_agent_auth.py tests/test_hr_team_sync.py tests/test_hr_http_contract.py tests/test_hr_management_api.py tests/test_hr_directory_projection.py tests/test_hr_governance.py tests/test_hr_builtin_skill.py tests/test_vo_agent_hr_skill.py` | 91 passed in 2.76s |
| Complete HR Python plus VO communication regression | `.venv/bin/python -m pytest -q $(rg --files tests | rg '/test_hr_.*\\.py$') tests/test_vo_agent_hr_skill.py tests/test_agent_communication_routing.py tests/test_agent_communication_skill.py tests/test_vo_agent_communication_service.py` | 475 passed in 9.96s |
| HR/Agent Guide Node static and pure-helper checks | explicit seven-script HR/Agent Guide list | 7 scripts passed; 167 locale keys validated |
| Broad Python regression excluding environment-bound workflow E2E and Claude Code provider suites | `.venv/bin/python -m pytest -q tests --ignore=tests/test_workflow_e2e.py --ignore=tests/test_claude_code_provider.py` | 1695 passed; 6 known unrelated baseline failures (Codex SSE, three Feishu state-isolation cases, reusable project validation, provider generated baseline) |
| OpenSpec | `openspec validate add-vo-human-resources-management --strict` | valid |

The local Chrome CDP development/browser runtime was not started for this
follow-up. Real development-machine acceptance tasks 13.4–13.10 remain open.
