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
- 验证方法：打开 Meetings dashboard，点击新建会议按钮，测试三种会议类型、参与者、主持人、上下文传递模式、初始上下文和最大轮次表单。
- 预期结果：用户能从会议中心自然进入新建会议表单；有效配置可创建；少于两名参与者、主持人不在名单、无主题、无上下文模式等输入被阻止。

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
- 验证方法：分别以 `incremental`、`summary`、`full` 三种上下文传递模式运行 fake provider 会议，检查每次 provider 收到的 prompt 和保存的 transcript。
- 预期结果：`incremental` 模式首轮发送完整会议说明和初始上下文，后续只发送自该 Agent 上次发言后的新增事件、极小状态锚点和本轮指令；`summary` 模式发送状态锚点、rolling summary、相关发言和本轮指令；`full` 模式发送完整会议配置、初始上下文和 transcript，并受预算限制；原始发言与结构化贡献均可追踪。

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
- 验证方法：通过 UI 新建并完成至少三名可用 AI 的真实会议；必须至少执行一次真实 provider/AI 调用验收，不能只用 fake provider 或 mock；记录各 Agent 的实际发言事件、provider 信息和最终结构化结果。
- 预期结果：会议从新建到 completed 全程可追踪并产生结构化结果；真实 AI 发言进入事件流；上下文传递模式按表单配置生效；如果真实 AI 环境不可用，Phase 2 不得标记为 gate passed，只能记录阻塞原因。

## Phase 3: User Control and Arbitration

### CHK-P3-001 Live Discussion View, User Statement and Context

- 关联需求：用户在会议进行中查看实时讨论、实时发言和补充上下文。
- 验证方法：在 active opening 和 discussion 阶段展开会议卡片，查看已完成的 AI 发言、正在发言的 AI、provider 调用中状态和逐轮 transcript；随后提交用户消息与新上下文。
- 预期结果：实时讨论按开场轮/讨论轮增量展示，每个 AI 的内容、失败状态和耗时可见；刷新后从事件流恢复；用户事件先持久化；后续 AI turn 可见；已完成发言不改变。

### CHK-P3-002 Targeted Question

- 关联需求：点名 AI。
- 验证方法：在一轮正式发言结束后的用户决策窗口中，用户向指定参与者提问。
- 预期结果：插入唯一 targeted step；指定 AI 回答一次；点名回答记录在当前 stage/round 下并标记为 targeted response，但不推进 round、不消耗 maxRounds、不改变原 speaker queue；完成后回到正确议程位置。

### CHK-P3-002A Round-End User Decision Window

- 关联需求：一轮正式发言结束后给用户留出点名、补充上下文或继续的窗口。
- 验证方法：配置 decision window timeout，运行 opening/discussion 一轮到正式 speaker queue 结束；分别验证用户在窗口内点名、补充上下文、点击继续、请求主持总结，以及不操作等待超时。
- 预期结果：正式轮次结束后进入 `awaiting_user_decision` 或等价可审计状态；窗口时长由设置变量控制，默认 20 秒，允许范围 10-120 秒；窗口内不会启动下一轮正式 AI 调用；点名/补充上下文写入事件流；点击继续或超时后恢复原议程，进入下一轮或总结。

### CHK-P3-003 Agenda Change

- 关联需求：调整议题。
- 验证方法：会议中修改 agenda。
- 预期结果：从下一未开始步骤生效；历史事件保留旧议题上下文。
- 当前结果：已实现 `/api/meetings/executable/<id>/agenda-change`，写入 ordered `agenda_change` 事件并更新 meeting `agenda`，保留 `previousAgenda`、reason、stage/round 和 appliesFromSequence；前端 active 会议卡片可调整议题，实时讨论显示“议题调整”；后续 prompt 固定包含 `Current agenda`，并在 incremental 事件文本中包含用户调整议题记录。

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
- 验证方法：并发提交暂停、用户消息、点名、decision window timeout 和 provider completion。
- 预期结果：按序列确定唯一结果；无重复 turn、非法状态或丢失用户事件；超时自动继续与用户点名/继续操作互斥并可审计。

### CHK-P3-011 Phase 3 End-to-End Gate

- 关联需求：用户可完整控制会议。
- 验证方法：人工执行一次含实时讨论查看、插话、轮末用户决策窗口、点名、暂停继续和争议裁决的三 AI 会议。
- 预期结果：实时讨论可见且随事件增量更新；每轮结束后按设置变量进入或跳过用户决策窗口；所有控制可用；会议最终生成一致结果，刷新后仍可审计。

### CHK-P3-012 Structured Turn Output and Provider Envelope Normalization

- 关联需求：会议发言可结构化处理和渲染，provider 原始 envelope 不污染 transcript。
- 验证方法：分别用 OpenClaw-style JSON envelope、Hermes/Codex 普通文本、纯 JSON、fenced JSON、无效 JSON 和 freeform Markdown 驱动会议 turn；检查 `participant_turn` 事件、active/history projection 和前端 live transcript。
- 预期结果：OpenClaw 等 provider 的原始 JSON envelope 被保存到 debug/meta 字段但不作为发言正文展示；会议正文从 `result.payload[].text` 或等价字段提取；合法结构化输出进入 `payload.structured`；UI 优先按“立场、理由、分歧、问题、下一步、信心”渲染，解析失败时显示纯文本并保留 parse error；原始发言与结构化字段均可追溯到事件序号。

