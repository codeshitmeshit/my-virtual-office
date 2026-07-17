## 1. Extend the common Feishu notification framework

- [x] 1.1 Extend application-card sends to return the Feishu `messageId`, add a generic authenticated card-update helper that reuses the existing intent builder, token cache, redaction, and notification audit, and cover send/update success and failure compatibility in `tests/test_feishu_notifications.py`.

## 2. Add durable Codex approval routing state

- [x] 2.1 Implement a bounded, TTL-pruned Codex Feishu approval route repository and coordinator-domain state transitions for register, delivery attempts, durable claim, commit, replay, failure, expiry, and delivery references, with concurrency and recovery tests that prove provider decisions are at most once.

## 3. Build approval intents and primary/fallback routing

- [x] 3.1 Build redacted Codex `application_form` intents for command, file-change, and permission approvals; freeze the trusted Feishu origin; route through the notification application using the original user's transferable identity; and fall back through the same common notification sender using Chat App credentials and the originating chat id, with a complete routing-matrix test.

## 4. Receive Chat App card actions

- [x] 4.1 Add a strictly validated, token-authenticated Chat App `cardAction` envelope and a bounded approval-action spool to the Node Channel SDK worker, forward it to a dedicated loopback endpoint without using the normal inbound-message path, and add worker protocol, retry, replay, size-limit, and authentication tests.

## 5. Resolve Codex approvals from Feishu exactly once

- [x] 5.1 Add Codex actions to the shared Feishu card-action dispatcher; verify callback actor and route linkage; claim and resolve approve-once/cancel exactly once; return stable replay, busy, stale, and unauthorized outcomes; and add callback security/idempotency tests.

- [x] 5.2 Add a source-aware Codex approval response persistence policy so Feishu-card decisions skip synthetic approval chat/communication messages while retaining provider events and separate approval audit, with regression tests proving Web Chat behavior and normal final replies remain unchanged.

## 6. Integrate asynchronous delivery and failure closure

- [x] 6.1 Register eligible approvals from the live Codex turn context and dispatch delivery on a bounded executor without blocking the app-server event reader; on queue saturation, deadline, or both delivery paths failing, cancel the guarded action exactly once and return a normal visible terminal failure through the originating turn, with timeout, saturation, and double-failure tests.

- [x] 6.2 Give pending/resolving approval state precedence in Codex presence projection until resolution, failure, turn terminal, or explicit cancellation, and add a regression test proving unrelated later activity cannot overwrite waiting-for-approval as idle.

## 7. Reconcile cards, audit, and recovery

- [ ] 7.1 Fan out resolved/failed/expired intent updates to every known primary and fallback card using the common update helper; add bounded/rotated linked notification and card-action audit records plus metrics; and test update failure isolation, ambiguous dual delivery, startup reconciliation, and stale-card behavior.

## 8. Validate the complete feature and document operations

- [ ] 8.1 Add focused server integration tests for notification-primary, Chat-App-only, fallback, duplicate/conflicting callbacks, undeliverable approval closure, and VO chat-history isolation; run the affected Python and Node test suites plus strict OpenSpec validation and record the evidence for the test-result gate.

- [ ] 8.2 Document configuration, original-user identity selection, callback transport, audit/metrics, gray rollout, failure diagnosis, and rollback behavior, including that interactive approvals do not use webhook or the configured fixed notification recipient.
