# Checklist

确认状态：已确认

## Acceptance Checklist

### CHK-001 Choice Normalization

- 关联需求：REQ-001, REQ-002
- 验证方法：Unit test `_normalize_hermes_approval_choice()` with `once`, `session`, `always`, `deny`, `approve_once`, `approve`, `allow_once`, `approve_session`, `allow_session`, `approve_always`, `allow_always`, `cancel`, `no`, and `denied`.
- 预期结果：All aliases map to the expected normalized value; unsupported choices are rejected by the approval respond handler.

### CHK-002 Native Hermes Choice Forwarding

- 关联需求：REQ-003
- 验证方法：Use a fake `HermesApiClient` and call `_handle_hermes_approval_respond()` for `once`, `session`, `always`, and `deny`.
- 预期结果：`respond_approval(run_id, choice)` receives the same normalized choice and does not collapse approvals to `once`.

### CHK-003 Native Approval Payload Choices

- 关联需求：REQ-004
- 验证方法：Unit test `_hermes_api_approval_from_event()` with an event that has no choices and with an event that provides a restricted choices list.
- 预期结果：Missing choices default to `["once", "session", "always", "deny"]`; provided choices are preserved exactly after safe normalization.

### CHK-004 CLI Fallback Scope Safety

- 关联需求：REQ-005
- 验证方法：Simulate CLI fallback approval detection and inspect generated approval choices.
- 预期结果：CLI fallback exposes only supported choices, initially `["once", "deny"]`, and does not claim session or permanent authorization.

### CHK-005 VO Chat Dynamic Buttons

- 关联需求：REQ-006, REQ-010
- 验证方法：Static/frontend test approval card rendering with choices `["once", "session", "always", "deny"]` and with `["deny"]`.
- 预期结果：Buttons match the provided choices; `always` is rendered with warning/danger treatment; restricted choices do not show hidden allow actions.

### CHK-006 VO Chat Approval Submission

- 关联需求：REQ-006, REQ-008
- 验证方法：Frontend test or static check that `respondHermesApproval()` submits the selected normalized choice and still supports old `approve_once`.
- 预期结果：The backend receives the selected choice; old approval cards still work through compatibility mapping.

### CHK-007 Feishu Approval Card Generation

- 关联需求：REQ-007, REQ-010
- 验证方法：Unit test Feishu approval card generation with the four Hermes choices and with restricted choices.
- 预期结果：Card contains the correct command, agent, run/session identifiers, and one action button per exposed choice; `always` is clearly marked as high risk.

### CHK-008 Feishu Callback Reuses Hermes Handler

- 关联需求：REQ-008
- 验证方法：Unit test Feishu card action callback for `hermes_approval_respond`.
- 预期结果：Callback delegates to `_handle_hermes_approval_respond()` and returns a clear success, denial, or already-handled result.

### CHK-009 Idempotent Cross-Surface Handling

- 关联需求：REQ-009
- 验证方法：Handle the same approval from VO first, then Feishu; repeat with Feishu first, then VO.
- 预期结果：Hermes receives only one approval response. The second action returns already handled or expired without duplicate side effects.

### CHK-010 Feishu Notification Dedupe

- 关联需求：REQ-007, REQ-009
- 验证方法：Trigger repeated `_remember_hermes_approval_pending()` or repeated progress events for the same `approval_id`.
- 预期结果：Only one Feishu card is sent for that approval.

### CHK-011 Feishu Disabled Behavior

- 关联需求：REQ-007
- 验证方法：Run approval flow with Feishu notifications disabled or missing app/webhook configuration.
- 预期结果：VO chat approval still works; no Feishu send is attempted or the result is recorded as skipped without failing the Hermes approval flow.

### CHK-012 Hermes Error Propagation

- 关联需求：REQ-003, REQ-010
- 验证方法：Fake Hermes native API rejects `session` or `always`.
- 预期结果：VO and Feishu callback return a visible error, the approval is not marked as successfully handled unless Hermes accepted it, and the pending state remains recoverable or clearly resolved as failed.

### CHK-013 History And Presence Audit

- 关联需求：REQ-008, REQ-009
- 验证方法：Respond to approval and inspect Hermes history plus gateway presence event.
- 预期结果：History records the approval choice and resolved status; presence emits `approval.responded` for accepted approvals and cancellation/denial for deny.

### CHK-014 Regression For Existing Approve Once

- 关联需求：REQ-002
- 验证方法：Run existing Hermes native API approval tests and add a compatibility test using `approve_once`.
- 预期结果：Existing approve-once behavior continues to pass.

### CHK-015 Manual End-To-End Verification

- 关联需求：REQ-001 through REQ-010
- 验证方法：With Hermes native API and Feishu notification configured, trigger a dangerous command approval in Hermes.
- 预期结果：VO chat and Feishu show matching approval options; choosing one option from either surface resumes or denies the Hermes run; the other surface does not cause duplicate handling.

## 人工确认记录

- 确认项：checklist 初次确认
- 确认时间：2026-07-06T13:48:17+08:00
- 用户确认摘要：用户回复 "continue"，确认进入 todolist 生成阶段。