### CHK-P3-013 Active Meeting Office Canvas Presence

- 关联需求：可执行会议进行中时，主应用画布也必须显示 AI 正在开会。
- 验证方法：创建一场至少三名参与者的非终态 executable meeting，打开主应用画布但不依赖 Meetings modal；检查 `/status` 或等价主画布数据源包含该会议投影，并在浏览器中观察参与者移动到 meeting table seats。再创建两名参与者会议，验证沿用 1:1 desk visit 行为；结束/取消会议后验证参与者离开会议状态并回到自身任务或空闲状态。
- 预期结果：active executable meeting 与 legacy `_meetings` 一样驱动画布会议场景；多人会议在存在 `meetingTable` 家具时围坐会议桌，不存在时使用现有聚集 fallback；终态会议不再占用画布会议状态；浏览器刷新后可从服务端状态恢复。

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

## Phase 1 验收记录

- 验收时间：2026-06-15T13:53:45+08:00
- 实现范围：新增 executable meeting 持久化 store、ordered event stream、版本与事件序号、状态机转换校验、participant occupancy、detail/events/transition/reconcile API、legacy active/history projection、`/api/meetings/end` 对 executable meeting 的 completed 转换支持，以及会议中心 executable stage/version/round/moderator 展示。
- 范围边界：Phase 1 不调用 AI，不实现 provider adapter、orchestrator、用户实时干预、AI 发起申请、自动上下文汇总、任务暂停恢复或行动项建项目任务。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖创建持久化、事件序号、idempotency key、占用冲突、非法转换、合法转换、history projection、events after sequence 和 reconcile。
- HTTP 验收：隔离状态目录 `VO_STATUS_DIR=/tmp/vo-meeting-phase1-e2e` 下启动 `http://127.0.0.1:8090`，验证 `POST /api/meetings/executable/create`、`GET /api/meetings/active`、`GET /api/meetings/executable/<id>`、`GET /api/meetings/executable/<id>/events?after=0`、occupancy conflict 409、`POST /api/meetings/executable/<id>/transition` 和 `GET /api/meetings/executable/reconcile`。
- Chrome MCP E2E：打开本地服务，调用前端会议中心并展开会议卡片，确认 `Phase 1 Browser Acceptance` 显示 `Executable · active_opening`、`Stage: active_opening`、`Version: 2`、`Round: 0/2`、`Moderator: main` 和三名参与者；截图保存至 `/tmp/meeting-phase1-e2e.png`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`.venv/bin/python tests/test_project_execution.py`、`.venv/bin/python tests/test_feishu_sync.py`、`node --check app/game.js`、`node --check app/projects.js`、`git diff --check` 均通过。`tests/test_project_execution.py` 仍有已知非致命 gateway 连接失败警告，最终输出 `ok`。
- Phase 1 Gate：CHK-P1-001 至 CHK-P1-009 自测通过；可以进入 Phase 2，但整个 `meeting-for-ai-phase-1-3` 仍未全局 tested/done，Phase 2 和 Phase 3 仍待实施。
- 汉化补充：2026-06-15T13:58:27+08:00 将 Phase 1 新增 UI 标签接入 `i18n.t()`，并在 `app/locales/en.json` 与 `app/locales/zh.json` 增加 `meeting_executable`、`meeting_stage`、`meeting_version`、`meeting_round`、`meeting_moderator`。

## Phase 2 验收记录

- 验收时间：2026-06-15T20:20:00+08:00
- 实现范围：新增会议中心“新建会议”入口和表单、参与者/主持人/contextMode/maxRounds/初始上下文提交、Phase 2 sequential runner、provider adapter、opening/discussion 顺序发言、rolling summary、`incremental`/`summary`/`full` prompt 策略、结构化 result、完成会议历史展示、真实 provider 超时配置 `VO_MEETING_PROVIDER_TIMEOUT_SEC`、provider 异常落事件继续推进，以及 OpenClaw workflow session id 安全化。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖 fake provider 顺序会议完成、incremental 第二轮只传增量、summary/full prompt 模式、provider timeout 注入到 Codex/Hermes/OpenClaw 路径，以及 OpenClaw session key 不含冒号。
- Fake/UI 验收：隔离状态目录 `VO_STATUS_DIR=/tmp/vo-meeting-phase2-ui` 与 `VO_MEETING_FAKE_PROVIDER=1` 下启动本地服务，通过 Chrome MCP 在 Meetings dashboard 点击“新建会议”，选择 3 个 Agent、`contextMode=incremental`、提交并完成会议，确认中文 UI、`completed` 状态、上下文模式和“主要贡献”展示。
- 真实 AI 验收：隔离状态目录 `VO_STATUS_DIR=/tmp/vo-meeting-phase2-real-final` 与 `VO_MEETING_PROVIDER_TIMEOUT_SEC=25` 下启动本地服务，运行真实会议 `cf2ed2cd-3f6a-4799-a765-7ed311c4a7c6`，参与者 `main`、`hermes-default`、`codex-local`，`contextMode=incremental`，`maxRounds=1`。会议完成为 `completed`，产生 18 个事件、6 次 `provider_call_started`、6 次 `participant_turn` 和结构化 result；Hermes/Codex 产生 4 次真实 AI 成功发言，OpenClaw 进入真实 provider 路径但因上游 `token-plan quota has been exhausted` 失败。
- Chrome MCP 真实 UI 验收：打开 `http://127.0.0.1:8090` 的 Meetings history，展开真实会议卡，确认 `可执行会议 · completed`、`阶段: completed`、`版本: 18`、`轮次: 1/1`、`上下文模式: incremental`、SUMMARY 和“主要贡献”可见；截图保存至 `/tmp/meeting-phase2-real-e2e-expanded.png`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`.venv/bin/python tests/test_project_execution.py`、`.venv/bin/python tests/test_feishu_sync.py`、`node --check app/game.js`、`node --check app/projects.js`、locale JSON 校验和 `git diff --check` 均通过。
- Phase 2 Gate：CHK-P2-001、CHK-P2-003、CHK-P2-004、CHK-P2-005、CHK-P2-007、CHK-P2-008、CHK-P2-009 的实现和自测通过；CHK-P2-010 已执行真实 provider 验收但不标记为完全通过，因为三 Agent happy path 受 OpenClaw 上游 quota 阻塞。当前可归档为“实现完成，真实 gate 外部 quota blocked”，不能进入 Phase 3 gate。

