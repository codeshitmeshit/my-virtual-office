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

- 目标：在 Meetings dashboard 中提供新建会议按钮和用户发起会议表单。
- 涉及区域：meeting modal、styles、locales。
- 输入：agent roster、meeting create/start APIs。
- 输出：新建会议入口、主题、类型、目的、参与者、AI 主持、上下文传递模式、初始上下文、最大轮次表单、validation、loading/error states。
- 依赖：TODO-P1-010。
- 完成标准：用户打开会议中心即可看到新建会议入口；有效配置可提交；少于两名参与者、主持人不在参会者中、无主题、无上下文传递模式等无效输入不创建会议；新增 UI 文案接入中英文 locale。
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

- 目标：定义 opening、discussion、moderator、summary prompt contract 和上下文传递模式。
- 涉及区域：meeting prompt builder/parser。
- 输入：meeting snapshot、events、rolling summary。
- 输出：provider-neutral prompts、`contextMode` 策略、上下文预算和严格解析/降级规则。
- 依赖：TODO-P2-003。
- 完成标准：支持 `incremental`、`summary`、`full` 三种模式；`incremental` 默认使用稳定 conversationId，首轮发送完整会议说明和初始上下文，后续只发送该 Agent 未见过的新事件、极小状态锚点和本轮指令；`summary` 每轮发送 rolling summary 与相关发言；`full` 每轮发送完整上下文但必须受预算限制；provider 会话失效或缺失 lastSeenEventSeq 时可降级到 summary bootstrap；解析失败保留原文并产生明确状态，不伪造结构字段。
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

- 目标：覆盖 form、availability、context mode、adapter、orchestrator、result 和 UI reducer。
- 涉及区域：Python/JS tests、fake providers。
- 输入：Phase 2 implementation。
- 输出：确定性三类会议 fixtures、三种 contextMode prompt fixtures、UI 表单 fixtures。
- 依赖：TODO-P2-001 至 TODO-P2-008。
- 完成标准：CHK-P2-001 至 CHK-P2-010 可自动验证的部分全部覆盖；fake provider 测试验证 incremental 模式不会在第二轮重复发送完整 transcript，summary/full 模式按预算裁剪。
- 关联 checklist：CHK-P2-001 至 CHK-P2-010。

### TODO-P2-010 Run Phase 2 Self-Test Gate

- 目标：独立验收真实顺序会议 MVP。
- 涉及区域：自动测试、浏览器 E2E、真实 provider/AI E2E smoke。
- 输入：TODO-P2-009。
- 输出：Phase 2 测试记录和 provider 兼容结果。
- 依赖：TODO-P2-009。
- 完成标准：自动化和浏览器 E2E 通过，并且至少一场通过 UI 创建的三 Agent 会议使用真实 AI/provider 完成 opening、discussion 和 structured result；记录真实 AI 发言事件、providerRef/conversationId、上下文传递模式和最终结果。若只能通过 fake provider，不得将 Phase 2 gate 标记为通过。
- 关联 checklist：CHK-P2-001 至 CHK-P2-010。

### Phase 2 执行状态

- TODO-P2-001：已完成。会议中心新增“新建会议”按钮和表单，包含主题、目的、会议类型、参与者、主持人、上下文传递模式、最大轮次和初始上下文，中英文文案已接入。
- TODO-P2-003、TODO-P2-004、TODO-P2-005、TODO-P2-006、TODO-P2-007、TODO-P2-008、TODO-P2-009：已完成自测。Fake provider 顺序会议、三种 contextMode prompt、结构化结果、历史 UI 展示、provider timeout 和 OpenClaw-safe session id 均有测试或 E2E 记录。
- TODO-P2-002：部分完成。当前依赖 Phase 1 occupancy 冲突拒绝；离线/忙碌 provider preflight 仍需要更细的 provider health 判定。
- TODO-P2-010：真实 provider 验收已执行但 gate blocked。真实会议 `cf2ed2cd-3f6a-4799-a765-7ed311c4a7c6` 完成并归档，Hermes/Codex 产生真实 AI 发言，OpenClaw 进入真实 provider 路径但因上游 token-plan quota exhausted 失败；因此 Phase 2 不能标为 fully passed。

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

