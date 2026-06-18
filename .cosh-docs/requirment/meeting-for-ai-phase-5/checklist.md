# Meeting for AI Phase 5 Checklist

确认状态：已确认

## 人工确认记录

- 2026-06-18T00:24:39+08:00：用户回复 `pass`，确认 Phase 5 checklist 可以进入 todolist 生成。确认范围包含忙碌冲突检测、advisory turn、轻量预约、任务暂停恢复、并发占用、UI 可观测性和 Phase 1-4 回归。

## 冲突检测与处理

### CHK-P5-001 忙碌 Agent 冲突检测

- 关联需求：检测活动任务、普通持续工作、provider 调用、外部等待和会议占用。
- 验证方法：分别让目标 Agent 处于空闲、项目任务执行中、provider 调用中、另一场会议中，再尝试创建或确认包含该 Agent 的会议。
- 预期结果：空闲 Agent 可继续；忙碌或已占用 Agent 进入明确冲突状态；系统展示冲突原因，不静默打断任务或重复占用。

### CHK-P5-002 等待、更换、强制加入三种处理路径

- 关联需求：用户可选择等待、更换参会者或强制加入。
- 验证方法：对同一忙碌 Agent 分别执行等待、更换参会者和强制加入。
- 预期结果：等待保留会议准备或冲突状态；更换后使用新参会者继续；强制加入必须记录用户选择、影响说明和原任务状态。

### CHK-P5-003 强制加入二次确认

- 关联需求：高影响操作需要用户最终确认。
- 验证方法：在中高风险冲突下点击强制加入，并尝试绕过二次确认。
- 预期结果：界面展示打断风险和恢复说明；未二次确认时不执行强制加入；确认后才进入会议占用和暂停流程。

### CHK-P5-004 冲突处理选择记录

- 关联需求：用户选择和关键状态变化可追踪。
- 验证方法：分别完成等待、更换、强制加入和取消冲突处理后查看会议事件或状态记录。
- 预期结果：记录操作者、时间、冲突 Agent、冲突原因、用户选择和转换结果。

## Advisory Turn

### CHK-P5-005 中高风险冲突默认触发 Advisory

- 关联需求：中高风险冲突默认触发 advisory turn。
- 验证方法：让 Agent 处于项目任务执行中、provider 调用中或状态不明，再尝试邀请其参会。
- 预期结果：系统自动发起受控 advisory；返回内容包含忙碌原因、预计可用时间或不确定性、打断风险、恢复说明和推荐动作。

### CHK-P5-006 低风险冲突不强制触发 Advisory

- 关联需求：低风险冲突可不默认触发，避免无谓延迟。
- 验证方法：构造低风险忙碌状态或可中断状态并邀请 Agent。
- 预期结果：系统可直接展示冲突和处理按钮；用户仍可按需查看影响；不会因为 advisory 缺失阻断普通处理。

### CHK-P5-007 强制加入前补齐 Advisory

- 关联需求：用户准备强制加入且尚无建议时，应先尝试获取建议。
- 验证方法：在无 advisory 结果的冲突状态下选择强制加入。
- 预期结果：系统先尝试获取 advisory；成功时展示建议后再允许二次确认；失败时显示无法获取建议并仍要求二次确认。

### CHK-P5-008 Advisory 不直接改状态

- 关联需求：advisory 只推荐，不自动执行。
- 验证方法：让 advisory 推荐等待、更换或强制加入，并检查会议、任务和占用状态。
- 预期结果：advisory 返回后不会自动暂停任务、释放占用、替换参会者或启动会议；必须等待用户选择或明确后端策略。

### CHK-P5-009 Advisory 失败降级

- 关联需求：advisory 失败时允许继续但不能默认同意。
- 验证方法：模拟 advisory 超时、失败或输出无效，再尝试继续处理冲突。
- 预期结果：界面显示无法获取建议；用户仍可等待、更换或二次确认强制加入；系统不把失败视为同意。

## 轻量预约

### CHK-P5-010 预约作为冲突处理选项

- 关联需求：轻量预约用于避免打断忙碌 Agent。
- 验证方法：在忙碌冲突面板选择稍后提醒或等空闲后再尝试。
- 预期结果：会议进入预约或等待提醒状态；不会启动会议；不会暂停当前任务；用户可看到预约安排。

### CHK-P5-011 预约不强锁 Agent

- 关联需求：预约是部分占用或可见安排，不阻止当前任务。
- 验证方法：创建预约后继续观察该 Agent 的当前任务和普通工作入口。
- 预期结果：当前任务可继续；预约以未来安排或提醒形式展示；系统不因预约提前阻止 Agent 工作。

### CHK-P5-012 预约到时重新冲突处理

- 关联需求：到预约时间或触发条件时仍忙碌则重新进入冲突处理。
- 验证方法：创建预约，并在触发时保持 Agent 忙碌。
- 预期结果：系统重新展示冲突处理选项；不自动强制加入、不自动取消、不跳过冲突检测。

### CHK-P5-013 预约文案不承诺必定开会