## Phase 3 部分验收记录

- 验收时间：2026-06-15T21:58:00+08:00
- 实现范围：完成 CHK-P3-001 的实时讨论查看、用户发言和补充上下文子集；新增 active meeting live transcript/pending provider call projection、前端 `/events?after=` 增量轮询、`/api/meetings/executable/<id>/intervention`、ordered `user_intervention` 事件、幂等、防终态追加、用户事件 transcript 展示，以及 incremental prompt 注入用户新增内容。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖 pending provider call 到 participant turn 的实时投影、用户插话/补充上下文投影、幂等提交、终态拒绝和后续 Agent incremental prompt 能看到用户新增事件。
- Chrome MCP 验收：本地服务 `http://127.0.0.1:8090` 下创建 active 会议 `phase3-ui-intervention-20260615-2155`，在 Meetings dashboard 展开会议并通过 UI 提交“用户插话验收：请先比较实时方案风险。”与“补充上下文验收：上线窗口只有 30 分钟，必须保留回滚路径。”；页面显示“用户插话”“实时讨论”、用户发言和补充上下文，后端事件流包含 `user_intervention`，active projection transcript 与页面一致。截图保存至 `/tmp/phase3-user-intervention-check.png`，断言输出保存至 `/tmp/phase3-user-intervention-check.json`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js`、locale JSON 校验和 `git diff --check` 均通过。
- Phase 3 Gate：当前仅完成实时讨论、用户插话和补充上下文子集；点名、议题修改、暂停继续、取消/提前结束、无共识裁决和主持接管仍未完成，因此 CHK-P3-011 不能标记通过。

## Phase 3 结构化发言补充验收记录

- 验收时间：2026-06-16T01:22:00+08:00
- 实现范围：完成 CHK-P3-012 的基础实现；会议 turn prompt 改为要求单个 JSON object，服务端新增 provider reply normalization、OpenClaw-style JSON envelope unwrap、structured turn parser、parse fallback、`rawText`/`structured`/`parseError` 事件字段和 `providerRaw` debug retention；transcript projection 不暴露 `providerRaw`。
- 前端范围：live/history transcript 若存在 `structured`，按“立场、理由、分歧、问题、下一步、信心”分区渲染；无结构化字段或解析失败时显示纯文本，并保留 fallback 标记。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖 OpenClaw-style envelope unwrap、结构化字段解析、`providerRaw` 不进入 transcript projection、以及 fake provider structured output 的完整会议事件保存。
- Chrome MCP 真实 AI 验收：本地服务 `http://127.0.0.1:8090` 以普通 provider 配置运行真实会议 `phase3-structured-real-20260616-0125`，参与者为 `main`/OpenClaw、`hermes-default`/Hermes、`codex-local`/Codex。会议历史页展开后显示“立场/理由/分歧/问题/下一步/信心”等结构化字段；真实 OpenClaw/Hermes/Codex 成功发言共 5 条进入 structured 渲染；另有一次 Codex 真实 timeout 作为失败文本保留并显示“已保留原文”；页面断言 `rawEnvelopeVisible: false`。截图保存至 `/tmp/phase3-real-structured-mcp-check.png`，断言输出保存至 `/tmp/phase3-real-structured-mcp-check.json`。
- 确定性回归：fake provider 会议 `phase3-structured-ui-20260616-0119` 仅作为结构化 UI 稳定回归，不作为验收依据；截图 `/tmp/phase3-structured-ui-check.png`，断言 `/tmp/phase3-structured-ui-check.json`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js`、locale JSON 校验和 `git diff --check` 均通过。

## Phase 3 主持 AI 总结结束补充验收记录

- 验收时间：2026-06-16T01:44:00+08:00
- 实现范围：active executable meeting 的结束按钮改为“请主持人总结并结束”，点击后不打开手填摘要/决议/行动项表单，而是 POST `/api/meetings/end` 并由主持 AI 基于 transcript 生成结构化 `summary`、`decision`、`unresolvedQuestions`、`disagreements` 和 `actionItems`；legacy meeting 仍保留 summary 必填校验。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖 executable meeting 无手填 summary 时调用主持人总结、生成 actionItems 并完成会议，以及 legacy meeting 无 summary 仍返回错误。
- Chrome MCP 真实 AI 验收：本地服务 `http://127.0.0.1:8090` 以普通 provider 配置运行 active 会议 `phase3-ai-end-content-real-20260616-0140`，会议包含用户插话和补充上下文；通过页面按钮触发结束后，手填弹窗前后均未出现，真实 OpenClaw 主持人 `main` 返回结构化 JSON，总结内容明确引用“主持 AI 自动总结、用户不再手填、actionItems 覆盖前端展示和端到端测试记录”等会议内容；会议进入 `completed`，`result.summary`、`result.decision`、2 条 `result.actionItems` 均存在。流程断言输出保存至 `/tmp/phase3-ai-end-content-real-mcp-check.json`；展开 completed 会议后页面显示 summary、decision、actionItems，且 `manualPromptVisible=false`，截图保存至 `/tmp/phase3-ai-end-content-real-ui-expanded-check.png`，展开态断言保存至 `/tmp/phase3-ai-end-content-real-ui-expanded-check.json`。
- 空 transcript 补充样本：会议 `phase3-ai-end-real-20260616-0130` 也通过真实 OpenClaw 主持人返回结构化 JSON，并明确指出 transcript 为空；该样本仅证明流程触发，不作为有内容会议的主验收依据。
- Fake provider 说明：本项验收未使用 fake provider；fake 仅保留为自动化确定性回归。
- Phase 3 Gate：当前新增“主持 AI 总结结束”子集已通过真实 AI + Chrome MCP 验收；点名、议题修改、暂停继续、取消、无共识裁决和主持接管仍未完成，因此 CHK-P3-011 仍不能标记通过。