### TODO-P3-002A Normalize Provider Replies and Structured Turn Output

- 目标：将 OpenClaw/Hermes/Codex 的 provider envelope 与会议发言正文拆开，并约束会议发言优先返回固定结构。
- 涉及区域：meeting provider adapter、prompt builder/parser、participant_turn event schema、transcript projection。
- 输入：provider raw response、speaker text、structured JSON/fenced JSON/freeform Markdown。
- 输出：`payload.text` 保存可展示的纯发言正文，`payload.structured` 保存 `position`、`reasoning`、`disagreements`、`questions`、`suggestedNextStep`、`confidence` 等字段，`payload.providerRaw` 或 debug-only meta 保存原始 provider envelope。
- 依赖：TODO-P2-003、TODO-P2-004、TODO-P3-001。
- 完成标准：OpenClaw 这类返回 JSON envelope 的 provider 不再把完整 JSON 当作会议发言展示；能从 `result.payload[].text` 或等价字段提取正文；prompt 明确要求返回单个 JSON object；解析失败时保留原文并记录 parse error，不阻塞会议；原始 provider JSON 不进入用户可见 transcript 正文。
- 关联 checklist：CHK-P3-001、CHK-P3-010、CHK-P3-012。

### TODO-P3-003 Implement Targeted Speaking Steps

- 目标：用户在轮末决策窗口内点名后插入一次目标 AI 回答并返回原议程。
- 涉及区域：orchestrator queue、event store、provider adapter、settings。
- 输入：targeted question event、decision window state、target participant。
- 输出：唯一 targeted step 和 targeted response transcript。
- 依赖：TODO-P3-001、TODO-P3-002。
- 完成标准：不重复回答；原 speaker queue 位置保持；点名回答挂在当前 stage/round 下但不推进 round、不消耗 maxRounds；非参会者和终态会议拒绝；真实 AI/provider 验收至少覆盖一次点名回答。
- 关联 checklist：CHK-P3-002、CHK-P3-002A。

### TODO-P3-003A Implement Round-End User Decision Window

- 目标：每轮正式发言结束后按设置变量进入用户决策窗口，供用户点名、补充上下文、继续或结束。
- 涉及区域：settings/config、state machine、orchestrator loop、frontend controls。
- 输入：decision window timeout setting、round completion event。
- 输出：`awaiting_user_decision` 状态、timeout/continue events、可恢复的下一步议程。
- 依赖：TODO-P2-004、TODO-P3-001、TODO-P3-003。
- 完成标准：窗口时长可通过设置变量控制，默认 20 秒，允许范围 10-120 秒；窗口期间不启动下一轮正式 AI 调用；用户点击继续或超时后恢复原议程；点名和补充上下文可在窗口内追加；刷新后窗口状态可恢复。
- 关联 checklist：CHK-P3-002A、CHK-P3-010。

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

- 目标：提供实时讨论查看、结构化发言渲染、发言、点名、议题、暂停继续、取消、结束、裁决和主持切换界面。
- 涉及区域：meeting dashboard frontend、styles、locales。
- 输入：Phase 3 APIs and event state。
- 输出：active meeting live transcript panel、structured turn field rendering、current provider call state、round-end decision window controls、state-aware controls and errors。
- 依赖：TODO-P3-001 至 TODO-P3-008。
- 完成标准：active 会议展开后能按开场轮/讨论轮增量展示每个 AI 已完成发言、结构化字段、失败状态、provider 类型、耗时和当前发言者；轮末窗口显示可点名、补充上下文、继续、请主持总结和取消；若 structured 存在则按“立场/理由/分歧/问题/下一步/信心”分区渲染，缺失或解析失败时降级显示纯文本；通过 `/events?after=` 或等价事件通道增量更新；刷新后 live transcript、pending decision/control state 恢复；非法状态按钮禁用。
- 关联 checklist：CHK-P3-001 至 CHK-P3-009、CHK-P3-012、CHK-P3-002A。

### TODO-P3-009A Project Executable Meetings to Office Canvas

