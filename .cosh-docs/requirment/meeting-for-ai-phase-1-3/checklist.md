# Meeting for AI Phase 1-3 Checklist

确认状态：已确认

确认记录：

- 确认时间：2026-06-15T05:09:51+08:00
- 用户确认摘要：用户要求 Phase 1-3 一起作为子需求推进，并明确要求按 Phase 生成 todolist，方便逐 Phase 自测。

## Phase 1: Durable Meeting Foundation

### CHK-P1-001 Canonical Meeting Persistence

- 关联需求：Phase 1 持久化会议实体。
- 验证方法：创建包含配置、参与者、阶段、轮次和上下文的可执行会议后重载 store。
- 预期结果：数据完整一致；临时文件不残留；版本和事件序号可继续递增。

### CHK-P1-002 State Transition Validation

- 关联需求：Phase 1 生命周期。
- 验证方法：覆盖所有合法主路径和非法跨阶段转换。
- 预期结果：合法转换追加事件并更新版本；非法转换返回冲突且不改变数据。

### CHK-P1-003 Ordered and Idempotent Events

- 关联需求：不可变事件流和幂等。
- 验证方法：并发追加事件并重复提交相同 idempotency key。
- 预期结果：序号严格递增且无重复副作用；重复请求返回原结果。

### CHK-P1-004 Participant Occupancy

- 关联需求：同一 AI 只能参加一场非终态会议。
- 验证方法：创建两场包含同一 AI 的活动会议，再结束第一场后重试。
- 预期结果：冲突期间拒绝；终态后释放占用并允许加入新会议。

### CHK-P1-005 Legacy Compatibility

- 关联需求：兼容 `_meetings` 和 `_meetingHistory`。
- 验证方法：加载旧格式 fixtures 并调用现有 active/history/end 接口。
- 预期结果：旧会议可展示和结束；不会伪造执行事件或破坏原数据。

### CHK-P1-006 Restart Reconciliation

- 关联需求：服务重启恢复。
- 验证方法：分别在 preparing、opening、discussion、paused、awaiting decision 状态模拟重启。
- 预期结果：状态可恢复；已完成事件不重复；只有缺失的下一步可继续。

### CHK-P1-007 Meeting Detail and Incremental Events API

- 关联需求：读取会议状态和事件。
- 验证方法：请求详情并按 `after` 序号增量读取。
- 预期结果：详情包含当前版本；增量事件无缺失、无重复且顺序稳定。

### CHK-P1-008 Meeting Center Rendering

- 关联需求：新旧会议前端兼容。
- 验证方法：同时加载 legacy、active executable、paused、completed 会议。
- 预期结果：类型和状态清晰可辨；刷新后从服务端数据恢复。

### CHK-P1-009 Phase 1 Regression Gate

- 关联需求：不破坏现有系统。
- 验证方法：运行会议旧接口、普通聊天、项目 CRUD 和办公室动画回归。
- 预期结果：现有行为无回归；Phase 1 不调用真实 AI。

## Phase 2: User-Started Sequential AI Meeting

### CHK-P2-001 Start Meeting Form

- 关联需求：用户主动发起。
- 验证方法：测试三种会议类型、参与者、主持人、初始上下文和最大轮次表单。
- 预期结果：有效配置可创建；少于两名参与者、主持人不在名单、无主题等输入被阻止。

### CHK-P2-002 Busy Agent Rejection

- 关联需求：Phase 2 只接受可用 Agent。
- 验证方法：选择正在执行操作或已被会议占用的 Agent。
- 预期结果：开始会议前明确拒绝并列出冲突；不暂停或打断原任务。

### CHK-P2-003 Provider Adapter Contract

- 关联需求：OpenClaw、Hermes、Codex 调用。
- 验证方法：用 fake provider 和各 provider 路由测试统一输入输出。
- 预期结果：返回统一状态、原文、结构化贡献、耗时和错误；稳定 conversation ID 不串会。

### CHK-P2-004 Opening Round

- 关联需求：每位 AI 依次首轮发言。
- 验证方法：运行三名参与者会议。
- 预期结果：每人恰好一次首轮发言；speaker queue、事件、当前发言者一致。

### CHK-P2-005 Bounded Discussion Rounds

- 关联需求：有限轮次讨论。
- 验证方法：配置两轮并让主持人点名回应。
- 预期结果：讨论最多两轮；每轮开始结束可追踪；不会无限调用。

### CHK-P2-006 Early Completion

- 关联需求：目标完成后提前结束。
- 验证方法：fake moderator 在首轮后返回目标完成。
- 预期结果：跳过剩余轮次并进入 summarizing；记录提前结束原因。

### CHK-P2-007 Prompt Context and Transcript