## Phase 3 历史查看体验补充验收记录

- 验收时间：2026-06-16T01:52:00+08:00
- 实现范围：会议历史记录按结束/更新时间倒序展示；历史页新增关键词搜索框；历史列表卡片展示摘要入口，点击卡片或“查看详情”打开独立详情弹窗，详情中集中展示元信息、参与者、摘要、决议、行动项、逐轮发言、Agent responses 和 contributions。
- Chrome MCP 验收：本地服务 `http://127.0.0.1:8090` 打开 Meetings dashboard 后切换到历史页，断言 `historyCount=10`、`sortedDesc=true`、搜索框可见且 placeholder 为“搜索会议主题、摘要、发言或行动项”；输入关键词 `Phase 3 ` 后列表从“介绍一下你自己”等全部历史过滤为 Phase 3 相关会议；点击“查看详情”后 `meetingDetailModal` 可见，详情标题为 `Phase 3 用户插话验收`，并检测到 summary/action item 内容。截图保存至 `/tmp/meeting-history-search-detail-mcp-check.png`，断言输出保存至 `/tmp/meeting-history-search-detail-mcp-check.json`。
- Phase 3 Gate：该项仅补齐历史查看体验，不代表点名、议题修改、暂停继续、取消、无共识裁决和主持接管完成。

## Phase 3 暂停继续取消控制补充验收记录

- 验收时间：2026-06-16T04:57:00+08:00
- 实现范围：active executable meeting 卡片新增暂停、继续和取消会议按钮；active projection 暴露 `executionPreviousStage`，用于前端从 `paused` 恢复到开场或讨论阶段；取消会议进入 `cancelled` 终态并从 active 列表移入历史列表；终态会议拒绝后续用户插话。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 新增暂停/继续/取消控制测试，覆盖 `active_opening -> paused -> active_opening -> cancelled`、`executionPreviousStage` active projection、history projection 和终态插话 409。
- 浏览器验收：本地服务 `http://127.0.0.1:8090` 下创建会议 `531b861a-36e0-4945-9d2e-ec38f955c746`，通过沙盒外 Chrome DevTools Protocol 驱动真实页面打开 Meetings dashboard、展开会议卡片、点击暂停、继续和取消；页面断言暂停后只显示“继续”，继续后恢复 `active_opening` 并显示“暂停”，取消后自动切换历史记录并显示 `cancelled`；API 断言 active 列表不再包含该会议、history 状态为 `cancelled`、终态插话返回 409。截图保存至 `/tmp/phase3-pause-resume-cancel-browser-check.png`，断言输出保存至 `/tmp/phase3-pause-resume-cancel-browser-check.json`。
- MCP 说明：本次尝试调用 Chrome MCP 时工具层持续返回 `Transport closed`；为避免阻塞验收，按用户允许的沙盒外环境要求使用真实 Chrome + DevTools Protocol 完成等价端到端验收。服务端和页面链路均为真实本地服务，未使用 fake provider；该控制流不触发 AI 生成。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。
- Phase 3 Gate：暂停继续取消子集已通过；点名、议题修改、无共识裁决和主持接管仍未完成，因此 CHK-P3-011 仍不能标记通过。

## Phase 3 主画布会议投影补充验收记录

