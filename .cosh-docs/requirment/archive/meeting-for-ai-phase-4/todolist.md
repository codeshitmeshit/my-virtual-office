# Meeting for AI Phase 4 Todolist

## Execution Rules

- Implement APIs and frontend UI first with deterministic fixtures or equivalent project-task request data.
- Do not run the true AI-originated request acceptance test until the user confirms the required skill has been installed for the requesting AI.
- Pending AI meeting requests must never appear as active meetings, reserve Agent occupancy, or call meeting participants before user confirmation.
- Every implementation task must update or add tests traceable to the listed checklist IDs.

## Request Domain and Persistence

### TODO-P4-001 Define AI Meeting Request Domain Model

- 目标：定义 AI 会议申请的持久对象、状态、来源类型、原始申请、用户确认信息和转换结果。
- 涉及区域：meeting domain/store 或新增 request store；project task source references。
- 输入：`meeting-for-ai-phase-4/requirement.md`、现有 executable meeting schema、项目任务模型。
- 输出：request schema、状态枚举、sourceType 扩展点、原始申请与用户最终配置字段。
- 依赖：无。
- 完成标准：支持 `project_task` 来源；保留未来来源扩展点；pending/rejected/confirmed 状态清晰；不与 active executable meeting 混淆。
- 关联 checklist：CHK-P4-001、CHK-P4-003、CHK-P4-014、CHK-P4-015。

### TODO-P4-002 Implement Durable Request Store and Idempotency

- 目标：实现 AI 会议申请的创建、读取、状态转换和幂等保护。
- 涉及区域：server persistence；meeting request service。
- 输入：TODO-P4-001 schema。
- 输出：create/list/detail/reject/confirm 状态操作和 idempotency key 支持。
- 依赖：TODO-P4-001。
- 完成标准：重复创建/确认不会产生重复副作用；非法状态转换返回可理解错误；rejected request 不能直接确认。
- 关联 checklist：CHK-P4-001、CHK-P4-011、CHK-P4-012、CHK-P4-014。

### TODO-P4-003 Enforce Request Quality Gate

- 目标：阻止缺少关键说明的 AI 会议申请成为可处理 pending request。
- 涉及区域：request validation；project task AI request endpoint。
- 输入：meeting goal、expected outcome、cannot-complete-alone reason、suggested participants/type。
- 输出：字段校验和错误响应。
- 依赖：TODO-P4-001、TODO-P4-002。
- 完成标准：缺少会议目标、期望产物或无法单独完成原因时不创建有效 pending request；错误能被前端展示。
- 关联 checklist：CHK-P4-002。

## Project Context Candidates

### TODO-P4-004 Build Same-Project Context Candidate Generator

- 目标：生成当前项目范围内的可选上下文候选。
- 涉及区域：project store；meeting request service。
- 输入：source project ID、source task ID、项目任务、同项目历史会议。
- 输出：候选上下文列表，包含 source kind、title、summary/excerpt、source reference。
- 依赖：TODO-P4-001。
- 完成标准：包含当前项目、当前任务、相关同项目任务、同项目历史会议；不包含跨项目内容。
- 关联 checklist：CHK-P4-004。

### TODO-P4-005 Keep Context Candidates Unselected by Default

- 目标：确保自动推荐上下文只是候选，不自动进入会议。
- 涉及区域：request candidate model；confirmation payload；frontend review UI。
- 输入：TODO-P4-004 candidates。
- 输出：默认未选中候选和显式选择记录。
- 依赖：TODO-P4-004。
- 完成标准：用户不选择候选时，确认会议不携带候选内容；前端默认状态明确。
- 关联 checklist：CHK-P4-005。

### TODO-P4-006 Create Immutable Confirmed Context Snapshot

- 目标：确认会议时只把用户已选候选和补充资料固化到会议上下文。
- 涉及区域：request confirmation service；executable meeting create flow；prompt context input。
- 输入：selected candidate IDs、supplemental context、source candidate content。
- 输出：meeting initial context snapshot 和 request-to-meeting trace。
- 依赖：TODO-P4-004、TODO-P4-005。
- 完成标准：未选候选不进入 provider 输入、发言记录、总结或结果；源项目内容后续变化不改变已确认会议快照。
- 关联 checklist：CHK-P4-006、CHK-P4-010、CHK-P4-019。

## Request APIs and Conversion

### TODO-P4-007 Add AI Meeting Request APIs

