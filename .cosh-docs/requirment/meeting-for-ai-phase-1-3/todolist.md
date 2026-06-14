# Meeting for AI Phase 1-3 Todolist

## Execution Rules

- Tasks are grouped by Phase and must be completed in order.
- Each Phase ends with an automated self-test gate and a manual acceptance gate.
- Do not start Phase 2 until the Phase 1 gate passes.
- Do not start Phase 3 until the Phase 2 gate passes.
- A failed gate returns work to the tasks in that Phase; it does not get deferred to Phase 7.
- Every implementation task must add or update tests traceable to the listed checklist IDs.

## Phase 1: Durable Meeting Foundation

### TODO-P1-001 Define Meeting Domain Schema

- 目标：定义可执行会议 snapshot、participant、event、result 和 occupancy 数据契约。
- 涉及区域：新增 meeting domain module；现有 meeting handlers。
- 输入：母需求 Phase 1、现有 `_meetings`/`_meetingHistory`。
- 输出：字段定义、状态枚举、事件类型、版本和序号规则。
- 依赖：无。
- 完成标准：schema 可校验；legacy 与 executable meeting 可明确区分。
- 关联 checklist：CHK-P1-001、CHK-P1-002、CHK-P1-005。

### TODO-P1-002 Implement Atomic Meeting Store

- 目标：实现锁保护、原子写入、版本检查和事件序号分配。
- 涉及区域：`VO_STATUS_DIR` persistence；新增 meeting store。
- 输入：TODO-P1-001 schema。
- 输出：load/save/create/update/append-event APIs。
- 依赖：TODO-P1-001。
- 完成标准：并发测试无丢写；临时文件原子替换；重复 idempotency key 无重复副作用。
- 关联 checklist：CHK-P1-001、CHK-P1-003。

### TODO-P1-003 Implement Meeting State Machine

- 目标：集中实现合法转换、终态、阶段和版本推进。
- 涉及区域：meeting domain/service。
- 输入：schema、store。
- 输出：单一 transition API 和 transition table。
- 依赖：TODO-P1-001、TODO-P1-002。
- 完成标准：所有 handler/runner 不直接修改 lifecycle 字段；非法转换返回 409。
- 关联 checklist：CHK-P1-002、CHK-P1-003。

### TODO-P1-004 Implement Participant Occupancy

- 目标：保证一个 Agent 只属于一场非终态会议。
- 涉及区域：meeting store、create/start/end/cancel transitions。
- 输入：participant IDs、meeting terminal rules。
- 输出：原子 occupancy reserve/release/reconcile。
- 依赖：TODO-P1-002、TODO-P1-003。
- 完成标准：冲突不可穿透；终态可靠释放；重启可重建索引。
- 关联 checklist：CHK-P1-004、CHK-P1-006。

### TODO-P1-005 Add Executable Meeting APIs

- 目标：提供创建、详情、增量事件、转换、取消和恢复状态接口。
- 涉及区域：`app/server.py` routes and handlers。
- 输入：meeting service。
- 输出：版本化 JSON API；expectedVersion/idempotencyKey 支持。
- 依赖：TODO-P1-002 至 TODO-P1-004。
- 完成标准：错误状态码和响应稳定；增量事件按序返回。
- 关联 checklist：CHK-P1-002、CHK-P1-003、CHK-P1-007。

### TODO-P1-006 Add Legacy Projection and Migration

- 目标：保持现有 active/history/end 与办公室动画兼容。
- 涉及区域：legacy meeting load/save handlers、gateway presence。
- 输入：旧 fixtures、新 meeting snapshots。
- 输出：legacy reader/migrator/projector。
- 依赖：TODO-P1-001、TODO-P1-002。
- 完成标准：旧数据不丢失；新会议可投影到现有参与者展示。
- 关联 checklist：CHK-P1-005、CHK-P1-009。

### TODO-P1-007 Add Restart Reconciliation

- 目标：启动时识别非终态会议并确定可恢复下一步。
- 涉及区域：server startup、meeting service。
- 输入：persisted snapshots、pending calls、events。
- 输出：reconciliation report 和恢复状态。
- 依赖：TODO-P1-003、TODO-P1-004、TODO-P1-006。
- 完成标准：不重复完成事件；paused/awaiting decision 保持等待。
- 关联 checklist：CHK-P1-006。

### TODO-P1-008 Update Meeting Center for Executable Meetings