- 关联需求：初始上下文、滚动摘要、相关发言。
- 验证方法：检查每次 fake provider 收到的 prompt 和保存的 transcript。
- 预期结果：只包含用户提供上下文和会议事件；原始发言与结构化贡献均可追踪。

### CHK-P2-008 Structured Result

- 关联需求：三种会议类型的结果。
- 验证方法：完成信息收集、讨论决策、任务协作会议。
- 预期结果：生成摘要、结论、未解决问题、争议、贡献和行动项草稿；行动项不创建项目任务。

### CHK-P2-009 Live Meeting UI

- 关联需求：阶段、轮次、发言者和记录展示。
- 验证方法：执行会议并刷新浏览器。
- 预期结果：UI 与服务端状态一致；刷新不丢记录；当前 speaker 和 participant status 正确。

### CHK-P2-010 Phase 2 End-to-End Gate

- 关联需求：真实多 AI 会议 Happy Path。
- 验证方法：通过 UI 完成至少三名可用 AI 的会议。
- 预期结果：会议从创建到 completed，全程可追踪并产生结构化结果。

## Phase 3: User Control and Arbitration

### CHK-P3-001 User Statement and Context

- 关联需求：用户实时发言和补充上下文。
- 验证方法：在 opening 和 discussion 阶段提交用户消息与新上下文。
- 预期结果：事件先持久化；后续 AI turn 可见；已完成发言不改变。

### CHK-P3-002 Targeted Question

- 关联需求：点名 AI。
- 验证方法：用户向指定参与者提问。
- 预期结果：插入唯一 targeted step；指定 AI 回答一次；完成后回到正确议程位置。

### CHK-P3-003 Agenda Change

- 关联需求：调整议题。
- 验证方法：会议中修改 agenda。
- 预期结果：从下一未开始步骤生效；历史事件保留旧议题上下文。

### CHK-P3-004 Pause and Resume

- 关联需求：暂停和继续。
- 验证方法：在 provider 调用前、调用中、调用完成后暂停并恢复。
- 预期结果：暂停后不启动新调用；恢复不重放完成 turn；在途晚到响应按当前状态安全处理。

### CHK-P3-005 Cancel and Late Response

- 关联需求：取消会议。
- 验证方法：调用进行中取消，并在取消后返回 provider 结果。
- 预期结果：会议保持 cancelled；晚到结果作为 ignored evidence 保存，不推进状态。

### CHK-P3-006 User Early End

- 关联需求：用户提前结束。
- 验证方法：opening 和 discussion 阶段分别结束。
- 预期结果：停止新发言并进入 summarizing；已有内容生成结果；不直接丢弃会议。

### CHK-P3-007 No-Consensus Arbitration

- 关联需求：等待用户裁决。
- 验证方法：让参与者形成互斥观点并耗尽轮次。
- 预期结果：进入 awaiting_user_decision；展示各方观点和主持建议；不自动多数决。

### CHK-P3-008 Arbitration Actions

- 关联需求：用户裁决、追加点名或无共识结束。
- 验证方法：分别测试三种处理。
- 预期结果：裁决写入结果；追加点名后可继续；无共识结束明确保留争议。

### CHK-P3-009 Moderator Failure and Takeover

- 关联需求：用户接管或更换主持人。
- 验证方法：模拟主持 AI 失败并选择用户接管或替换 AI。
- 预期结果：已完成发言不重复；新主持从持久化位置继续；失败可审计。

### CHK-P3-010 Intervention Ordering and Races

- 关联需求：统一事件队列。
- 验证方法：并发提交暂停、用户消息、点名和 provider completion。
- 预期结果：按序列确定唯一结果；无重复 turn、非法状态或丢失用户事件。

### CHK-P3-011 Phase 3 End-to-End Gate

- 关联需求：用户可完整控制会议。
- 验证方法：人工执行一次含插话、点名、暂停继续和争议裁决的三 AI 会议。
- 预期结果：所有控制可用，会议最终生成一致结果，刷新后仍可审计。

## Combined Regression Gate

### CHK-ALL-001 Full Phase 1-3 Automated Suite

- 关联需求：Phase 1-3 整体稳定性。
- 验证方法：连续运行 store/state、orchestrator、provider adapter、HTTP、UI 和 regression 测试。
- 预期结果：全部通过，测试间无共享脏状态。

### CHK-ALL-002 Existing Feature Regression

- 关联需求：兼容现有 Virtual Office。
- 验证方法：回归 legacy meetings、Agent chat、Codex activity、项目 CRUD、项目执行和办公室动画。
- 预期结果：无行为回归。

### CHK-ALL-003 Scope Boundary

- 关联需求：后续 Phase 不被误实现或误宣传。
- 验证方法：检查 UI、API 和文档。
- 预期结果：无 AI 主动申请、自动上下文汇总、忙碌任务暂停、行动项建任务功能；相关入口明确留待后续 Phase。