- 目标：提供前端和后续 AI skill 可调用的 Phase 4 request API。
- 涉及区域：`app/server.py` routes；request service。
- 输入：create/list/detail/reject/confirm payloads。
- 输出：项目任务来源创建申请、按状态查询、按任务查询、拒绝、确认并创建会议的 API。
- 依赖：TODO-P4-002、TODO-P4-003、TODO-P4-004。
- 完成标准：API 覆盖 pending/rejected/confirmed；支持 Meetings dashboard 聚合查询和任务详情查询；普通聊天或无项目任务来源不能创建正式申请。
- 关联 checklist：CHK-P4-001、CHK-P4-003、CHK-P4-009、CHK-P4-013、CHK-P4-014。

### TODO-P4-008 Implement Editable Confirmation to Executable Meeting

- 目标：把用户编辑后的申请转换为一场 executable meeting。
- 涉及区域：request confirmation service；existing `/api/meetings/executable/create` flow。
- 输入：用户最终 topic/purpose/type/participants/moderator/maxRounds/context selections/supplemental context。
- 输出：created meeting ID、confirmed request record、edit summary。
- 依赖：TODO-P4-006、TODO-P4-007。
- 完成标准：最终会议使用用户配置；原始申请理由和用户修改摘要可追踪；重复确认只创建一场会议。
- 关联 checklist：CHK-P4-007、CHK-P4-008、CHK-P4-011、CHK-P4-019。

### TODO-P4-009 Implement Rejection Feedback to Source Task

- 目标：用户拒绝申请后把拒绝原因返回来源任务上下文。
- 涉及区域：request service；project task activity/comment/status area。
- 输入：request ID、rejection reason。
- 输出：rejected request、source task-visible feedback。
- 依赖：TODO-P4-007。
- 完成标准：拒绝后不创建会议；来源任务可看到拒绝原因；同一申请不再重复显示为待处理。
- 关联 checklist：CHK-P4-009、CHK-P4-020。

### TODO-P4-010 Protect Pre-Confirmation Safety Boundaries

- 目标：保证未确认申请不产生执行副作用。
- 涉及区域：request lifecycle；active meetings projection；occupancy checks；provider call path。
- 输入：pending request records。
- 输出：安全校验和回归测试。
- 依赖：TODO-P4-007、TODO-P4-008。
- 完成标准：pending request 不出现在 active meetings；不占用 Agent；不调用任何会议参与者 provider。
- 关联 checklist：CHK-P4-010、CHK-P4-015。

## Frontend UI

### TODO-P4-011 Add Meetings Dashboard AI Requests Queue

- 目标：在 Meetings dashboard 中新增独立 AI Requests 队列。
- 涉及区域：`app/index.html` meetings modal tabs；`app/game.js` meetings dashboard render；locales；styles。
- 输入：request list/detail APIs。
- 输出：AI Requests tab/section、pending/rejected/confirmed cards、review entry。
- 依赖：TODO-P4-007。
- 完成标准：AI Requests 与 Active/History 分离；pending request 不显示为 active meeting；状态文案清楚。
- 关联 checklist：CHK-P4-013、CHK-P4-014、CHK-P4-015。

### TODO-P4-012 Build Request Review and Edit UI

- 目标：让用户在确认前编辑申请配置、选择上下文、补充资料并确认或拒绝。
- 涉及区域：Meetings dashboard modal；request review modal/panel；agent selector；context candidate selector。
- 输入：request detail、agent roster、context candidates。
- 输出：可编辑确认表单、拒绝原因输入、错误/加载状态。
- 依赖：TODO-P4-005、TODO-P4-007、TODO-P4-008、TODO-P4-009、TODO-P4-011。
- 完成标准：用户可编辑 topic/purpose/type/participants/moderator/maxRounds/context/supplemental context；确认和拒绝路径均可用。
- 关联 checklist：CHK-P4-005、CHK-P4-007、CHK-P4-009、CHK-P4-019、CHK-P4-020。

### TODO-P4-013 Show Requests in Source Task Detail Panel

- 目标：在项目任务详情中展示该任务相关 AI 会议申请。
- 涉及区域：`app/projects.js` task detail panel；project/task request API integration；locales/styles。
- 输入：source task request list。
- 输出：任务详情中的 pending/rejected/confirmed request section 和处理入口。
- 依赖：TODO-P4-007、TODO-P4-012。
- 完成标准：来源任务详情展示请求 AI、原因、期望产物、状态和处理入口；拒绝原因可回看。
- 关联 checklist：CHK-P4-013、CHK-P4-020。