- 目标：展示 executable/legacy 类型、阶段、轮次、参与者和恢复状态。
- 涉及区域：`app/index.html`、`app/game.js`、`app/style.css`、locales。
- 输入：meeting detail/events APIs。
- 输出：新旧会议兼容卡片与详情基础视图。
- 依赖：TODO-P1-005、TODO-P1-006。
- 完成标准：刷新后只依赖服务端数据恢复；状态标签准确。
- 关联 checklist：CHK-P1-008。

### TODO-P1-009 Build Phase 1 Automated Tests

- 目标：覆盖 store、state、occupancy、migration、restart 和 HTTP。
- 涉及区域：新增 Python tests 和必要 JS tests。
- 输入：Phase 1 implementation。
- 输出：确定性测试 fixtures 和一键测试命令。
- 依赖：TODO-P1-001 至 TODO-P1-008。
- 完成标准：CHK-P1-001 至 CHK-P1-009 全覆盖；测试不调用 AI。
- 关联 checklist：CHK-P1-001 至 CHK-P1-009。

### TODO-P1-010 Run Phase 1 Self-Test Gate

- 目标：独立验收 Phase 1。
- 涉及区域：自动测试、浏览器 smoke、回归。
- 输入：TODO-P1-009。
- 输出：Phase 1 测试记录和已知限制。
- 依赖：TODO-P1-009。
- 完成标准：Phase 1 checklist 全通过后才允许开始 Phase 2。
- 关联 checklist：CHK-P1-001 至 CHK-P1-009。

## Phase 2: User-Started Sequential AI Meeting

### TODO-P2-001 Add Start Meeting UI

- 目标：提供主题、类型、目的、参与者、AI 主持、上下文和最大轮次表单。
- 涉及区域：meeting modal、styles、locales。
- 输入：agent roster、meeting create/start APIs。
- 输出：表单、validation、error states。
- 依赖：TODO-P1-010。
- 完成标准：有效配置可提交；无效输入不创建会议。
- 关联 checklist：CHK-P2-001。

### TODO-P2-002 Implement Availability Preflight

- 目标：Phase 2 开始前拒绝忙碌、离线或已占用 Agent。
- 涉及区域：meeting service、presence/provider activity lookup。
- 输入：participant IDs。
- 输出：availability result 和冲突原因。
- 依赖：TODO-P1-004、TODO-P2-001。
- 完成标准：不暂停现有任务；冲突结果可在 UI 理解。
- 关联 checklist：CHK-P2-002。

### TODO-P2-003 Implement Meeting Provider Adapter

- 目标：统一 OpenClaw、Hermes、Codex 的会议调用契约。
- 涉及区域：provider adapters、meeting service。
- 输入：meeting turn request。
- 输出：normalized contribution result。
- 依赖：TODO-P1-010。
- 完成标准：fake provider 可完全驱动测试；conversation ID 稳定且隔离。
- 关联 checklist：CHK-P2-003。

### TODO-P2-004 Define Turn Prompt and Structured Output

- 目标：定义 opening、discussion、moderator、summary prompt contract。
- 涉及区域：meeting prompt builder/parser。
- 输入：meeting snapshot、events、rolling summary。
- 输出：provider-neutral prompts 和严格解析/降级规则。
- 依赖：TODO-P2-003。
- 完成标准：解析失败保留原文并产生明确状态，不伪造结构字段。
- 关联 checklist：CHK-P2-003、CHK-P2-007、CHK-P2-008。

### TODO-P2-005 Implement Persisted Meeting Orchestrator

- 目标：从持久状态执行 opening、discussion、early completion、summarizing。
- 涉及区域：新增 orchestrator/runner、startup recovery hook。
- 输入：meeting service、provider adapter。
- 输出：per-meeting serialized runner。
- 依赖：TODO-P2-002 至 TODO-P2-004。
- 完成标准：provider 调用外置于 store lock；pending call 和 completion 幂等。
- 关联 checklist：CHK-P2-004、CHK-P2-005、CHK-P2-006。

### TODO-P2-006 Implement Rolling Summary and Relevant Context

- 目标：控制上下文长度并维持讨论连贯。
- 涉及区域：event reducer、prompt builder。
- 输入：original transcript events。
- 输出：rolling summary、relevant statements selection。
- 依赖：TODO-P2-004、TODO-P2-005。
- 完成标准：原始事件不被摘要替代；prompt 只含允许上下文。
- 关联 checklist：CHK-P2-007。

