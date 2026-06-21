# Meeting for AI Phase 5 Todolist

## Execution Rules

- Every task must preserve the invariant that one Agent can hold at most one active meeting occupancy at a time.
- Advisory turn output is read-only. It may recommend waiting, replacing, or force joining, but it must not directly change meeting, task, or occupancy state.
- Lightweight scheduling is a conflict-handling option only. It must not become a full calendar system or hard reservation mechanism.
- Provider capability differences must be visible to users: true pause, logical pause, and unavailable pause are distinct product states.
- Tests must cover deterministic backend paths before browser or real-provider acceptance.

## Conflict Domain and State

### TODO-P5-001 Define Conflict and Occupancy State Model

- 目标：定义 Phase 5 所需的冲突、占用、预约、暂停和恢复状态。
- 涉及区域：meeting domain model、participant state、occupancy projection、status persistence。
- 输入：Phase 5 requirement、existing executable meeting schema、Phase 1-4 event model。
- 输出：conflict record、occupancy lock state、busy risk level、reservation/reminder state、pause/resume metadata。
- 依赖：无。
- 完成标准：能表达 idle、low-risk busy、medium/high-risk busy、meeting-occupied、waiting、reserved/reminder、forced、paused、resume_failed 等状态；不混淆 pending request 和 active meeting。
- 关联 checklist：CHK-P5-001、CHK-P5-010、CHK-P5-014、CHK-P5-018、CHK-P5-021。

### TODO-P5-002 Implement Atomic Meeting Occupancy Guard

- 目标：确保会议确认和启动时不会让同一 Agent 被重复占用。
- 涉及区域：meeting confirmation/start flow、occupancy persistence、idempotency handling。
- 输入：TODO-P5-001 state model、existing meeting confirmation APIs。
- 输出：原子占用校验、失败冲突结果、幂等重复请求处理。
- 依赖：TODO-P5-001。
- 完成标准：近同时确认两场包含同一 Agent 的会议时只有一场成功占用；另一场进入可理解冲突状态；重复确认不产生双重占用。
- 关联 checklist：CHK-P5-018、CHK-P5-020。

### TODO-P5-003 Detect Busy Agent Context

- 目标：识别 Agent 正在执行的任务、provider 调用、外部等待、普通持续工作和会议占用。
- 涉及区域：project execution status、agent activity status、provider call tracking、meeting active projection。
- 输入：Agent ID、project/task state、active meeting state、provider call state。
- 输出：busy reason、risk level、current work summary、estimated availability if known。
- 依赖：TODO-P5-001。
- 完成标准：空闲 Agent 可继续；忙碌 Agent 进入冲突状态并显示原因；状态不明按中高风险处理。
- 关联 checklist：CHK-P5-001、CHK-P5-005、CHK-P5-021。

## Conflict Resolution

### TODO-P5-004 Add Conflict Resolution Actions

- 目标：支持等待、更换参会者、强制加入和取消冲突处理。
- 涉及区域：meeting conflict APIs、meeting preparation state、participant edit flow。
- 输入：conflict ID、user action、replacement participant、force-join confirmation。
- 输出：wait/replaced/forced/cancelled state transitions 和事件记录。
- 依赖：TODO-P5-002、TODO-P5-003。
- 完成标准：四种处理动作状态清晰；更换后使用新参会者继续；等待保留会议准备状态；强制加入不绕过二次确认。
- 关联 checklist：CHK-P5-002、CHK-P5-003、CHK-P5-004。

### TODO-P5-005 Record Conflict Audit Events

- 目标：记录冲突原因、用户选择、advisory 结果和状态转换。
- 涉及区域：meeting event store、audit/event projection、detail API。
- 输入：conflict state transitions、user actions、advisory result。
- 输出：可查询的冲突处理事件和会议详情展示数据。
- 依赖：TODO-P5-004。
- 完成标准：每个冲突处理路径都记录操作者、时间、Agent、原因、选择和结果。
- 关联 checklist：CHK-P5-004、CHK-P5-021。

### TODO-P5-006 Enforce Force-Join Double Confirmation

- 目标：保护高影响强制加入动作。
- 涉及区域：conflict UI/API、force-join endpoint、event validation。
- 输入：force join request、risk summary、advisory status。
- 输出：二次确认流程和服务端验证。
- 依赖：TODO-P5-004、TODO-P5-005。
- 完成标准：未完成二次确认时不进入会议占用或暂停；确认后记录风险说明和用户确认。
- 关联 checklist：CHK-P5-003、CHK-P5-007、CHK-P5-009。

## Advisory Turn