### TODO-P4-014 Add Control Panel Meetings Confirmation Prompt

- 目标：右侧控制面板 Meetings 区域提示有 AI 会议申请需要人工确认。
- 涉及区域：sidebar Meetings widget；`app/game.js` sidebar refresh；locales/styles。
- 输入：pending request count API。
- 输出：轻量待确认数量/提示和跳转到 AI Requests 队列的入口。
- 依赖：TODO-P4-007、TODO-P4-011。
- 完成标准：有 pending request 时显示提示；点击打开 Meetings dashboard 并进入或突出 AI Requests；不展示完整审查表单，不伪装成 active meeting。
- 关联 checklist：CHK-P4-015、CHK-P4-016。

### TODO-P4-015 Add Task Card Compact Indicator

- 目标：在项目看板任务卡上显示紧凑 AI meeting request 状态。
- 涉及区域：`app/projects.js` task card render；styles。
- 输入：task-level pending request count/status。
- 输出：任务卡 badge/count。
- 依赖：TODO-P4-007、TODO-P4-013。
- 完成标准：任务卡显示紧凑提示；点击任务后在详情面板处理；任务卡不承载完整确认流程。
- 关联 checklist：CHK-P4-017。

## Tests and Acceptance

### TODO-P4-016 Add Backend Request Lifecycle Tests

- 目标：覆盖 request 创建、校验、上下文候选、拒绝、确认、幂等和安全边界。
- 涉及区域：Python tests；request fixtures。
- 输入：TODO-P4-001 至 TODO-P4-010。
- 输出：确定性自动化测试。
- 依赖：TODO-P4-010。
- 完成标准：覆盖 CHK-P4-001 至 CHK-P4-012；不需要真实 AI provider。
- 关联 checklist：CHK-P4-001 至 CHK-P4-012。

### TODO-P4-017 Add Frontend/API Fixture Acceptance Tests

- 目标：验证 AI Requests 队列、任务详情展示、控制面板提示和编辑确认 UI。
- 涉及区域：browser/CDP or equivalent UI test；frontend fixtures；JS syntax/i18n checks。
- 输入：TODO-P4-011 至 TODO-P4-015。
- 输出：前端验收记录和截图/断言文件。
- 依赖：TODO-P4-015、TODO-P4-016。
- 完成标准：覆盖 CHK-P4-013 至 CHK-P4-020 中不依赖真实 AI 的部分；用户发起会议回归通过。
- 关联 checklist：CHK-P4-013 至 CHK-P4-020。

### TODO-P4-018 Stop for Real AI Skill Preparation

- 目标：在真实 AI-originated request 验收前暂停并通知用户准备 skill。
- 涉及区域：交付流程；checklist/status notes。
- 输入：API/UI fixture gate 结果。
- 输出：明确的用户通知和等待确认状态。
- 依赖：TODO-P4-017。
- 完成标准：未获得用户确认前，不执行真实 AI 主动申请验收；交付说明明确需要安装的 skill 和验证入口。
- 关联 checklist：CHK-P4-021。

### TODO-P4-019 Run Real AI-Originated Request Acceptance

- 目标：在用户确认 skill 已安装后，验证真实 AI 从项目任务中提交会议申请的完整链路。
- 涉及区域：project execution task context；request API；Meetings dashboard；confirmed meeting startup。
- 输入：用户已安装对应 skill 的真实 AI；明确阻塞项目任务。
- 输出：真实 AI 申请、用户确认、会议启动验收记录。
- 依赖：TODO-P4-018，且必须等待用户确认。
- 完成标准：真实 AI 提交包含目标、期望产物和无法单独完成原因的申请；用户确认前无 provider participant calls；确认后会议使用用户最终配置和已选上下文启动。
- 关联 checklist：CHK-P4-022。

### TODO-P4-020 Update Requirement Status and Test Evidence

- 目标：把实现、测试和用户确认状态回写需求归档。
- 涉及区域：`checklist.md`、`status.json`、交付说明。
- 输入：TODO-P4-016 至 TODO-P4-019 结果。
- 输出：测试记录、已知限制、待用户确认节点。
- 依赖：TODO-P4-017；真实 AI gate 结果按用户确认情况追加。
- 完成标准：checklist 测试记录完整；若真实 AI gate 尚未执行，状态明确停在等待用户准备 skill；不得误标 done。
- 关联 checklist：CHK-P4-001 至 CHK-P4-022。
