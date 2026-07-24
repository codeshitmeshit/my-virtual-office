# Task 17 Local Integrated Regression

Date: 2026-07-24
Branch: `codex/merged-agent-management`

## 17.1 Focused Python

Result: **PASS — 243 passed in 2.99s**

Command:

```bash
.venv/bin/python -m pytest -q \
  tests/test_agent_profile_store.py \
  tests/test_agent_profile_configuration.py \
  tests/test_agent_profile_mutations.py \
  tests/test_agent_management_confirmations.py \
  tests/test_agent_management_executor.py \
  tests/test_agent_management_high_risk.py \
  tests/test_agent_legacy_mutation_policy.py \
  tests/test_agent_legacy_mutation_http.py \
  tests/test_agent_management_sessions.py \
  tests/test_agent_management_session_mint.py \
  tests/test_agent_management_session_mint_http.py \
  tests/test_agent_management_session_exchange.py \
  tests/test_agent_management_session_exchange_http.py \
  tests/test_agent_management_session_security.py \
  tests/test_agent_management_browser.py \
  tests/test_agent_management_browser_http.py \
  tests/test_agent_management_http.py \
  tests/test_agent_management_http_contract.py \
  tests/test_hr_agent_api.py \
  tests/test_hr_directory_projection.py \
  tests/test_hr_reporting_projection.py \
  tests/test_hr_governance.py \
  tests/test_hr_observability.py \
  tests/test_hr_http_contract.py \
  tests/test_hr_repository_governance.py
```

Coverage recorded:

- profile persistence, audience policy, field autosave mutation and bounded undo;
- exact payload-bound one-use confirmation challenges and high-risk execution;
- retained legacy route authorization and bypass denial;
- Agent launch-code/session mint, exchange, expiry, restart invalidation and browser projection;
- HR self/public/full projections, governance, audit/observability and HTTP delegation.

## 17.2 Focused Node, Static UI and Browser

Result: **PASS — 11 Node/static scripts, 13 Python UI tests, 1 Chrome acceptance**

The Node/static group covered:

- merged shell state, configuration component and Human/Agent adapters;
- English/Chinese locale integrity and dynamic HR copy;
- merged and nested-dialog keyboard/focus behavior;
- Human Resources controls, detail request ordering, overview degradation and management-token behavior;
- browser-fixture completeness and shared CDP configuration.

The Python UI group covered merged-modal semantics, unique close control,
responsive/reduced-motion rules, HR embedding and the absence of `_acp` or new
Agent Management implementation in `app/game.js`.

The deterministic Chrome acceptance passed with:

- human roster `2`, restricted human configuration present and one close control;
- selector Arrow-key movement and Escape focus return;
- explicit Agent/action/before/after high-risk impact with no generic Save button;
- Agent audience restricted DOM `0`, editable colleague fields `0`, human HR
  requests `0`, and hidden restricted response/DOM sentinel occurrences `0`.

## 17.3 Existing Domain Regressions

Result: **PASS for every specified domain**

Isolated domain groups:

| Domain | Result |
|---|---:|
| Archive Room Phase 1–8, AI refine, Archive Manager lifecycle/ownership | 48 passed |
| Meeting repository/lifecycle/requests/actions/Phase 1–8/boundaries | 160 passed |
| Projects, execution, authoring, scheduling, materialization and boundaries | 408 passed |
| Agent workspace/communication, system Agents, Provider paths/boundaries | 282 passed |
| Existing HR lifecycle, directory, reporting, assessment, schedule and UI contracts | 446 passed |
| Relevant project/meeting/workspace/Provider/management-token/i18n Node scripts | 20 passed |
| Provider generated-inventory and mutation-route characterization | 15 passed |

The broad Python invocation collected 2071 tests. It produced 2057 passes and
14 failures when run in one process. Thirteen failures (Claude Code `1`, Feishu
`3`, Hermes `2`, project execution `7`) all passed in fresh isolated pytest
processes and were caused by suite-global environment/background-thread
contamination. The remaining failure was a deterministic Provider inventory
staleness check caused by the newly added focused Python modules; the repository
generator refreshed the two current artifacts and its `--check` plus all seven
inventory tests pass.

`tests/test_workflow_e2e.py` was excluded from pytest collection because it
performs an import-time write to the live app and correctly failed without a
management token. Live behavior is covered only by the controlled Task 17.4
fixture and the separate development-machine gate.

The broad Node scan additionally identified two unrelated/non-hermetic entries:
`e2e_internal_bubble.js` requires a running CDP endpoint, while the weather cache
version assertion observes an uncommitted meeting/index change outside this
change. Neither was counted as a pass. The stale Codex import marker was updated
to assert both imported symbols without relying on their order on one line.
