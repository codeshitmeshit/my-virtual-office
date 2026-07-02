# Feishu Meeting Request Actions Todolist

## TODO-001 - Verify current meeting request creation and website behavior

- 目标：确认现有需要人工确认的会议申请触发点、网站展示、确认/拒绝流程，作为不可改变的基线。
- 涉及区域：`app/server.py` meeting request handlers, project/task meeting request UI, existing meeting request tests.
- 输入：`requirement.md`、`review.md`、现有 `_handle_meeting_request_*` 逻辑。
- 输出：实现前基线说明和可复用 handler 清单。
- 依赖：无。
- 完成标准：明确哪些 handler 是权威业务入口；确认飞书接入不需要改变网站队列展示和原 API 语义。
- 关联 checklist：CHK-001, CHK-001A, CHK-009。

## TODO-002 - Ensure Feishu meeting request cards include the intended actions

- 目标：让需要人工确认的会议申请在发送飞书 application_form 时包含同意、拒绝、查看详情。
- 涉及区域：meeting request notification intent, Feishu notification card action definitions.
- 输入：现有 `_send_meeting_request_notification` 和 Feishu card rendering rules。
- 输出：会议申请卡片 action payload。
- 依赖：TODO-001。
- 完成标准：卡片包含同意、拒绝、查看详情；同意/拒绝携带 `confirm_meeting_request` / `reject_meeting_request` 和 `request_id`；查看详情有可用入口或明确降级。
- 关联 checklist：CHK-002, CHK-005。

## TODO-003 - Add a Feishu action dispatcher for meeting request actions

- 目标：在通用 Feishu card action handler 中识别会议申请动作，并分发到现有 VO 会议申请业务逻辑。
- 涉及区域：`_handle_feishu_card_action`, action value parsing, meeting request confirm/reject handlers.
- 输入：Feishu long-connection event body, action value, request ID。
- 输出：`confirm_meeting_request` 和 `reject_meeting_request` 的业务分发结果。
- 依赖：TODO-001, TODO-002。
- 完成标准：未知 action 仍走通用记录；会议 action 调用现有确认/拒绝语义；不新增独立审批状态机。
- 关联 checklist：CHK-003, CHK-004, CHK-009, CHK-010。

## TODO-004 - Return explicit Feishu toast results

- 目标：让飞书按钮反馈体现真实业务结果，而不是只返回“操作已收到”。
- 涉及区域：Feishu card action response construction, meeting action dispatcher result mapping.
- 输入：confirm/reject handler result, failure code/status.
- 输出：成功/失败 toast 文案。
- 依赖：TODO-003。
- 完成标准：同意成功返回已同意/已批准类文案；拒绝成功返回已拒绝类文案；不可处理返回明确失败原因。
- 关联 checklist：CHK-003, CHK-004, CHK-006, CHK-007。

## TODO-005 - Preserve stale action safety

- 目标：处理重复点击、已确认、已拒绝、缺失 request ID、不存在 request ID 等场景。
- 涉及区域：meeting action dispatcher, existing meeting request state validation.
- 输入：不同状态的 meeting request 和 Feishu action event。
- 输出：安全的 no-op/failure response and record outcome。
- 依赖：TODO-003, TODO-004。
- 完成标准：不会覆盖已有状态；不会创建错误会议；返回清晰 toast；记录失败原因。
- 关联 checklist：CHK-006, CHK-007, CHK-008。

## TODO-006 - Enrich Feishu action trace records with business outcome

- 目标：让记录能追踪谁在何时对哪个 meeting request 做了什么动作，结果是什么。
- 涉及区域：`feishu-card-actions.jsonl` record shape or adjacent recording helper.
- 输入：Feishu event user/message/chat fields, action value, dispatcher outcome。
- 输出：包含 outcome 的 action record。
- 依赖：TODO-003, TODO-004, TODO-005。
- 完成标准：记录包含 user、requestId、action、messageId/chatId、timestamp、business outcome；不包含 App Secret 或敏感配置。
- 关联 checklist：CHK-008, CHK-011。