### TODO-P2-007 Implement Structured Meeting Result

- 目标：生成三种会议类型的标准结果。
- 涉及区域：summarization stage、meeting result schema。
- 输入：transcript、moderator output、meeting type。
- 输出：summary、decision、unresolved、disagreements、contributions、action drafts。
- 依赖：TODO-P2-005、TODO-P2-006。
- 完成标准：结果可追溯事件；action drafts 不创建项目任务。
- 关联 checklist：CHK-P2-008。

### TODO-P2-008 Implement Live Meeting UI

- 目标：展示 stage、round、speaker、participants、transcript 和 result。
- 涉及区域：meeting dashboard frontend。
- 输入：detail 和 incremental event APIs。
- 输出：轮询增量更新、刷新恢复、完成视图。
- 依赖：TODO-P2-005、TODO-P2-007。
- 完成标准：浏览器关闭不影响执行；重新打开状态一致。
- 关联 checklist：CHK-P2-009。

### TODO-P2-009 Build Phase 2 Automated Tests

- 目标：覆盖 form、availability、adapter、orchestrator、result 和 UI reducer。
- 涉及区域：Python/JS tests、fake providers。
- 输入：Phase 2 implementation。
- 输出：确定性三类会议 fixtures。
- 依赖：TODO-P2-001 至 TODO-P2-008。
- 完成标准：CHK-P2-001 至 CHK-P2-010 可自动验证的部分全部覆盖。
- 关联 checklist：CHK-P2-001 至 CHK-P2-010。

### TODO-P2-010 Run Phase 2 Self-Test Gate

- 目标：独立验收真实顺序会议 MVP。
- 涉及区域：自动测试、浏览器 E2E、真实 provider smoke。
- 输入：TODO-P2-009。
- 输出：Phase 2 测试记录和 provider 兼容结果。
- 依赖：TODO-P2-009。
- 完成标准：三 AI Happy Path 通过后才允许开始 Phase 3。
- 关联 checklist：CHK-P2-001 至 CHK-P2-010。

## Phase 3: User Control and Arbitration

### TODO-P3-001 Add User Intervention Event Types and API

- 目标：支持用户发言、补充上下文、点名、议题修改和控制命令。
- 涉及区域：meeting schema/service/API。
- 输入：expectedVersion、idempotencyKey、intervention payload。
- 输出：ordered durable intervention events。
- 依赖：TODO-P2-010。
- 完成标准：所有 intervention 先持久化后响应；并发顺序确定。
- 关联 checklist：CHK-P3-001、CHK-P3-002、CHK-P3-003、CHK-P3-010。

### TODO-P3-002 Apply User Context and Agenda Changes

- 目标：让后续 turn 使用用户新增内容和新议题。
- 涉及区域：event reducer、prompt builder。
- 输入：intervention events。
- 输出：effective context/agenda at each sequence。
- 依赖：TODO-P3-001。
- 完成标准：历史 turn 不重写；后续 prompt 可验证。
- 关联 checklist：CHK-P3-001、CHK-P3-003。

### TODO-P3-003 Implement Targeted Speaking Steps

- 目标：用户点名后插入一次目标 AI 回答并返回原议程。
- 涉及区域：orchestrator queue。
- 输入：targeted question event。
- 输出：唯一 targeted step。
- 依赖：TODO-P3-001、TODO-P3-002。
- 完成标准：不重复回答；原 speaker queue 位置保持。
- 关联 checklist：CHK-P3-002。

### TODO-P3-004 Implement Pause and Resume Semantics

- 目标：停止新调用并从下一未完成步骤恢复。
- 涉及区域：state machine、orchestrator、UI controls。
- 输入：pause/resume events、pending calls。
- 输出：paused state 和 deterministic resume。
- 依赖：TODO-P3-001。
- 完成标准：在途响应按版本处理；完成 turn 不重放。
- 关联 checklist：CHK-P3-004。

### TODO-P3-005 Implement Cancel and Early End

- 目标：支持安全取消和提前进入总结。
- 涉及区域：state machine、orchestrator、result builder。
- 输入：cancel/end events。
- 输出：cancelled 或 summarizing transition。
- 依赖：TODO-P3-004。
- 完成标准：取消后晚到响应不推进；提前结束保留已有内容。
- 关联 checklist：CHK-P3-005、CHK-P3-006。

