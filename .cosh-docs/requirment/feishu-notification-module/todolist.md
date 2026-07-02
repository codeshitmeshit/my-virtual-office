# Feishu Notification Module Todolist

## TODO-001 - Locate existing notification and Feishu integration surfaces

- 目标：确认 VO 现有代码中是否已有 Feishu、通知、会议申请或记录相关实现，避免重复造轮子。
- 涉及区域：server code, existing Feishu integration, meeting request flow, tests.
- 输入：`requirement.md`、`review.md`、现有代码搜索结果。
- 输出：实现落点和复用点清单。
- 依赖：无。
- 完成标准：明确新增模块应放置的位置、可复用的 HTTP/config/record helper、首个可接入业务点。
- 关联 checklist：CHK-013, CHK-015。

## TODO-002 - Define notification domain model and validation rules

- 目标：建立四类通知、申请表单状态、按钮 action category、业务关联对象、受众和错误变体的统一输入模型。
- 涉及区域：notification module data model and validation.
- 输入：四类通知产品定义、申请表单状态、按钮扩展规则、错误用户/管理员分流规则。
- 输出：可被业务模块调用的 notification intent/model 和 validation errors。
- 依赖：TODO-001。
- 完成标准：四类通知类型、申请表单状态、action category、related business object、audience/error variant 都有明确字段和校验；非法输入能被拒绝或返回可理解错误。
- 关联 checklist：CHK-001, CHK-003, CHK-004, CHK-005, CHK-008, CHK-012。

## TODO-003 - Implement Feishu card rendering

- 目标：将统一通知模型渲染成 Feishu interactive card payload。
- 涉及区域：Feishu card builder/rendering.
- 输入：TODO-002 的 notification model。
- 输出：四类通知对应的 Feishu card JSON payload。
- 依赖：TODO-002。
- 完成标准：四类卡片都包含统一标题、摘要、核心字段和类型样式；业务 detail 字段可扩展；申请表单按钮和状态清晰呈现；非申请类只允许导航按钮。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007。

## TODO-004 - Implement webhook sender with secret-safe configuration

- 目标：通过配置读取 Feishu webhook 并发送卡片，同时避免泄露真实 webhook。
- 涉及区域：configuration, HTTP sender, logging/error handling.
- 输入：Feishu webhook config name, rendered card payload.
- 输出：sender function/service and sanitized send result.
- 依赖：TODO-003。
- 完成标准：真实 webhook 不写入源码；日志和错误记录脱敏；Feishu success/non-success/network failure 有清晰结果；调用方可选择是否把通知失败视为业务失败。
- 关联 checklist：CHK-009, CHK-011, CHK-012。

## TODO-005 - Add basic notification delivery records

- 目标：记录每次通知尝试，用于排障和业务追踪。
- 涉及区域：existing persistence/status/logging layer.
- 输入：notification intent, send result, related business object.
- 输出：基础发送记录。
- 依赖：TODO-002, TODO-004。
- 完成标准：记录包含类型、标题、业务对象类型和 ID、目标描述、发送时间、成功状态、失败原因；失败原因脱敏；能判断某业务对象是否尝试过通知。
- 关联 checklist：CHK-009, CHK-010, CHK-011。

## TODO-006 - Add application-form action metadata without full callback coupling

- 目标：让申请表单按钮携带可扩展业务语义，同时不伪装成完整审批闭环。
- 涉及区域：application form card model, card rendering, action metadata.
- 输入：action category, business action value, single/multi participant setting, state.
- 输出：按钮 value/meta 和用户可见反馈语义。
- 依赖：TODO-002, TODO-003。
- 完成标准：按钮可表达业务动作和通用分类；默认单人决策、多参与声明可区分；文案和元数据不承诺未实现的回调闭环。
- 关联 checklist：CHK-003, CHK-005, CHK-006。

## TODO-007 - Integrate first VO caller behind the common module