- 验收时间：2026-06-16T14:45:00+08:00
- 实现范围：`/status._meetings` 合并 active executable meeting projection，使主画布在不打开 Meetings modal 的情况下也能消费 AI 会议；前端 `processMeetings()` 对已存在会议增加 Agent 对象 rebind 和 meeting 状态恢复，避免 roster 刷新后 `activeMeetings` 保存旧 Agent 引用导致画布状态丢失。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 新增 `/status` canvas meeting projection 测试，覆盖三人 executable meeting 进入 `_meetings`、保留 `participants`/`agents`/`type=group`、保留 legacy meeting 并在 cancel 后从 projection 移除。
- 浏览器验收：沙盒外本地服务 `http://127.0.0.1:8138` 下使用真实 active executable meeting `1bae4cbd-2929-4689-9fc1-511ff7bce617`，通过 Chrome DevTools Protocol 打开主画布并主动触发 `pollStatus()`；页面断言 `activeMeetings` 包含该会议，`main`、`hermes-default`、`codex-local` 三个 Agent 均进入 `state=meeting`，`meetingId` 指向该会议，且分配 3 个 meeting table slots。截图保存至 `/tmp/phase3-canvas-meeting-projection-check.png`，断言输出保存至 `/tmp/phase3-canvas-meeting-projection-check.json`。
- MCP 说明：本次 Chrome MCP 工具层仍返回 `Transport closed`，因此按用户允许的沙盒外测试要求使用真实 Chrome + DevTools Protocol 完成等价端到端验收。该验收使用真实本地服务和已有真实 AI 会议数据，但不触发新的 AI 生成。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。
- Phase 3 Gate：主画布会议投影子集已通过；点名、议题修改、无共识裁决和主持接管仍未完成，因此 CHK-P3-011 仍不能标记通过。

## Phase 3 点名与轮末决策窗口补充验收记录

- 验收时间：2026-06-16T15:45:00+08:00
- 实现范围：每轮正式发言完成后进入 `awaiting_user_decision`；窗口时长由 `VO_MEETING_DECISION_WINDOW_SEC` 控制，默认 20 秒，允许范围 10-120 秒；窗口内支持点名指定参会 Agent 回答，点名问题记录为 `targeted_question`，点名回答记录为 `participant_turn.kind=targeted_response`，并挂在当前 `stage/round` 下，不推进正式 round、不消耗 maxRounds、不改变原 speaker queue；前端 active 会议卡片新增轮末决策窗口、点名对象、点名问题、点名提问和继续控件，transcript 中显示“点名提问/点名回答”。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 新增 decision window 默认 20 秒与 10-120 clamp 测试；新增点名测试，覆盖 opening 轮完成后进入 `awaiting_user_decision`、`decisionForStage=active_opening`、`decisionForRound=0`、`decisionNextStage=active_discussion`、点名回答仍为 `active_opening round=0`、会议仍停留在 `awaiting_user_decision`、幂等点名不重复、非参会者拒绝、窗口继续后进入下一正式阶段、非窗口点名拒绝。
- 真实 AI 验收：按用户要求避开 `8090/8091`，在 `http://127.0.0.1:8038`、WS `8039` 启动当前代码服务，创建真实会议 `b95ca5c5-f6e1-4db3-9fea-2bf41f18e5c2`，参与者 `main`/OpenClaw 与 `hermes-default`/Hermes，`maxRounds=1`，未设置 fake provider。opening 轮真实调用 OpenClaw 与 Hermes 后进入 `awaiting_user_decision`，`decisionWindowSec=20`、`decisionForStage=active_opening`、`decisionForRound=0`、`decisionNextStage=active_discussion`。随后向 `hermes-default` 点名提问，真实 Hermes provider 返回 `providerKind=hermes`、`kind=targeted_response`、`stage=active_opening`、`round=0`，会议仍停留在 `awaiting_user_decision` 且 `round=0`。
- 浏览器验收：Chrome MCP 工具层仍返回 `Transport closed`；按用户允许的沙盒外环境要求，使用真实 Chrome DevTools Protocol，应用服务端口 `8038/8039`、Chrome CDP 端口 `8040`。页面打开 Meetings dashboard 并展开真实会议后，断言轮末决策窗口、点名提问按钮、继续按钮、点名提问 marker、点名回答 marker 和真实 Hermes 回答文本均可见；页面数据中 `meetingStage=awaiting_user_decision`、`meetingRound=0`、`decisionWindowSec=20`，transcript 包含普通 opening 发言、`targeted_question` 和 `targeted_response`。截图保存至 `/tmp/phase3-targeted-real-ui-cdp-check.png`，断言输出保存至 `/tmp/phase3-targeted-real-ui-cdp-check.json`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。
- Phase 3 Gate：点名与轮末决策窗口子集已通过真实 AI + 浏览器验收；议题修改、无共识裁决、主持接管和更完整的并发/超时竞态测试仍未完成，因此 CHK-P3-011 仍不能标记通过。

## Phase 3 轮末继续竞态修复验收记录