### TODO-P3-006 Implement No-Consensus Detection

- 目标：轮次耗尽或主持判断无共识时等待用户。
- 涉及区域：moderator parser、state machine、result draft。
- 输入：discussion events。
- 输出：awaiting_user_decision snapshot with positions。
- 依赖：TODO-P2-007、TODO-P3-001。
- 完成标准：不自动多数决；各方观点和建议可展示。
- 关联 checklist：CHK-P3-007。

### TODO-P3-007 Implement Arbitration Actions

- 目标：用户可裁决、追加点名或无共识结束。
- 涉及区域：API、orchestrator、result builder。
- 输入：decision event。
- 输出：continued discussion or summarizing。
- 依赖：TODO-P3-003、TODO-P3-006。
- 完成标准：裁决进入最终结果；重复提交幂等。
- 关联 checklist：CHK-P3-008。

### TODO-P3-008 Implement Moderator Takeover and Replacement

- 目标：主持失败时由用户接管或替换 AI。
- 涉及区域：participant roles、orchestrator、UI。
- 输入：moderator failure and replacement event。
- 输出：new moderator assignment and resume point。
- 依赖：TODO-P3-001、TODO-P3-004。
- 完成标准：已完成发言不重放；失败原因可审计。
- 关联 checklist：CHK-P3-009。

### TODO-P3-009 Add Active Meeting Control UI

- 目标：提供发言、点名、议题、暂停继续、取消、结束、裁决和主持切换界面。
- 涉及区域：meeting dashboard frontend、styles、locales。
- 输入：Phase 3 APIs and event state。
- 输出：state-aware controls and errors。
- 依赖：TODO-P3-001 至 TODO-P3-008。
- 完成标准：非法状态按钮禁用；刷新后 pending decision/control state 恢复。
- 关联 checklist：CHK-P3-001 至 CHK-P3-009。

### TODO-P3-010 Build Phase 3 Race and Recovery Tests

- 目标：覆盖 intervention ordering、pause races、late response、moderator failure 和 arbitration。
- 涉及区域：Python/JS tests、fake delayed providers。
- 输入：Phase 3 implementation。
- 输出：deterministic concurrency fixtures。
- 依赖：TODO-P3-001 至 TODO-P3-009。
- 完成标准：CHK-P3-001 至 CHK-P3-010 自动覆盖；无 flaky timing assertion。
- 关联 checklist：CHK-P3-001 至 CHK-P3-010。

### TODO-P3-011 Run Phase 3 Self-Test Gate

- 目标：独立验收用户实时控制与裁决。
- 涉及区域：自动测试、浏览器 E2E、人工三 AI 场景。
- 输入：TODO-P3-010。
- 输出：Phase 3 测试记录。
- 依赖：TODO-P3-010。
- 完成标准：含插话、点名、暂停继续和裁决的完整流程通过。
- 关联 checklist：CHK-P3-001 至 CHK-P3-011。

## Combined Phase 1-3 Completion

### TODO-ALL-001 Run Full Regression Matrix

- 目标：确认 Phase 1-3 合并后无跨 Phase 回归。
- 涉及区域：meeting tests、chat、Codex activity、projects、office animation。
- 输入：全部 Phase 实现。
- 输出：完整测试报告。
- 依赖：TODO-P1-010、TODO-P2-010、TODO-P3-011。
- 完成标准：CHK-ALL-001、CHK-ALL-002 通过。
- 关联 checklist：CHK-ALL-001、CHK-ALL-002。

### TODO-ALL-002 Verify Scope Boundary and Documentation

- 目标：防止把 Phase 4-7 功能误作为已实现。
- 涉及区域：UI copy、API docs、skills、requirement status。
- 输入：最终实现。
- 输出：限制说明和开发文档。
- 依赖：TODO-ALL-001。
- 完成标准：AI 申请、自动汇总、任务暂停、行动项建任务均明确未实现。
- 关联 checklist：CHK-ALL-003。

### TODO-ALL-003 Record Implementation and Test Status

- 目标：更新 checklist 结果、status.json 和母需求关联状态。
- 涉及区域：本子需求及 parent requirement docs。
- 输入：测试报告和人工验收。
- 输出：implementation_done/tested 状态记录。
- 依赖：TODO-ALL-001、TODO-ALL-002。
- 完成标准：每个 Phase 的测试结果和待用户确认节点清晰记录。
- 关联 checklist：全部。