- 目标：选择会议申请或一个低风险内部场景作为首个调用方，证明模块可复用。
- 涉及区域：meeting request or selected VO workflow.
- 输入：common notification module API, business event data.
- 输出：一个业务流程通过通用模块发送通知或申请表单。
- 依赖：TODO-002, TODO-003, TODO-004, TODO-005。
- 完成标准：业务流程不再手写 Feishu card；发送记录能关联业务对象；其他现有流程不受影响。
- 关联 checklist：CHK-010, CHK-013, CHK-015。

## TODO-008 - Unit-test model validation and card rendering

- 目标：覆盖类型、状态、按钮规则、错误变体、非法输入和 payload 结构。
- 涉及区域：unit tests for notification model and renderer.
- 输入：TODO-002, TODO-003, TODO-006。
- 输出：自动化测试。
- 依赖：TODO-002, TODO-003, TODO-006。
- 完成标准：四类通知、申请表单状态、合法/非法按钮、非申请决策按钮拒绝、用户/管理员错误内容差异均有测试。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-007, CHK-008, CHK-012。

## TODO-009 - Unit-test sender and delivery records without real network

- 目标：用 fake sender/HTTP client 测试成功、非成功响应、网络失败和记录写入。
- 涉及区域：sender tests, record tests.
- 输入：TODO-004, TODO-005。
- 输出：自动化测试。
- 依赖：TODO-004, TODO-005。
- 完成标准：测试不调用真实 Feishu；成功和失败记录均可验证；失败原因脱敏；webhook token 不出现在测试输出。
- 关联 checklist：CHK-009, CHK-010, CHK-011。

## TODO-010 - Run regression tests for related VO flows

- 目标：确认新增通用模块不破坏已有会议、项目、Agent 协作或 Feishu 相关功能。
- 涉及区域：existing test suite and targeted regression tests.
- 输入：现有测试命令和相关测试文件。
- 输出：测试结果记录。
- 依赖：TODO-007, TODO-008, TODO-009。
- 完成标准：相关自动化测试通过；若存在已知非致命问题，记录具体范围和影响。
- 关联 checklist：CHK-013, CHK-015。

## TODO-011 - Add documentation and usage examples

- 目标：让后续 VO 模块知道如何调用通用通知模块。
- 涉及区域：developer docs, inline examples, config notes.
- 输入：implemented API and examples.
- 输出：简明开发说明，包含四类通知示例、申请表单按钮规则、webhook secret 配置说明。
- 依赖：TODO-002, TODO-003, TODO-004, TODO-005。
- 完成标准：文档不包含真实 webhook；说明非申请类只允许导航按钮；说明 callback workflow 是后续能力。
- 关联 checklist：CHK-006, CHK-007, CHK-011, CHK-013。

## TODO-012 - Perform optional manual Feishu verification

- 目标：在用户明确允许使用测试 webhook 或指定 webhook 时，发送标记清晰的测试卡片。
- 涉及区域：manual verification script or command.
- 输入：configured webhook, test notification, test application form.
- 输出：人工验证结果和发送记录。
- 依赖：TODO-004, TODO-005。
- 完成标准：发送一条普通测试通知和一条测试申请表单；内容不含敏感业务数据；记录发送结果；如未获允许则跳过并说明。
- 关联 checklist：CHK-014。

## TODO-013 - Update requirement checklist with implementation test results

- 目标：开发完成后把每个 checklist 项的验证结果写回需求归档。
- 涉及区域：`.cosh-docs/requirment/feishu-notification-module/checklist.md`, delivery notes.
- 输入：TODO-008 到 TODO-012 的测试和验证结果。
- 输出：带测试结果的 checklist 或交付说明。
- 依赖：TODO-008, TODO-009, TODO-010, TODO-012。
- 完成标准：每个 CHK 项都有通过、跳过或风险说明；等待用户确认测试通过。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012, CHK-013, CHK-014, CHK-015。
