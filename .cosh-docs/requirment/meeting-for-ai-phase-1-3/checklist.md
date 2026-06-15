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
- 验证方法：人工执行一次含实时讨论查看、插话、点名、暂停继续和争议裁决的三 AI 会议。
- 预期结果：实时讨论可见且随事件增量更新；所有控制可用；会议最终生成一致结果，刷新后仍可审计。

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
- Phase 3 Gate：暂停继续取消子集已通过；点名、议题修改、无共识裁决、主持接管和主画布会议投影仍未完成，因此 CHK-P3-011 仍不能标记通过。