- 关联需求：预约不是完整日程或强排程。
- 验证方法：检查冲突面板、预约状态、提醒消息和会议详情文案。
- 预期结果：文案表达为稍后提醒、到时尝试或等空闲后再处理；不暗示到时一定能开会或已强占 Agent。

## 任务暂停与恢复

### CHK-P5-014 原任务状态快照

- 关联需求：记录参会前任务和状态。
- 验证方法：让正在执行项目任务的 Agent 被强制加入会议，查看会议和任务记录。
- 预期结果：系统保存原任务 ID、任务状态、当前进度摘要、暂停原因、恢复标识和用户选择。

### CHK-P5-015 真实暂停与逻辑暂停区分

- 关联需求：provider 支持真实暂停时使用真实暂停，否则使用逻辑暂停并明确展示。
- 验证方法：分别用支持暂停和不支持暂停的 Agent 参会。
- 预期结果：支持暂停时展示真实暂停结果；不支持时展示逻辑暂停限制；界面不把逻辑暂停描述为真实进程暂停。

### CHK-P5-016 会议结束后幂等恢复

- 关联需求：正常结束、取消或失败后恢复原任务，且恢复幂等。
- 验证方法：在会议正常结束、取消和失败三种场景后重复触发恢复。
- 预期结果：可恢复任务只恢复一次；重复恢复请求不产生重复任务或重复派发；恢复状态可查询。

### CHK-P5-017 恢复失败人工补救

- 关联需求：恢复失败时有明确告警和人工处理信息。
- 验证方法：模拟原任务不可恢复、Agent 离线或恢复调用失败。
- 预期结果：系统释放可释放会议占用；任务进入可见的恢复失败或需人工处理状态；用户看到失败原因和下一步处理入口。

## 并发与占用

### CHK-P5-018 单 Agent 单会议约束

- 关联需求：同一 AI 同一时间只能参加一场会议。
- 验证方法：并行确认两场都包含同一 Agent 的会议。
- 预期结果：只有一场能获得该 Agent 的会议占用；另一场进入冲突状态；不会出现同一 Agent 同时在两场 active meeting 中。

### CHK-P5-019 多场无冲突会议并行

- 关联需求：会议可并行，不含冲突 AI 的其他会议正常运行。
- 验证方法：创建两场参会 Agent 完全不重叠的会议并同时运行。
- 预期结果：两场会议均可进入 active 状态并独立推进；状态、发言和占用互不污染。

### CHK-P5-020 并发确认原子性

- 关联需求：占用校验必须是原子的。
- 验证方法：对包含同一 Agent 的两个会议近同时提交确认或启动请求。
- 预期结果：服务端不会产生双重占用；失败请求返回可理解的冲突结果；重复请求保持幂等。

## UI、可观测性与回归

### CHK-P5-021 会议实时状态展示

- 关联需求：会议中心、会议详情和办公室场景展示冲突、等待、预约、暂停和恢复状态。
- 验证方法：依次制造冲突、等待、预约、强制加入、暂停、恢复和恢复失败状态，观察 UI。
- 预期结果：会议中心、会议详情和办公室 Agent 状态一致；用户能看懂当前阶段和可选操作。

### CHK-P5-022 普通聊天回归

- 关联需求：会议不替代普通一对一即时消息。
- 验证方法：在存在会议冲突、预约和 active meeting 时分别发送普通 Agent 消息。
- 预期结果：普通聊天不被错误阻断；如目标 Agent 因会议占用无法响应，系统给出明确状态而非通用失败。

### CHK-P5-023 项目工作流回归

- 关联需求：项目任务创建和项目执行不受会议占用逻辑误伤。
- 验证方法：会议前后创建项目任务、启动项目执行，并观察被会议占用或预约 Agent 的处理。
- 预期结果：不相关项目工作流正常；被会议占用的 Agent 有明确冲突或等待状态；会议结束后可恢复正常。

### CHK-P5-024 Phase 1-4 回归

- 关联需求：已完成会议基础、用户控制、AI 申请和上下文快照不回归。
- 验证方法：回归用户发起会议、用户干预/裁决、AI 发起申请、上下文候选确认和正式会议启动。
- 预期结果：Phase 1-4 已验收能力仍可用；新增冲突处理不会破坏已确认上下文、用户控制或 AI request 流程。

## 测试记录

