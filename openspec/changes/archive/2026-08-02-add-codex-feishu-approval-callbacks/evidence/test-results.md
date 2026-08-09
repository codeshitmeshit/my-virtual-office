## Test result evidence

Date: 2026-07-17

### Automated verification

- `pytest -q tests/test_feishu_notifications.py tests/test_codex_feishu_approvals.py tests/test_codex_feishu_callbacks.py tests/test_codex_feishu_approval_integration.py tests/test_codex_server.py tests/test_codex_durable_events.py tests/test_codex_bridge.py tests/test_codex_provider.py tests/test_codex_fast_path_config.py tests/test_codex_fast_path_rollback.py tests/test_codex_coalescer_journal.py`
  - Result: 213 passed.
  - Covers notification-primary, Chat-App-only, primary failure fallback, duplicate/conflicting callbacks, queue/deadline/double-delivery failure closure, card fan-out/reconciliation, and VO history isolation.
- `npm test` in `integrations/feishu-channel-worker`
  - Result: 52 passed.
  - Covers strict card-action envelopes, callback authentication, bounded action spool, retry/replay, and worker protocol compatibility.
- `openspec validate add-codex-feishu-approval-callbacks --strict`
  - Result: valid.
- `git diff --check`
  - Result: clean for whitespace errors.

### Remaining manual verification

- A real Feishu test tenant is still required to confirm the notification application's `union_id` delivery permission and the visual resolved-card rendering. The specified fail-safe behavior for insufficient identity permission is covered automatically: primary delivery fails, Chat App fallback is attempted, and dual failure cancels the guarded action.
