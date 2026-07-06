# Todolist

## TODO-001 Normalize Hermes Approval Choices

- 目标：Extend Hermes approval choice normalization to support `once`, `session`, `always`, and `deny`.
- 涉及区域：`app/server.py`
- 输入：Current `_normalize_hermes_approval_choice()` and approval response handler.
- 输出：A normalized choice helper with backward-compatible aliases for old `approve_once` flows.
- 依赖：None.
- 完成标准：All aliases map to the expected normalized values; invalid choices are rejected.
- 关联 checklist：CHK-001, CHK-014

## TODO-002 Preserve And Default Hermes Approval Choices

- 目标：Ensure native Hermes approval payloads expose the correct choices.
- 涉及区域：`app/server.py`, `tests/test_hermes_server_native_api.py`
- 输入：Native Hermes `approval.request` event payload.
- 输出：Approval objects that preserve Hermes-provided choices or default to `["once", "session", "always", "deny"]`.
- 依赖：TODO-001.
- 完成标准：Unit tests cover missing choices and restricted choices.
- 关联 checklist：CHK-003

## TODO-003 Forward Native Approval Scope To Hermes

- 目标：Pass `once`, `session`, `always`, or `deny` through to Hermes native API.
- 涉及区域：`app/server.py`, `app/providers/hermes.py`, `tests/test_hermes_server_native_api.py`
- 输入：User approval response from VO chat or Feishu action.
- 输出：`client.respond_approval(run_id, choice)` receives the normalized choice.
- 依赖：TODO-001, TODO-002.
- 完成标准：Tests verify all four choices are forwarded without collapsing to `once`.
- 关联 checklist：CHK-002, CHK-012, CHK-013

## TODO-004 Keep CLI Fallback Conservative

- 目标：Avoid claiming unsupported session/permanent authorization in CLI fallback approvals.
- 涉及区域：`app/server.py`, `app/providers/hermes.py`, Hermes approval tests.
- 输入：CLI approval detection path from `_detect_hermes_approval_request()`.
- 输出：CLI fallback approval choices limited to supported values, initially `["once", "deny"]`.
- 依赖：TODO-001.
- 完成标准：Tests confirm CLI fallback does not expose `session` or `always` unless explicit support is added.
- 关联 checklist：CHK-004

## TODO-005 Render VO Hermes Approval Choices Dynamically

- 目标：Render approval buttons from `approval.choices` in the VO chat UI.
- 涉及区域：`app/chat.js`, `app/locales/en.json`, `app/locales/zh.json`, CSS if needed.
- 输入：Approval payload with `choices`.
- 输出：VO chat approval card buttons for provided choices only.
- 依赖：TODO-002.
- 完成标准：Static/frontend tests verify full and restricted choice rendering; `always` is visually high risk.
- 关联 checklist：CHK-005, CHK-006, CHK-010

## TODO-006 Submit VO Approval Choice Without Downgrading

- 目标：Ensure VO chat submits the selected choice directly to backend.
- 涉及区域：`app/chat.js`, backend approval tests.
- 输入：User clicks `once`, `session`, `always`, or `deny` in VO chat.
- 输出：`/api/hermes/approval/respond` receives the selected choice.
- 依赖：TODO-001, TODO-005.
- 完成标准：Old `approve_once` still works, and new choices arrive at backend unchanged except normalization.
- 关联 checklist：CHK-006, CHK-014

## TODO-007 Build Feishu Hermes Approval Card

- 目标：Generate an actionable Feishu card for Hermes dangerous command approvals.
- 涉及区域：`app/feishu_notifications.py`, `app/server.py`, related Feishu notification helpers/tests.
- 输入：Standard Hermes approval object and Feishu notification config.
- 输出：Feishu card containing command, agent/run/session context, and one button per exposed choice.
- 依赖：TODO-002.
- 完成标准：Unit tests verify card payload and action values for full and restricted choices.
- 关联 checklist：CHK-007, CHK-010, CHK-011

## TODO-008 Send Feishu Approval Card With Dedupe

- 目标：Send the Feishu approval card when approval becomes pending, without duplicate sends.
- 涉及区域：`app/server.py`, Feishu notification record/dedupe helpers.
- 输入：Pending Hermes approval from native API or supported approval path.
- 输出：A Feishu approval notification sent once per `approval_id` when configured.
- 依赖：TODO-007.
- 完成标准：Tests cover enabled, disabled, missing config, and duplicate approval events.
- 关联 checklist：CHK-010, CHK-011

## TODO-009 Handle Feishu Approval Card Actions

- 目标：Make Feishu button clicks approve or deny the same Hermes approval.
- 涉及区域：`app/feishu_long_connection.py`, `app/server.py`, Feishu action routing/tests.
- 输入：Feishu card action payload with `action: hermes_approval_respond`.
- 输出：Callback delegates to `_handle_hermes_approval_respond()`.
- 依赖：TODO-001, TODO-003, TODO-007.
- 完成标准：Feishu callbacks for all supported choices return success or clear error and reuse backend state.
- 关联 checklist：CHK-008, CHK-012

## TODO-010 Make Cross-Surface Approval Idempotent

- 目标：Prevent duplicate Hermes approval responses from VO and Feishu.
- 涉及区域：`app/server.py`, approval pending queue, history helpers, Feishu callback tests.
- 输入：Same approval handled multiple times from one or both surfaces.
- 输出：Only the first valid response reaches Hermes; later attempts return already handled or expired.
- 依赖：TODO-003, TODO-009.
- 完成标准：Tests cover VO-first, Feishu-first, and repeated Feishu actions.
- 关联 checklist：CHK-009, CHK-010, CHK-013

## TODO-011 Record Audit Trail And Presence

- 目标：Record approval outcome consistently in history and presence.
- 涉及区域：`app/server.py`, `app/gateway_presence.py` if needed.
- 输入：Approval response result.
- 输出：History records normalized choice and resolved status; presence emits approval/cancel events.
- 依赖：TODO-003, TODO-010.
- 完成标准：Tests inspect history and presence payloads for accepted and denied approvals.
- 关联 checklist：CHK-013

## TODO-012 Update Tests And Regression Coverage

- 目标：Run and expand focused tests for Hermes approval and Feishu actions.
- 涉及区域：`tests/test_hermes_server_native_api.py`, `tests/test_feishu_notifications.py`, related JS static tests if present.
- 输入：Implementation from TODO-001 through TODO-011.
- 输出：Passing targeted test suite and new regression tests.
- 依赖：TODO-001 through TODO-011.
- 完成标准：All checklist-linked automated tests pass locally.
- 关联 checklist：CHK-001 through CHK-014

## TODO-013 Manual End-To-End Verification

- 目标：Verify real VO + Hermes native API + Feishu approval flow.
- 涉及区域：Running VO app, Hermes native API config, Feishu notification app.
- 输入：Configured test environment that can trigger a Hermes dangerous command approval.
- 输出：Manual verification notes for VO chat and Feishu action handling.
- 依赖：TODO-012.
- 完成标准：Manual test proves one surface can approve and the other surface does not duplicate the response.
- 关联 checklist：CHK-015