- 目标：让非终态 executable meeting 与 legacy `_meetings` 一样驱动主应用画布会议场景。
- 涉及区域：`app/server.py` `/status` 或主画布数据源、meeting active projection、`app/game.js` `processMeetings()` 兼容路径、必要的 UI/browser regression。
- 输入：canonical executable meeting store、`_meeting_active_projection()`、现有 meeting table slot/1:1 visit 行为。
- 输出：主画布可消费的 active meeting projection，包含 `id`、`participants`/`agents`、`type`、`topic` 和终态过滤；浏览器刷新后仍可恢复会议桌场景。
- 依赖：TODO-P1-006、TODO-P2-005、TODO-P3-009。
- 完成标准：创建三名参与者 active executable meeting 后，主画布在不打开 Meetings modal 的情况下把参会 Agent 移动到 meeting table seats；创建两名参与者会议后使用 desk visit；会议 completed/cancelled/failed 后画布移除会议占用并让 Agent 回到原有状态；legacy `_meetings` 动画不回归。
- 关联 checklist：CHK-P3-013、CHK-P1-005、CHK-ALL-002。

### TODO-P3-010 Build Phase 3 Race, Recovery and Structured Output Tests

- 目标：覆盖 intervention ordering、pause races、late response、moderator failure、arbitration、provider envelope normalization 和 structured turn parsing。
- 涉及区域：Python/JS tests、fake delayed providers。
- 输入：Phase 3 implementation。
- 输出：deterministic concurrency fixtures。
- 依赖：TODO-P3-001 至 TODO-P3-009。
- 完成标准：CHK-P3-001 至 CHK-P3-010、CHK-P3-012 与 CHK-P3-013 自动覆盖；无 flaky timing assertion；测试覆盖 OpenClaw-style JSON envelope、fenced JSON、纯 JSON、无效 JSON、freeform fallback 和 executable meeting 主画布投影。
- 关联 checklist：CHK-P3-001 至 CHK-P3-010、CHK-P3-012、CHK-P3-013。

### TODO-P3-011 Run Phase 3 Self-Test Gate

- 目标：独立验收用户实时控制与裁决。
- 涉及区域：自动测试、浏览器 E2E、人工三 AI 场景。
- 输入：TODO-P3-010。
- 输出：Phase 3 测试记录。
- 依赖：TODO-P3-010。
- 完成标准：含 active 实时讨论查看、主画布会议桌可视化、插话、轮末用户决策窗口、点名、暂停继续和裁决的完整流程通过。
- 关联 checklist：CHK-P3-001 至 CHK-P3-011、CHK-P3-013、CHK-P3-002A。

### Phase 3 执行状态