### TODO-P5-007 Implement Advisory Request Lifecycle

- 目标：为中高风险冲突创建受控 advisory turn。
- 涉及区域：agent communication adapter、meeting conflict service、advisory persistence。
- 输入：busy Agent context、source meeting、current task summary、conflict options。
- 输出：advisory pending/completed/failed state、recommendation、risk summary、resume notes。
- 依赖：TODO-P5-003。
- 完成标准：中高风险冲突默认触发 advisory；低风险不被强制触发；结果可展示且可追踪。
- 关联 checklist：CHK-P5-005、CHK-P5-006。

### TODO-P5-008 Keep Advisory Read-Only

- 目标：确保 advisory 输出不能直接改变会议、任务或占用状态。
- 涉及区域：advisory result handling、meeting transition validation。
- 输入：advisory recommendation。
- 输出：只读建议投影和执行动作隔离。
- 依赖：TODO-P5-007。
- 完成标准：advisory 推荐等待/更换/强制加入后，系统仍等待用户动作；没有自动暂停、替换、释放或启动会议。
- 关联 checklist：CHK-P5-008。

### TODO-P5-009 Add Advisory Failure Degradation

- 目标：处理 advisory 超时、失败或输出无效。
- 涉及区域：advisory timeout/error path、conflict UI/API。
- 输入：advisory timeout、provider error、invalid output。
- 输出：无法获取建议状态、用户继续处理入口、强制加入二次确认要求。
- 依赖：TODO-P5-007、TODO-P5-008。
- 完成标准：失败不阻塞等待/更换；失败不等于同意；强制加入仍需二次确认。
- 关联 checklist：CHK-P5-007、CHK-P5-009。

## Lightweight Scheduling

### TODO-P5-010 Add Lightweight Reservation Option

- 目标：将稍后提醒/等空闲再尝试作为冲突处理选项。
- 涉及区域：conflict actions、meeting preparation state、reservation/reminder projection。
- 输入：conflict ID、remind later or wait-until-available action、optional target time。
- 输出：reservation/reminder state and visible schedule marker。
- 依赖：TODO-P5-004。
- 完成标准：预约不会启动会议、不会暂停当前任务、不会强占 Agent；用户可看到该未来安排。
- 关联 checklist：CHK-P5-010、CHK-P5-011。

### TODO-P5-011 Recheck Conflict On Reservation Trigger

- 目标：预约触发时重新检查 Agent 状态并回到冲突处理。
- 涉及区域：reservation trigger loop、meeting conflict service、notification/projection。
- 输入：reservation due event、current Agent state。
- 输出：重新冲突检测结果、用户提醒、下一步处理入口。
- 依赖：TODO-P5-010、TODO-P5-003。
- 完成标准：Agent 仍忙时不自动强制加入、不自动取消、不跳过冲突检测；Agent 空闲时可继续会议准备。
- 关联 checklist：CHK-P5-012。

### TODO-P5-012 Review Reservation Copy and Boundaries

- 目标：确保预约文案不承诺必定开会或硬占用 Agent。
- 涉及区域：locales、conflict panel copy、meeting detail state labels、notifications。
- 输入：reservation states and UI labels。
- 输出：稍后提醒、到时尝试、等空闲后再处理等清晰文案。
- 依赖：TODO-P5-010。
- 完成标准：所有预约相关文案都表达为轻量安排；不出现必定开会、已强占或完整日程承诺。
- 关联 checklist：CHK-P5-013。

## Pause and Resume

### TODO-P5-013 Snapshot Original Work Before Participation

- 目标：Agent 正式进入会议前保存原任务和恢复上下文。
- 涉及区域：project execution state、agent activity state、meeting participant state。
- 输入：Agent current task/work state、force/wait resolution reason。
- 输出：original task ID、progress summary、pause reason、resume token、resume notes。
- 依赖：TODO-P5-004、TODO-P5-006。
- 完成标准：强制加入和正常加入忙碌 Agent 前均保存可恢复快照；快照可在会议详情和恢复流程中使用。
- 关联 checklist：CHK-P5-014。

### TODO-P5-014 Distinguish True Pause, Logical Pause, and Unavailable Pause

- 目标：按 provider 能力展示和执行不同暂停语义。
- 涉及区域：provider capability registry、pause service、UI state labels。
- 输入：Agent/provider kind、current work type、pause capability。
- 输出：true_paused、logical_paused、pause_unavailable 状态和说明。
- 依赖：TODO-P5-013。
- 完成标准：支持真实暂停时记录真实暂停结果；不支持时使用逻辑暂停并明确限制；不可暂停时进入明确冲突或人工处理。
- 关联 checklist：CHK-P5-015。