## TODO-007 - Add focused tests for Feishu approve/reject meeting request actions

- 目标：用自动化测试覆盖飞书按钮同意/拒绝到 VO meeting request 状态更新。
- 涉及区域：`tests/test_feishu_notifications.py`, `tests/test_meeting_for_ai_phase4.py`, or new focused test file.
- 输入：synthetic Feishu card action payloads, pending meeting request fixtures.
- 输出：同意/拒绝 happy-path tests。
- 依赖：TODO-003, TODO-004。
- 完成标准：模拟 `confirm_meeting_request` 后状态更新且 toast 正确；模拟 `reject_meeting_request` 后状态更新且 toast 正确。
- 关联 checklist：CHK-003, CHK-004, CHK-007。

## TODO-008 - Add stale and invalid action tests

- 目标：覆盖重复点击、状态冲突、缺失/错误 request ID 等边界。
- 涉及区域：Feishu action dispatcher tests, meeting request state fixtures.
- 输入：confirmed/rejected/nonexistent/malformed request action payloads。
- 输出：边界测试。
- 依赖：TODO-005。
- 完成标准：每个边界场景返回清晰失败或 no-op；状态未被破坏；记录包含失败 outcome。
- 关联 checklist：CHK-006, CHK-008。

## TODO-009 - Run regression tests for existing meeting request behavior

- 目标：证明飞书接入不改变原网站会议申请逻辑。
- 涉及区域：existing meeting request and project execution tests.
- 输入：现有测试命令。
- 输出：回归测试结果。
- 依赖：TODO-001, TODO-003, TODO-007, TODO-008。
- 完成标准：现有会议申请创建、网站/API 确认、网站/API 拒绝、任务阻塞/恢复行为保持通过；若有既有非相关失败，明确记录。
- 关联 checklist：CHK-001A, CHK-009。

## TODO-010 - Run Feishu notification regression tests

- 目标：确认通用飞书通知模块和长连接 callback 不被会议申请接入破坏。
- 涉及区域：Feishu notification tests, long connection event conversion tests.
- 输入：现有 Feishu notification test suite。
- 输出：测试结果记录。
- 依赖：TODO-003, TODO-004, TODO-006。
- 完成标准：四类通知、普通 card action logging、长连接 response 仍通过；未知 action 不被会议 dispatcher 误处理。
- 关联 checklist：CHK-010, CHK-011。

## TODO-011 - Update requirement checklist with implementation results

- 目标：开发完成后将 checklist 每项的验证结果写回需求归档。
- 涉及区域：`.cosh-docs/requirment/feishu-meeting-request-actions/checklist.md`, `status.json`.
- 输入：TODO-007 至 TODO-010 的测试和验收结果。
- 输出：实现验证记录。
- 依赖：TODO-007, TODO-008, TODO-009, TODO-010。
- 完成标准：CHK-001 至 CHK-012 都有通过、跳过或风险说明；状态推进到 implementation_done 并等待用户测试确认。
- 关联 checklist：CHK-001, CHK-001A, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012。

## TODO-012 - Perform manual production acceptance

- 目标：在生产或等价环境中验证真实飞书会议申请卡片和按钮处理。
- 涉及区域：production Feishu app config, real or controlled meeting request flow.
- 输入：一个需要人工确认的会议申请。
- 输出：人工验收记录。
- 依赖：TODO-007, TODO-008, TODO-009, TODO-010。
- 完成标准：网站仍显示会议申请；飞书同时收到卡片；飞书同意/拒绝能更新 VO 状态；记录可追踪；用户确认测试通过。
- 关联 checklist：CHK-001, CHK-001A, CHK-002, CHK-003, CHK-004, CHK-008, CHK-012。