- 2026-06-18T01:25:17+08:00：Phase 5 后端实现完成。新增 conflict-aware executable meeting 创建、忙碌 Agent 检测、advisory 推荐、等待/预约/更换/强制加入冲突处理、强制加入二次确认、原任务快照、逻辑暂停标记、terminal 幂等恢复、单 Agent 单会议占用保护和 `/api/meetings/executable/<id>/conflict` API。
- 2026-06-18T01:25:17+08:00：Phase 5 前端支持完成。New Meeting 使用 conflict-aware 创建；冲突会议打开详情页；详情页展示参会冲突、risk、advisory、availability、pause capability、reservation 提醒，并提供等待、稍后再试、更换、强制加入和重新检查冲突操作。
- 2026-06-18T01:25:17+08:00：自动化验证通过：`node --check app/game.js`、`python -m json.tool app/locales/en.json`、`python -m json.tool app/locales/zh.json`、`.venv/bin/python -m py_compile app/server.py`、`.venv/bin/python tests/test_meeting_for_ai_phase5.py`、`.venv/bin/python tests/test_meeting_for_ai_phase1.py`、`.venv/bin/python tests/test_meeting_for_ai_phase4.py`、`.venv/bin/python tests/test_project_execution.py`。
- 2026-06-18T01:25:17+08:00：`tests/test_meeting_for_ai_phase5.py` 覆盖确定性后端路径：默认忙碌拒绝、显式 conflict-aware 创建、advisory 只读、conflict meeting 禁止直接 run、轻量预约不占用 Agent、预约 refresh 重新检查冲突、强制加入二次确认、原任务逻辑暂停快照、取消后幂等恢复、替换参会者、单 Agent 单会议保护。
- 2026-06-18T01:25:17+08:00：Phase 1/4 和项目执行回归通过。测试过程中出现既有 gateway 连接警告：`Gateway WS agent call failed` / `Gateway session abort failed`，未导致测试失败。
- 2026-06-18T03:19:38+08:00：使用 `chrome-devtools` MCP 在 `http://127.0.0.1:8038` 完成 Phase 5 p2p 浏览器验收。测试 fixture：`Phase 5 MCP Conflict Acceptance`，忙碌 Agent 为 `busy-agent`，来源任务为 `Phase 5 MCP busy task`。
- 2026-06-18T03:19:38+08:00：MCP UI 验证通过：会议中心展示 `conflict` 阶段；会议详情展示参会冲突、risk=`medium`、busy reason、预计可用、暂停能力、advisory=`WAIT`、中断风险、恢复说明，以及等待/稍后再试/更换/强制加入/重新检查冲突按钮。
- 2026-06-18T03:19:38+08:00：MCP p2p 过程中发现并修复前端投影缺口：`_exec_meeting_project_active` 未向会议中心详情投影 `conflicts`、`reservation`、`originalWork`、`participantState`，导致详情面板只显示“重新检查冲突”而缺少冲突卡片。
- 2026-06-18T03:19:38+08:00：根据验收反馈调整“稍后再试”：提醒时间不再由用户输入；UI 点击后直接提交轻量预约，由 busy Agent/advisory 的可用性状态决定后续重试/提醒。后端保留 `targetAt` 兼容 API 调用。
- 2026-06-18T03:19:38+08:00：MCP 操作验证通过：点击“稍后再试”后会议冲突变为 `reserved`，`reservation.busy-agent.status=scheduled` 且 `targetAt=""`；点击“强制加入”触发二次确认 dialog，确认后写入 `force_join` 事件，并生成 `originalWork.busy-agent.pauseState=logical_paused` 快照；取消会议后 `originalWork.busy-agent.resumeStatus=resumed`。
- 2026-06-18T03:19:38+08:00：MCP 测试还验证了单 Agent 单活跃会议保护：额外创建同参会者会议时被标记为 `meeting_occupied` 高风险冲突，advisory 推荐 `replace`。
- 2026-06-18T03:19:38+08:00：补充验证通过：`node --check app/game.js`、`.venv/bin/python -m json.tool app/locales/en.json`、`.venv/bin/python -m json.tool app/locales/zh.json`、`.venv/bin/python -m py_compile app/server.py`、`.venv/bin/python tests/test_meeting_for_ai_phase5.py`。
- 2026-06-18T03:57:48+08:00：真实 AI 冲突验收通过。先创建并运行真实 `hermes-default` + `codex-local` 会议占用 Hermes，再创建包含同一 Hermes 的第二场会议；第二场正确进入 `conflict`，并触发 busy-agent advisory turn 调用 Hermes。Hermes 返回中文 busy reason、预计可用时间、建议 `reserve`、打断风险、恢复说明，`advisory.source=agent_advisory_turn`。
- 2026-06-18T03:57:48+08:00：使用 `chrome-devtools` MCP 验证真实 advisory UI：会议详情显示“高风险”“预计可用: 当前会议结束后（大约 2 轮讨论后）”“暂停能力: 不可暂停”“建议: 稍后再试”“来源: 忙碌 Agent 建议”，并保留等待/稍后再试/更换/强制加入/重新检查冲突操作。
- 2026-06-18T03:57:48+08:00：验收反馈修复完成：冲突 UI 的枚举和兜底文案汉化；取消会议在历史列表不再显示为“已完成”，改为“已取消”；“推迟开会”仍为轻量稍后再试而非完整排期的缺口已记录到 `docs/todo-task.md`。
- 2026-06-18T03:57:48+08:00：最终补充验证通过：`node --check app/game.js`、`.venv/bin/python -m json.tool app/locales/zh.json`、`.venv/bin/python -m json.tool app/locales/en.json`、`.venv/bin/python -m py_compile app/server.py`、`VO_MEETING_DISABLE_LIVE_ADVISORY=1 .venv/bin/python tests/test_meeting_for_ai_phase5.py`。用户确认验收 Phase 5，子需求归档为 done。