### TODO-P5-015 Implement Idempotent Resume

- 目标：会议正常结束、取消或失败后恢复原任务且不会重复恢复。
- 涉及区域：meeting terminal transitions、resume service、project execution continuation。
- 输入：meeting terminal event、original work snapshot、resume token。
- 输出：resume_attempted/resumed/resume_failed 状态和幂等保护。
- 依赖：TODO-P5-013、TODO-P5-014。
- 完成标准：正常结束、取消和失败后均触发可恢复任务恢复；重复恢复请求不重复派发或重复创建任务。
- 关联 checklist：CHK-P5-016、CHK-P5-017。

### TODO-P5-016 Add Resume Failure Manual Recovery

- 目标：恢复失败时提供可见告警和人工补救入口。
- 涉及区域：meeting detail UI、project task status、agent status projection。
- 输入：resume failure reason、original work snapshot。
- 输出：resume_failed state、operator message、manual recovery action or note。
- 依赖：TODO-P5-015。
- 完成标准：恢复失败不会隐藏；会议占用尽量释放；任务或 Agent 显示需人工处理状态。
- 关联 checklist：CHK-P5-017、CHK-P5-021。

## UI and Regression

### TODO-P5-017 Build Conflict and Reservation UI

- 目标：在会议中心、会议详情和冲突处理面板展示 Phase 5 状态和操作。
- 涉及区域：meeting dashboard、meeting detail modal、control/sidebar if relevant、styles/locales。
- 输入：conflict detail API、advisory result、reservation state、pause/resume state。
- 输出：冲突原因、advisory 建议、等待/更换/强制加入/预约操作、暂停恢复状态展示。
- 依赖：TODO-P5-004、TODO-P5-007、TODO-P5-010、TODO-P5-015。
- 完成标准：用户能看懂当前状态、风险、建议和可选操作；办公室 Agent 状态与会议详情一致。
- 关联 checklist：CHK-P5-002、CHK-P5-003、CHK-P5-010、CHK-P5-013、CHK-P5-021。

### TODO-P5-018 Add Backend Lifecycle Tests

- 目标：用确定性测试覆盖冲突、advisory、预约、暂停恢复和并发占用。
- 涉及区域：Python tests、fixtures、meeting/project stores。
- 输入：TODO-P5-001 至 TODO-P5-016。
- 输出：自动化测试覆盖主要状态和错误路径。
- 依赖：TODO-P5-016。
- 完成标准：覆盖 CHK-P5-001 至 CHK-P5-020 的后端状态流、幂等、并发和错误路径。
- 关联 checklist：CHK-P5-001 至 CHK-P5-020。

### TODO-P5-019 Add Frontend and Browser Acceptance

- 目标：验证用户可见的冲突处理、advisory、预约、暂停恢复和状态一致性。
- 涉及区域：browser/MCP validation、frontend fixtures、JS/i18n checks。
- 输入：TODO-P5-017、TODO-P5-018。
- 输出：浏览器验收记录和必要截图/断言。
- 依赖：TODO-P5-017、TODO-P5-018。
- 完成标准：覆盖 CHK-P5-021，且能从 UI 完成等待、更换、强制加入、预约和恢复失败查看。
- 关联 checklist：CHK-P5-021。

### TODO-P5-020 Run Regression Matrix

- 目标：确认普通聊天、项目工作流和 Phase 1-4 已验收能力不回归。
- 涉及区域：meeting tests、project execution tests、chat/agent communication path、AI request path。
- 输入：existing Phase 1-4 acceptance paths、Phase 5 implementation。
- 输出：回归测试记录和失败修复。
- 依赖：TODO-P5-018、TODO-P5-019。
- 完成标准：普通聊天、项目任务创建/执行、用户发起会议、用户干预/裁决、AI 发起申请和上下文确认均保持可用。
- 关联 checklist：CHK-P5-022、CHK-P5-023、CHK-P5-024。

### TODO-P5-021 Update Requirement Status and Evidence

- 目标：把开发、测试、已知限制和用户确认节点回写归档。
- 涉及区域：checklist.md、status.json、交付说明。
- 输入：TODO-P5-018 至 TODO-P5-020 结果。
- 输出：测试记录、限制说明、等待用户验收状态。
- 依赖：TODO-P5-020。
- 完成标准：checklist 测试记录完整；实现完成后状态推进到 implementation_done 或 tested；最终 done 仍等待用户确认。
- 关联 checklist：CHK-P5-001 至 CHK-P5-024。
