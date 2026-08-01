# Local verification evidence

Date: 2026-08-01

Scope: local implementation and regression evidence only. Production-only acceptance tasks 9.2–9.4 remain open.

## Focused verification

- `.venv/bin/python -m pytest -q --tb=short tests/test_feishu_notification_topics.py`
  - Result: 40 passed.
  - Covers notification-App event normalization, p2p/topic admission, authenticated root lookup, durable binding, bounded XML context, pinned Agent selection, ordering, idempotency, queue pressure, restart fencing/recovery, Provider-neutral bridge use, topic-native replies, attachments, preflight safety, and approval placement.
- `.venv/bin/python -m pytest -q --tb=short tests/test_feishu_notification_topics.py tests/test_codex_feishu_approvals.py tests/test_codex_feishu_approval_integration.py tests/test_provider_conversations.py tests/test_feishu_chat_commands.py`
  - Result: 79 passed.
- `.venv/bin/python -m pytest -q --tb=short tests/test_feishu_notifications.py tests/test_chat_slash_commands_characterization.py tests/test_feishu_notification_topics.py`
  - Result: 120 passed.
  - Confirms existing notification sends/updates, current slash-command policy, and the new topic path together.
- `npm test -- --test-reporter=spec` in `integrations/feishu-channel-worker`
  - Result: 52 passed, 0 failed.
  - Confirms the separately configured Chat App worker and group/mention behavior remain unchanged.
- `openspec validate add-feishu-topic-conversations --strict`
  - Result: valid.
- Python compilation of all touched Python modules and `git diff --check`
  - Result: passed.

## Wider regression evidence

- `.venv/bin/python -m pytest -q --tb=short tests/test_feishu_notifications.py`
  - Result: 76 passed.
  - Two stale assertions were aligned with the already-shipped XML group-prompt contract; no runtime behavior changed.
- `.venv/bin/python -m pytest -q --tb=short tests/test_chat_slash_commands_characterization.py`
  - Result: 4 passed.
  - The characterization reflects the latest main-branch ordinary-delivery and idempotency contract for unknown slash-like messages; no runtime behavior changed.
- Repository-wide `.venv/bin/python -m pytest -q --tb=short`
  - Collection is blocked by root-level `test_review_parser.py` calling `sys.exit(0)` during import.
- Directory-wide `.venv/bin/python -m pytest -q --tb=short tests`
  - Collection is blocked by an unset `VO_CLAUDE_CODE_REPLY_TEXT` required by `tests/test_claude_code_server.py` and by `tests/test_workflow_e2e.py` requiring a live management token.
- Directory-wide run with those two external collectors excluded
  - Result: 2,393 passed, 102 failed.
  - Failures are existing, broad shared-state/order baselines outside this change (archive, HR, meetings, project, and similar surfaces). The isolated Feishu suites above pass from a clean process.
- Additional route/provider regression selection
  - Result: 54 passed, 1 unrelated existing meetings-route failure caused by a mock that does not accept the current `summary=` keyword.

## Code-review corrections made before acceptance

- Normalize nested sender IDs from the notification long-connection projection so approval actor authorization remains intact.
- Reuse the durable topic binding when a later Feishu event omits `rootId`, while rejecting conflicting explicit roots.
- Require an explicit human `sender_type=user` and tolerate malformed event timestamps.
- Fence recovery ownership, recover only stale processing records, and keep all recovery inert while the feature flag is disabled.
- Keep the read-only preflight free of read-repair writes.
- Prevent notification-topic approval cards from falling back to the main bot DM or the separately configured Chat App.
- Preserve the feature flag when legacy configuration clients omit the new field.
- Validate the replaceable Agent-selection policy before durable binding creation and pin the selected Agent atomically.
- Claim the one-time activation acknowledgement before delivery, classify delivery exceptions, and retain the persisted Agent outcome when final reply delivery fails.
- Serialize concurrent first-message admission so the topic creator remains the first dispatched turn while keeping Provider execution outside the short admission lock.

## Read-only production observation

- A user-identity Feishu read of the message identifier visible in the supplied screenshot succeeded without sending or modifying data.
- The referenced message is a human-authored text request in a real `p2p` conversation, not the notification App's long-running-diversion root message. It therefore cannot be used as task 9.2 evidence or passed off as a successful root preflight.
- The local historical notification index contains only the older record shape and produces a safe `unverified` preflight result; a deployed production instance and an explicitly selected notification root are still required.

## Production gates still required

- 9.2: deploy disabled and inspect one explicitly selected, redacted production long-running notification shape through preflight.
- 9.3: enable one selected notification and verify no-`@` p2p topic continuation, independent conversation state, bounded context, pinned Agent, ordering, and topic-local output.
- 9.4: disable the flag and verify activation stops without affecting existing notification, card-action, Chat App, or group behavior.
