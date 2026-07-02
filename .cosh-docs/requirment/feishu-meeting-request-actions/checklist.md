# Feishu Meeting Request Actions Checklist

确认状态：已确认

## Checklist

### CHK-001 - Existing human-required meeting requests send Feishu application cards

- 关联需求点：以当前已经需要人工申请的会议为触发范围。
- 验证方法：创建一个现有流程中需要人工确认的会议申请，并检查 Feishu notification intent/card。
- 预期结果：该请求通过通用 Feishu 消息模块发送 application_form 卡片；不扩展到所有普通会议事件。

### CHK-001A - Existing website meeting request behavior is unchanged

- 关联需求点：原来网站上的会议申请展示和处理逻辑不变，飞书只是额外提醒和快捷确认通道。
- 验证方法：创建需要人工确认的会议申请，检查 VO 网站会议申请队列、详情、确认、拒绝流程。
- 预期结果：网站展示、状态流、确认/拒绝入口和原有业务规则不因飞书接入发生变化。

### CHK-002 - Meeting request cards expose Agree, Reject, and View Details actions

- 关联需求点：飞书卡片包含同意、拒绝、查看详情。
- 验证方法：检查会议申请 Feishu 卡片 actions。
- 预期结果：卡片包含同意、拒绝、查看详情；同意/拒绝携带 `request_id` 和明确 action value。

### CHK-003 - Agree from Feishu approves the VO meeting request

- 关联需求点：飞书可直接完成常见同意决策。
- 验证方法：创建 pending meeting request，模拟 Feishu `confirm_meeting_request` card action。
- 预期结果：请求状态变为 confirmed/approved 等现有 VO 成功状态，并启动转换后的 executable meeting；返回 Feishu 成功 toast；不会绕过现有确认规则。

### CHK-004 - Reject from Feishu rejects the VO meeting request

- 关联需求点：飞书可直接完成常见拒绝决策。
- 验证方法：创建 pending meeting request，模拟 Feishu `reject_meeting_request` card action。
- 预期结果：请求状态变为 rejected；返回 Feishu 成功 toast；若 Feishu 未提供原因，使用可追踪的默认拒绝原因。

### CHK-005 - View Details keeps a path back to VO context

- 关联需求点：复杂场景仍引导回 VO 查看上下文。
- 验证方法：检查 View Details action 的存在和行为。
- 预期结果：用户能从卡片进入或定位到相关 VO 项目/任务/会议申请上下文；若当前没有深链能力，应明确降级为可理解的查看入口。

### CHK-006 - Stale or already-processed actions do not corrupt state

- 关联需求点：已处理、过期、状态变化时返回清晰失败提示。
- 验证方法：对已 confirmed、已 rejected、缺失 request_id、不存在 request_id 的卡片动作重复点击。
- 预期结果：系统返回清晰失败或 no-op toast；不会覆盖已有状态；日志记录失败原因。

### CHK-007 - Feishu action result is explicit, not generic only

- 关联需求点：点击后反馈“已同意/已拒绝”等明确业务结果。
- 验证方法：模拟同意、拒绝、失败三类动作并检查返回体。
- 预期结果：成功 toast 表达已同意或已拒绝；失败 toast 表达不可处理原因；不只返回“操作已收到”。

### CHK-008 - Action traceability includes actor, request, action, time, and outcome

- 关联需求点：记录谁在什么时间做了什么决策。
- 验证方法：检查 `feishu-card-actions.jsonl` 或相关记录。
- 预期结果：记录包含 Feishu 用户标识、request ID、action、message/chat ID、时间、业务 outcome；不记录 app secret。

### CHK-009 - Existing VO meeting request APIs remain compatible

- 关联需求点：Feishu 是现有流程入口，不创建新审批系统。
- 验证方法：运行现有会议申请确认/拒绝相关测试。
- 预期结果：VO 内原有创建、确认、拒绝、阻塞任务等行为不回归。

### CHK-010 - Feishu generic notification behavior remains compatible

- 关联需求点：复用通用消息模块，不破坏其他通知类型。
- 验证方法：运行 Feishu notification module tests，覆盖四类测试卡片和普通 card action logging。
- 预期结果：普通通知、警告、错误、非会议申请表单仍可发送；未知 action 仍可被记录并返回合理反馈。

### CHK-011 - No real Feishu secrets are committed or logged

- 关联需求点：继续保护 App Secret、Receive ID、webhook 等敏感配置。
- 验证方法：检查 diff、测试 fixture、日志记录字段。
- 预期结果：提交中不包含真实密钥；失败记录和测试输出不泄露密钥。

### CHK-012 - Manual production acceptance path is clear

- 关联需求点：最终要能在生产飞书里处理真实人工会议申请。
- 验证方法：在生产配置中触发一个需要人工处理的会议申请，点击同意/拒绝并观察 VO 状态。
- 预期结果：飞书卡片可见；按钮返回明确结果；VO 中会议申请状态同步；记录可追踪。

## 人工确认记录

- 2026-07-02T22:13:20+08:00 - checklist 初次确认。用户确认摘要：需求目的修正为“原网站会议申请逻辑不变，飞书只作为同步消息和快捷确认通道”，并要求修改后直接产出 todolist。

## 实现验证记录

- 2026-07-02T22:23:32+08:00 - CHK-001、CHK-001A、CHK-002、CHK-003、CHK-004、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010、CHK-011 自动化验证通过。覆盖测试：`.venv/bin/python tests/test_feishu_notifications.py`、`.venv/bin/python tests/test_meeting_request_blocks_task.py`、`.venv/bin/python tests/test_meeting_for_ai_phase4.py`、`.venv/bin/python -m py_compile app/server.py app/feishu_notifications.py app/feishu_long_connection.py tests/test_meeting_request_blocks_task.py tests/test_feishu_notifications.py`。
- 2026-07-02T22:23:32+08:00 - CHK-005 使用 `/#projects` 等价项目入口作为查看详情降级路径；未新增网站深链系统，符合本期“不改变原网站会议申请逻辑”的约束。
- 2026-07-02T22:23:32+08:00 - CHK-012 待生产人工验收。需要在生产飞书中触发一个真实需要人工确认的会议申请，验证网站仍展示原申请、飞书同时收到卡片、按钮可更新 VO 状态。
- 2026-07-02T22:58:47+08:00 - CHK-003 补充验证通过：飞书同意按钮会在确认申请后调用 executable meeting run 入口，返回“会议申请已同意，会议已开始”，并在 action outcome 中记录 `confirmed_started` 和 run stage；网站内原确认接口仍只确认/转换，不被改成自动启动。