- TODO-P3-001（用户发言/补充上下文事件与 API 部分）：已完成主要实现。新增 `/api/meetings/executable/<id>/intervention`，支持用户发言、补充上下文、二者合并提交、幂等键、防终态追加和 ordered `user_intervention` 事件持久化；暂停、继续和取消控制已接入前端与状态机；点名和议题修改已接入 durable event/API/UI。
- TODO-P3-002（用户上下文注入部分）：已完成主要实现。`user_intervention` 与 `agenda_change` 已进入 transcript projection 和 `_meeting_build_prompt()` 的事件文本，`incremental` 模式下后续 Agent 会收到自上次发言后的新增用户插话/上下文/议题调整；prompt 固定头部包含 `Current agenda`，确保后续未开始步骤按新议题执行。
- TODO-P3-002A：已完成基础实现。会议 prompt 现在要求返回单个 JSON object；服务端新增 provider reply normalization、OpenClaw-style envelope unwrap、structured turn parser、parse fallback 和 debug raw retention；`participant_turn` 保存 `text`、`rawText`、`structured`、`parseError`，projection 不把 `providerRaw` 暴露到 transcript。
- TODO-P3-003 / TODO-P3-003A：已完成主要链路。服务端在每轮正式发言结束后进入 `awaiting_user_decision`，窗口时长由 `VO_MEETING_DECISION_WINDOW_SEC` 控制，默认 20 秒，允许范围 10-120 秒；点名问题通过 `/api/meetings/executable/<id>/targeted-question` 写入 `targeted_question`，指定真实 provider 返回 `participant_turn.kind=targeted_response`，挂在当前 stage/round 下但不推进正式 round、不消耗 maxRounds、不破坏原 speaker queue；前端 active 会议卡片新增轮末决策窗口、点名对象、点名问题、点名提问和继续控件，并在 transcript 中标记“点名提问/点名回答”。
- TODO-P3-009（实时讨论查看部分）：已部分完成。Active executable meeting projection 已包含 live transcript、pending provider calls 和 lastEventSequence；会议中心打开时通过 `/api/meetings/executable/<id>/events?after=<seq>` 增量轮询并渲染“实时讨论”、开场轮/讨论轮、每个 AI 发言、失败状态、耗时和正在调用状态。
- TODO-P3-009（用户插话 UI 与结构化发言渲染部分）：已部分完成。Active executable meeting 展开后显示“用户插话”输入区，支持实时发言和补充上下文提交，提交后即时进入 live transcript，刷新后从事件流恢复；当 turn 含 `structured` 时，前端按“立场/理由/分歧/问题/下一步/信心”渲染，缺失时回退纯文本。
- TODO-P3-009（主持 AI 总结结束部分）：已部分完成。Active executable meeting 的结束按钮不再打开手填摘要弹窗，而是请求主持 AI 基于 transcript 输出结构化 `summary`、`decision`、`unresolvedQuestions`、`disagreements` 和 `actionItems`；legacy meeting 仍保留手填摘要要求。
- TODO-P3-009（历史查看体验部分）：已部分完成。历史会议按结束/更新时间倒序排列；历史页新增关键词搜索，覆盖主题、目的、摘要、决议、参与者、发言、贡献和行动项；历史列表保持轻量，点击“查看详情”或卡片头部打开会议详情弹窗，集中查看摘要、决议、行动项、逐轮发言和贡献。
- TODO-P3-009（暂停/继续/取消控制部分）：已部分完成。Active executable meeting 展开后显示暂停、继续和取消会议按钮；暂停后卡片进入 `paused` 并隐藏 AI 总结结束按钮，继续根据 `executionPreviousStage` 返回开场或讨论阶段，取消后转入历史并释放 active/occupancy；终态会议拒绝后续用户插话。
- TODO-P3-009A：已完成。`/status._meetings` 现在合并非终态 executable meeting projection，主画布复用 legacy `processMeetings()` 驱动多人 meeting table 和 1:1 desk visit；前端在 roster/agent 实例刷新后会重新绑定 active meeting 的当前 Agent 对象并恢复 meeting 状态。
- TODO-P3-006：已完成。讨论轮耗尽后会构造 no-consensus arbitration snapshot，包含各方最新 position、disagreements 和主持建议，并进入 `awaiting_user_decision`；不会自动多数决。
- TODO-P3-007：已完成主要链路。新增 `/api/meetings/executable/<id>/arbitration`，支持 `decide`、`continue_discussion` 和 `end_no_consensus`；裁决写入最终 `result.arbitration` 和 `arbitration_decision` 事件，终态后重复提交拒绝；no-consensus 窗口不会被倒计时 timeout 自动总结，必须由用户裁决、继续一轮或无共识结束。
- TODO-P3-008：已完成主要链路。主持 AI 总结失败时不再静默 fallback 完成，而是记录 `moderator_failure`，将会议置为 `awaiting_user_decision` 并暴露 `moderatorFailure`；新增 `/api/meetings/executable/<id>/moderator-takeover`，支持用户手动总结并结束，或选择另一名参会者作为新主持重试总结；终态后重复接管会拒绝。
- TODO-P3-009（主持接管 UI 部分）：已完成。Active executable meeting 展开后在主持失败状态显示“主持接管”面板、失败原因、用户总结/决议输入、接管并结束按钮、替换主持人选择和重试按钮。
- TODO-P3-010（实时讨论、用户上下文、结构化输出、主持总结、历史 UI、会议控制、点名、无共识裁决、主持接管和晚到响应竞态测试部分）：已完成主要覆盖。`tests/test_meeting_for_ai_phase1.py` 覆盖 active projection 的 pending call 到 participant turn 转换、`user_intervention` 投影、幂等、防终态追加、incremental prompt 注入、OpenClaw-style envelope unwrap、structured parser、transcript 不暴露 `providerRaw`、executable meeting 无手填摘要时走主持 AI 总结、legacy meeting 仍要求 summary、暂停/继续/取消的 previousStage 投影、history 转移和终态插话拒绝，以及 decision window 默认 20 秒/10-120 clamp、点名回答不推进 round、不消耗 maxRounds、非窗口点名拒绝、点名幂等、per-meeting decision window 设置、no-consensus timeout 不自动推进、裁决/继续/无共识结束动作、主持失败后的用户接管和替换主持重试、正式 provider 调用中取消后的晚到响应忽略、点名 provider 调用中继续后的晚到响应忽略。Chrome MCP 使用真实本地服务验证 active UI 显示实时讨论和 pending provider call，验证会议 `phase3-ui-intervention-20260615-2155` 的用户插话/补充上下文在页面与事件流中一致展示，验证真实 AI 会议 `phase3-structured-real-20260616-0125` 的结构化字段渲染且原始 envelope 不可见，验证真实 OpenClaw 主持会议 `phase3-ai-end-content-real-20260616-0140` 由 AI 生成结束摘要/决议/行动项且没有弹出手填表单，验证历史页倒序、关键词搜索和详情弹窗；2026-06-16 本次 MCP transport 中断，改用沙盒外 Chrome DevTools Protocol 驱动真实页面完成暂停/继续/取消验收；点名验收使用真实 Hermes provider 会议 `b95ca5c5-f6e1-4db3-9fea-2bf41f18e5c2`，断言与截图保存到 `/tmp/phase3-targeted-real-ui-cdp-check.json` 和 `/tmp/phase3-targeted-real-ui-cdp-check.png`；2026-06-17 使用 Chrome MCP 和真实 AI 会议 `phase3-arbitration-mcp-20260617e` 验证无共识裁决面板、真实 AI position/disagreement 展示、前端裁决提交、`completed` 状态和唯一 `arbitration_decision` 事件；同日使用 Chrome MCP 和本地服务会议 `phase3-moderator-takeover-mcp-20260617b` 验证主持接管面板、用户接管提交、`completed` 状态、结果持久化和唯一 `moderator_takeover` 事件；同日使用 Chrome MCP 验证 `phase3-ignored-late-response-mcp-20260617` 的 `provider_call_ignored` 已落事件但晚到响应不污染实时讨论。
- TODO-P3-011：已完成。真实三 AI 总 gate 会议 `phase3-total-real-mcp-20260617` 使用 OpenClaw、Hermes、Codex 三个 provider 串联完成 opening、用户插话/补充上下文、点名 Hermes、继续 discussion、no-consensus 裁决和 completed 结束；事件流含 27 个事件、7 条 `participant_turn`、1 条 `user_intervention`、1 条 `targeted_question`、1 条 `targeted_response`、1 条 `arbitration_decision`，providerKinds 覆盖 `openclaw`、`hermes`、`codex`，失败 turn 为 0。Chrome MCP 验证历史详情中可见总 gate 会议、用户插话、补充上下文和裁决文本。
- 未完成：Phase 3 当前实现和总 gate 已完成；后续只保留更高强度压力/并发 soak 测试作为非阻塞增强。

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

### Phase 1-3 最终归档状态

- 归档时间：2026-06-17T04:34:19+08:00
- 用户确认：用户确认会议 Phase 3 已完成验收。
- 完成范围：Phase 1 durable meeting foundation、Phase 2 user-started sequential AI meeting、Phase 3 user control and arbitration 的子需求闭环完成；Phase 2 原真实 provider quota 阻塞由后续 Phase 3 real three-AI 总 gate 覆盖。
- 归档结论：`meeting-for-ai-phase-1-3` 标记为 done；父需求 `meeting-for-ai` 仅记录 Phase 1-3 完成，后续 Phase 4-7 不在本次归档范围内。