- 验收时间：2026-06-16T17:03:00+08:00
- 修复范围：轮末“继续”按钮不再先调用 `/transition` 且不再携带可能过期的 `expectedVersion`，改为直接调用 `/api/meetings/executable/<id>/run`，body 为 `{ action: "continue" }`；倒计时归零自动续跑继续使用 `{ action: "timeout" }`；续跑期间禁用点名/继续控件，避免重复提交。
- 问题原因：倒计时自动续跑或其它事件会推进 meeting version，用户再点击继续时旧页面数据里的 `executionVersion` 已过期，原先 `/transition` 请求会触发 `Meeting version conflict`。
- MCP 验收：创建运行时 fixture `phase3-continue-no-conflict-mcp-20260616`，其处于未过期的 `awaiting_user_decision`；通过 Chrome MCP 打开 `http://127.0.0.1:8038`、展开会议卡并点击“继续”。页面未弹出 alert，后端会议进入 `completed`，事件流包含 `decision_window_closed reason=user_continue` 和后续 `meeting_transitioned`/`meeting_result`，未出现 version conflict。截图保存至 `/tmp/phase3-continue-no-conflict-mcp-check.png`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。

## Phase 3 无共识裁决补充验收记录

- 验收时间：2026-06-17T00:47:00+08:00
- 实现范围：讨论轮耗尽后生成 no-consensus arbitration snapshot，包含真实发言提取出的各方 position、disagreements 和主持建议；active 会议卡片展示“无共识裁决”面板、裁决/理由输入框，以及“采纳裁决并结束”“继续一轮”“无共识结束”三个动作；新增 `/api/meetings/executable/<id>/arbitration`，支持 `decide`、`continue_discussion` 和 `end_no_consensus`；裁决会写入 `result.arbitration`、最终 `decision` 和 `arbitration_decision` 事件。
- 行为修复：创建会议时支持 `decisionWindowSec` 单会话设置，范围沿用 10-120 秒；该设置在 opening 窗口继续到 discussion 后不会丢失。no-consensus 裁决窗口不会被倒计时或 `action=timeout` 自动推进到总结，必须由用户显式裁决、继续讨论或无共识结束。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖单会话窗口期配置与 clamp、no-consensus timeout 不自动推进、decide 完成并写入 result、终态重复提交拒绝、end_no_consensus 完成并保留争议、continue_discussion 扩展 `maxRounds` 并恢复讨论。
- Chrome MCP 真实 AI 验收：按用户指定端口在 `http://127.0.0.1:8038`、WS `8039` 启动本地服务，创建真实 AI 会议 `phase3-arbitration-mcp-20260617e`，未启用 fake provider。真实 AI 在 opening/discussion 轮产生结构化 position/disagreements 后进入 `awaiting_user_decision`，`arbitration.reason=no_consensus`，`decisionWindowSec=120`。Chrome MCP 打开 Meetings dashboard，切回“进行中”并展开该会议，断言“无共识裁决”、两位 AI 的真实 position/disagreements、裁决输入框、理由输入框和三个动作按钮均可见。随后通过页面同一前端函数提交裁决，后端从 `awaiting_user_decision` 转为 `completed`，`result.decision` 等于提交文本，`result.arbitration.action=decide`，事件流中恰好 1 条 `arbitration_decision`，事件 payload 包含原 arbitration snapshot。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 均通过；`git diff --check` 将在本轮最终检查中执行。
- Phase 3 Gate：无共识裁决子集已通过真实 AI + Chrome MCP 验收；主持接管在后续记录中完成，当前仍需更完整的并发/超时竞态测试和完整三 AI 串联 gate，因此 CHK-P3-011 仍不能标记通过。

## Phase 3 主持失败接管补充验收记录

- 验收时间：2026-06-17T01:36:00+08:00
- 实现范围：主持 AI 总结失败时，会议不再静默 fallback 完成；服务端记录失败的主持 `participant_turn`、写入 `moderator_failure` 事件，并把会议置为 `awaiting_user_decision`，active projection 暴露 `moderatorFailure`。新增 `/api/meetings/executable/<id>/moderator-takeover`，支持 `user_takeover` 手动提交总结/决议并结束会议，也支持 `replace_moderator` 选择另一名参会者作为主持人重试总结。
- 前端范围：active 会议卡片在 `moderatorFailure.reason=moderator_failed` 时显示“主持接管”面板，包含失败原因、用户总结、决议、接管并结束、替换主持人和用新主持重试控件；相关文案已接入中英文 locale。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖主持失败进入 `awaiting_user_decision`、active projection 暴露 `moderatorFailure`、用户接管完成并写入 `moderatorTakeover`、替换主持人重试并完成、以及终态后重复接管返回 409。
- Chrome MCP 验收：按用户指定端口保持本地服务 `http://127.0.0.1:8038`、WS `8039` 运行，创建主持失败验收会议 `phase3-moderator-takeover-mcp-20260617b`。Chrome MCP 打开 Meetings dashboard，展开 active 会议后确认“主持接管”、`[ERROR] moderator test failure from MCP fixture`、用户总结、接管并结束、替换主持人和用新主持重试控件均可见。随后通过页面前端函数提交用户总结“`MCP 用户接管总结：主持失败后由用户确认会议结论。`”和决议“`MCP 验收通过用户接管链路。`”，后端会议进入 `completed`，`result.summary`/`result.decision` 持久化，`result.moderatorTakeover.action=user_takeover`，事件流中恰好 1 条 `moderator_takeover` 和 1 条 `meeting_result`。
- 说明：本项 UI/控制链路使用确定性主持失败 fixture 验证；替换主持人重试链路由自动化测试覆盖。Phase 3 最终 gate 仍需真实 AI 完整串联场景统一验收。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 均通过；`git diff --check` 将在本轮最终检查中执行。
- Phase 3 Gate：主持失败接管子集已通过自动化 + Chrome MCP 验收；晚到响应竞态在后续记录中完成，当前剩余完整三 AI 串联总 gate，因此 CHK-P3-011 仍不能标记通过。

