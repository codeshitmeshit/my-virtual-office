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
