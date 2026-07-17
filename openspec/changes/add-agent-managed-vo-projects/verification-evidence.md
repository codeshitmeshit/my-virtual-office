# Verification Evidence

## Task 9.2 — Focused verification matrix

Run on 2026-07-18 from `/Users/bytedance/cosh/my-virtual-office` against implementation commit `805e7e6` and its ancestors.

Aggregate command: `.venv/bin/pytest -q` over the focused files listed below.

Result: **145 passed in 2.50s**.

| Verification domain | Test files | Result |
| --- | --- | --- |
| Project commands | `tests/test_project_commands.py` | 7 passed |
| Repository and bounded root storage | `tests/test_project_repository.py`, `tests/test_project_authoring_store.py` | 27 passed |
| Management-token boundary | `tests/test_project_authoring_http_management.py`, `tests/test_project_authoring_http_contract.py` | 13 passed |
| Request-secret boundary | `tests/test_project_authoring_http_agent.py`, `tests/test_project_authoring_security.py` | 4 passed |
| Project Execution actor eligibility | `tests/test_project_execution_actor_eligibility.py` | 3 passed |
| Versioned templates and compatibility | `tests/test_project_templates.py`, `tests/test_project_template_compatibility.py` | 6 passed |
| Schedule and legacy cron behavior | `tests/test_project_schedule_service.py`, `tests/test_project_scheduled_cron_phase1.py` through `phase5.py` | 37 passed |
| Capacity limits and disabled flags | `tests/test_project_authoring_config.py` | 4 passed |
| Counters, durations, logs, health, queue age, alerts | `tests/test_project_authoring_observability.py` | 3 passed |
| Authoring service, validation, and audit | `tests/test_project_authoring_service.py`, `tests/test_project_authoring_validation.py`, `tests/test_project_authoring_audit.py` | 41 passed |

Every domain was also rerun separately; all results above passed with no retry or deselection. The management HTTP group includes the authenticated health endpoint and verifies that secret hashes and claim tokens are absent from its response. The request-secret group verifies hash-only persistence and request/Agent scope. The execution-role group verifies that local-user execution remains trackable but cannot start automated execution.