## Phase 3 晚到 Provider 响应竞态补充验收记录

- 验收时间：2026-06-17T02:17:00+08:00
- 实现范围：正式发言和点名回答的 provider 调用返回落库前会重新检查会议状态。若会议已暂停、终态、阶段变化或 round 变化，则不写入正式 `participant_turn`，改写可审计的 `provider_call_ignored` 事件，保留 providerRef、conversationId、duration、原文/结构化解析结果、期望 stage/round 和当前 stage/round。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 新增两类竞态测试：正式 provider 调用期间取消会议，晚到响应只写 `provider_call_ignored` 且不产生正式 turn；点名 provider 调用期间用户继续原议程，晚到点名回答只写 `provider_call_ignored` 且不产生 `kind=targeted_response` 的正式 turn。
- Chrome MCP 验收：本地服务使用最新代码重启在 `http://127.0.0.1:8038`、WS `8039`。创建会议 `phase3-ignored-late-response-mcp-20260617`，事件流含 1 条正式发言和 1 条 `provider_call_ignored`。Chrome MCP 打开 Meetings dashboard 并展开会议，确认“实时讨论”和正式发言“正式发言：建议先做竞态防护。”可见；晚到响应文本“晚到响应不应出现在正式发言里”不在页面出现；详情 API 中 `provider_call_ignored` 数量为 1，transcript 中不包含晚到响应文本。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js` 均已在实现后通过；完整最终检查在本轮结束前执行。
- Phase 3 Gate：晚到 provider 响应竞态子集已通过自动化 + Chrome MCP 验收；完整三 AI 串联总 gate 已在后续记录中通过。

## Phase 3 总体验收记录

- 验收时间：2026-06-17T02:25:10+08:00
- 真实 AI 总 gate：本地服务 `http://127.0.0.1:8038`、WS `8039`，创建真实三 AI 会议 `phase3-total-real-mcp-20260617`，参与者 `main`/OpenClaw、`hermes-default`/Hermes、`codex-local`/Codex，`contextMode=incremental`，`maxRounds=1`，`decisionWindowSec=120`。
- 串联流程：真实 AI opening 完成后进入轮末用户决策窗口；写入用户插话和补充上下文；点名 Hermes 并得到 `targeted_response`；点击继续进入 discussion；讨论轮耗尽进入 no-consensus arbitration；提交用户裁决后会议进入 `completed`。
- 事件验收：详情 API 显示 `stage=completed`、事件数 27、`participant_turn=7`、providerKinds 覆盖 `openclaw`/`hermes`/`codex`、`user_intervention=1`、`targeted_question=1`、`targeted_response=1`、`arbitration_decision=1`、失败 turn 为 0。
- Chrome MCP 验收：打开 Meetings dashboard 历史页并查看详情，确认总 gate 会议可见，状态为 completed；详情弹窗中可见用户插话“请重点判断 Phase 3 是否可以进入总验收”、补充上下文“必须保留真实 providerRef、逐轮发言、用户裁决和最终结果”，以及裁决文本“Phase 3 可以进入人工总验收”。
- 自动化回归：`tests/test_meeting_for_ai_phase1.py`、`tests/test_project_execution.py`、`tests/test_feishu_sync.py`、Codex bridge/provider/server/live activity、review parser、websocket route、JS/i18n/font/browser viewer/internal bubble 等回归通过；`tests/test_project_execution.py` 仍有已知 gateway 连接警告但最终 `ok`。
- 依赖缺失说明：`tests/test_workflow_e2e.py` 未运行完成，原因是当前环境缺少 Python `requests`；`tests/e2e_internal_bubble.js` 未运行完成，原因是当前环境缺少 Node `puppeteer-core`。这两项为环境依赖缺失，不是 Phase 3 断言失败。
- Phase 3 Gate：CHK-P3-001 至 CHK-P3-013 的实现与总体验收通过；Phase 3 可进入用户统一手动验收。

## Phase 3 总结倒计时关闭修复验收记录

