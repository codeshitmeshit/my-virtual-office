# Task 12.16 Evidence — Automatic reporting and page schedule

Date: 2026-07-20
Environment: local macOS workspace; fake/injected Agent conversations only

## Implemented behavior

- The production HR application runtime now constructs and installs the automatic scheduler loop instead of starting an empty runtime holder.
- Automatic and manual cycle paths use the same durable collection, HR normalization, and assessment services.
- Open, close, retry, and restarted closed-cycle reconciliation normalize every raw report that lacks normalized data before assessment; one normalization failure remains scoped to that Agent and stays retryable.
- A shared `PeriodicTimer` owns resident callback timing for both HR and project recurrence; HR and project domain state remain the durable scheduling authorities.
- Human Resources owns a persisted schedule setting in HR SQLite. A repository with no saved setting defaults to enabled at `18:00`; authenticated management UI/API updates take effect on the next tick without restart.
- The Human Resources overview exposes schedule enablement, saved time, timezone, and next occurrence, and provides accessible time/enable/save controls.

## Verification

- Focused Python plus project recurrence/cron compatibility: `508 passed in 12.88s`.
- HR UI/static Node checks: all seven selected scripts passed, including controls, overview, i18n/accessibility, detail pagination, browser fixture, and Agent guide checks.
- Focused schedule/automatic pipeline/API/UI rerun: `61 passed in 2.12s`; all three selected Node checks passed.
- Python compilation succeeded for the changed service and server modules.
- Broad repository run excluding the live `test_workflow_e2e.py` collector: `1717 passed, 8 failed`; six failures match the pre-existing unrelated Codex SSE, Feishu isolation, reusable-project validation, and generated provider-inventory baseline failures. The two additional order-sensitive failures (Claude native-Agent discovery and project-execution temporary-directory cleanup) both passed immediately when rerun together (`2 passed`).
- Running unfiltered repository-root pytest remains unsuitable because the legacy root `test_review_parser.py` exits during collection; the live workflow E2E collector also requires a matching management token.

## Acceptance boundary

This is local deterministic evidence only. It does not satisfy tasks 13.4–13.10 or claim real development-machine/OpenClaw acceptance.