- 验收时间：2026-06-17T03:25:00+08:00
- 修复范围：区分 no-consensus 裁决等待和最终总结倒计时。已有实质分歧的会议不再显示会自动继续的倒计时，而显示“等待裁决”并关闭 auto-continue；若最新一轮没有实质分歧，`无`、`无新分歧`、`none` 等声明不会再被当作争议，最终轮窗口超时会进入主持总结并关闭会议。
- 竞态修复：`run` 遇到 `summarizing` 只返回正在总结，避免前端轮询或重复点击在主持人总结尚未返回时触发 fallback completion；主持人回包时若会议已终态，则记录 `provider_call_ignored`，不会追加第二份 `meeting_result` 或出现 `completed -> completed` 转换。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 覆盖无实质分歧最终轮 timeout 自动总结、summarizing 期间重入 `run` 不完成会议、最终仅 1 条 `meeting_result` 且无 `from=completed` 的重复 transition。
- Chrome MCP 验收：本地服务 `http://127.0.0.1:8038`、WS `8039` 使用当前真实 AI 会议 `05baddfd-423c-4778-bcdf-217e5060a412` 验证 no-consensus UI。该会议保持 `awaiting_user_decision`、`arbitration.reason=no_consensus`，页面卡片显示“等待裁决”、`data-auto-continue=0`、不含 `mtg-decision-countdown` 自动倒计时 class，且无共识裁决面板可见。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。

## Phase 3 裁决策略与固定结果输出补充验收记录

- 验收时间：2026-06-17T03:35:00+08:00
- 实现范围：新增会议级 `resolutionPolicy`，默认 `user_decision` 保持原有行为；新增 `moderator_decision`，当最终轮存在实质分歧时不进入用户裁决等待，而是等待窗口超时或继续后进入主持人总结并自动关闭会议。
- 结果结构：主持人总结 prompt 要求固定 JSON schema，新增 `outcome` 枚举：`approved`、`rejected`、`no_consensus`、`needs_user_decision`，并新增 `rationale`。结果解析会保留这些字段；fallback 默认为 `approved`，避免空 outcome。
- 前端范围：新建会议弹窗新增“裁决策略”下拉，包含“用户裁决分歧”和“主持裁决并关闭”；active/detail 视图展示裁决策略，历史详情展示 outcome 和 rationale。
- 自动化覆盖：`tests/test_meeting_for_ai_phase1.py` 新增 `moderator_decision` 策略测试，覆盖有实质分歧但不生成 `meeting.arbitration` 用户等待状态、`decision_window_opened.payload.arbitration` 保留分歧证据、主持总结 prompt 包含固定 outcome schema、超时后自动 completed，并持久化 `outcome=rejected`、decision 和 rationale。
- Chrome MCP 验收：重启本地服务 `http://127.0.0.1:8038`、WS `8039` 后强制刷新页面，打开 Meetings dashboard 和新建会议表单，确认存在 `new-mtg-resolution-policy`，选项为 `user_decision` / `moderator_decision`，可见中文文案“裁决策略”“用户裁决分歧”“主持裁决并关闭”，默认值为 `user_decision`。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。

## Phase 3 结构化会议摘要渲染补充验收记录

- 验收时间：2026-06-17T03:45:00+08:00
- 实现范围：会议详情中的总结结果不再只按纯文本块显示，新增“会议结论”结构化面板，集中展示 outcome、summary、decision、rationale、unresolvedQuestions、disagreements 和 actionItems。
- 前端范围：新增 `_mtgRenderResultSummary()`，历史/详情弹窗复用该渲染；outcome 使用状态徽章样式区分 `approved`、`rejected`、`no_consensus`、`needs_user_decision`；未解决问题、分歧和行动项以项目列表显示。
- Chrome MCP 验收：本地服务 `http://127.0.0.1:8038`、WS `8039` 重启后，通过页面渲染函数注入结构化结果样例，断言 `.mtg-result-summary` 存在，`outcome=rejected` 显示为“不通过”并带 rejected class，摘要、决议、理由、未解决问题、分歧和行动项文本均可见。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。

## Phase 3 进行中会议弹窗详情补充验收记录

- 验收时间：2026-06-17T04:15:00+08:00
- 实现范围：进行中会议列表不再使用卡片展开方式展示实时讨论和控制区，改为概要卡片 + 详情弹窗。点击进行中会议卡片或“查看详情”按钮打开详情弹窗。
- 前端范围：active meeting 卡片只显示标题、状态、轮次、当前发言者、裁决策略摘要和“查看详情”；详情弹窗承载实时讨论、用户插话、议题调整、轮末决策窗口、点名、主持接管、暂停/继续/结束/取消等控制。实时事件轮询会在弹窗打开时重渲染详情内容。
- Chrome MCP 验收：本地服务 `http://127.0.0.1:8038`、WS `8039` 重启后打开 Meetings dashboard 的进行中页。断言 active 列表 `cardBodies=0`、`openBodies=0`、`summaries=1`；点击卡片后 `meetingDetailModal` 打开，详情弹窗绑定会议 `ad9d8d37-49d5-4bb4-8cee-d88ac0c6acde`，并可见实时讨论、用户插话、暂停/继续和取消会议控制。
- 回归结果：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`node --check app/game.js`、`node tests/test_i18n_integrity.js` 和 `git diff --check` 均通过。

## Phase 1-3 用户最终验收确认

- 确认项：Meeting for AI Phase 3 / meeting-for-ai-phase-1-3 最终验收。
- 确认时间：2026-06-17T04:34:19+08:00
- 用户确认摘要：用户确认“会议 phase3 我验收完了”，并要求在 `meeting-for-ai` 和 `meeting-for-ai-phase-1-3` 中做对应标记。
- 结论：Phase 3 用户验收通过；`meeting-for-ai-phase-1-3` 子需求可归档为完成。Phase 4-7 仍属于父需求后续范围，不随本次确认自动完成。
