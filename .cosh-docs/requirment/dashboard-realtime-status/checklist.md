# Checklist: Dashboard Realtime Status

确认状态：已确认

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-07-04T13:12:52+08:00
- 用户确认摘要：用户回复 "pass"，确认当前 checklist 可作为后续 todolist 和实施验收依据。

## Scope

This checklist validates the first phase of dashboard realtime status:

- Status overview and agent current state.
- Meeting summary, including active meetings and pending meeting requests.
- Action-required activity log entries.
- Visible sync / degraded fallback state.
- Snapshot fallback and correction behavior.

Project summary realtime updates, complete chat streaming, complete provider progress streaming, and full audit-log behavior are out of scope.

## Checklist Items

### CHK-001 Status Overview Near-Realtime Update

- 关联需求点：status overview plus meeting summary; 1-3 second perceived latency.
- 验证方法：Trigger or simulate an agent state change that affects working / idle / meeting / break counts, then observe the control panel.
- 预期结果：The relevant count and agent state update within 1-3 seconds in normal conditions.

### CHK-002 Agent Current State Consistency

- 关联需求点：state trustworthiness; dashboard consistency with backend snapshot.
- 验证方法：Compare the control panel agent state with the backend status snapshot after a state change and after a manual refresh or reconnect.
- 预期结果：The displayed agent state converges to the backend snapshot and does not remain stale after correction.

### CHK-003 Active Meeting Summary Near-Realtime Update

- 关联需求点：meeting summary included in phase scope.
- 验证方法：Create, start, or end an active meeting, then observe the sidebar meeting summary.
- 预期结果：Active meeting entries appear, update, or disappear within 1-3 seconds in normal conditions.

### CHK-004 Pending Meeting Request Near-Realtime Update

- 关联需求点：meeting summary; user-action-needed events.
- 验证方法：Create or simulate a pending meeting request that requires user confirmation.
- 预期结果：The control panel meeting summary reflects the pending request within 1-3 seconds and makes it clear that user action is needed.

### CHK-005 Activity Log Only Shows Action-Required Event Classes

- 关联需求点：activity log as exception / action-required center.
- 验证方法：Generate normal status changes, normal meeting progress, and action-required events such as pending confirmation, conflict, timeout, failure, approval, or arbitration.
- 预期结果：The activity log includes action-required events and does not become a full stream of normal chatter, token progress, or routine provider updates.

### CHK-006 Activity Log Event Clarity

- 关联需求点：faster discovery of events needing user attention.
- 验证方法：Inspect activity log entries for pending meeting request, conflict, timeout, failure, and approval cases.
- 预期结果：Each entry clearly communicates what happened, who or what is affected, and whether the user needs to act.

### CHK-007 Dashboard Realtime Connection Normal State

- 关联需求点：status indicator plus explicit error/reconnect hints.
- 验证方法：Open the dashboard while realtime updates are connected and functioning.
- 预期结果：A low-noise healthy state is visible and identifies that the dashboard is using the SSE realtime connection, without cluttering the panel.

### CHK-008 Dashboard Reconnect / Degraded State

- 关联需求点：visible fallback / degraded refresh hint.
- 验证方法：Interrupt the realtime update path and observe the dashboard.
- 预期结果：The panel clearly distinguishes SSE reconnecting from polling fallback, and does not imply that SSE realtime updates are active when they are not.

### CHK-009 Fallback Snapshot Keeps Dashboard Usable

- 关联需求点：existing workflows continue when realtime updates are unavailable.
- 验证方法：Use the dashboard while realtime updates are unavailable.
- 预期结果：The dashboard continues to show status and meeting summary via fallback refresh, with visible degraded state.

### CHK-010 Reconnect Snapshot Correction

- 关联需求点：accuracy and consistency after reconnect.
- 验证方法：Disconnect realtime updates, change backend state, then reconnect.
- 预期结果：After reconnect, the control panel reconciles with the latest snapshot and removes stale or incorrect state.

### CHK-011 No Project Summary Realtime Scope Creep

- 关联需求点：project summary out of scope for phase one.
- 验证方法：Review the dashboard behavior and visible realtime updates for project progress sections.
- 预期结果：Project summary is not required to update through the new realtime path in this phase; existing behavior remains acceptable.

### CHK-012 Noise Control For High-Frequency Events

- 关联需求点：dashboard remains calm and scannable.
- 验证方法：Generate rapid provider progress or repeated status events.
- 预期结果：The control panel does not spam the activity log or visibly flicker; repeated events are coalesced, ignored, or kept outside the action-required log.

### CHK-013 Existing Polling-Based UI Does Not Regress

- 关联需求点：compatibility with fallback and existing workflows.
- 验证方法：Verify existing dashboard, meeting sidebar, and agent status behavior when realtime updates are healthy and when degraded.
- 预期结果：Existing UI remains functional; fallback refresh does not duplicate entries or create contradictory states.

### CHK-014 Manual Verification Of User-Facing Copy

- 关联需求点：visible sync and fallback state.
- 验证方法：Review Chinese UI copy for SSE connected, SSE reconnecting, disconnected, and polling fallback states.
- 预期结果：Copy is concise, understandable, and clearly tells the user whether the dashboard is currently using SSE or polling fallback without implying stronger realtime guarantees than the product promises.

### CHK-015 Regression: Meeting Detail Remains Usable

- 关联需求点：do not replace detail pages or workflows.
- 验证方法：Open a meeting detail view and use existing meeting controls while dashboard realtime updates are enabled.
- 预期结果：Meeting detail view and controls continue to work; dashboard updates do not interfere with meeting-specific live behavior.

### CHK-016 Frontend Realtime Logic Lives In A Dedicated JS Module

- 关联需求点：new implementation should avoid further coupling with large existing files.
- 验证方法：Review the changed frontend files after implementation.
- 预期结果：The main dashboard realtime connection, event handling, sync-state handling, and fallback coordination live in a new focused JS file. Existing large files such as `app/game.js` contain only minimal integration hooks where needed.

### CHK-017 Backend Event Stream Logic Lives In A Dedicated Python Module

- 关联需求点：new implementation should avoid further coupling with large existing files.
- 验证方法：Review the changed backend files after implementation.
- 预期结果：The main dashboard event stream, event shaping, subscription management, and related helpers live in a new focused Python file. Existing large files such as `app/server.py` contain only minimal route or wiring code where needed.

### CHK-018 Modular Boundary Does Not Create Hidden Product Gaps

- 关联需求点：module split must preserve product behavior.
- 验证方法：Run the dashboard realtime scenarios while inspecting that the new modules still cover status overview, meeting summary, action-required log events, sync state, and fallback behavior.
- 预期结果：The modular split improves code organization without reducing the agreed product scope or causing duplicate state ownership.

## 测试执行记录

- 执行时间：2026-07-04T13:20:56+08:00
- 执行人：Codex
- 结果摘要：自动化检查通过；UI 视觉验收仍需用户人工确认。

### 已执行命令

```bash
python3 -m py_compile app/dashboard_realtime.py app/server.py
.venv/bin/python tests/test_dashboard_realtime.py
node --check app/dashboard-realtime.js
node --check app/game.js
node tests/check_dashboard_realtime_static.mjs
python3 -m json.tool app/locales/zh.json
python3 -m json.tool app/locales/en.json
.venv/bin/python tests/test_meeting_for_ai_phase1.py
node tests/check_sidebar_meeting_direct_detail.mjs
```

### 覆盖说明

- CHK-001, CHK-002, CHK-003, CHK-004：通过 `tests/test_dashboard_realtime.py` 覆盖 dashboard snapshot、状态摘要、会议摘要和事件差分。
- CHK-005, CHK-006, CHK-012：通过 `tests/test_dashboard_realtime.py` 覆盖 pending request、meeting conflict、provider timeout、user decision 等 action-required 事件提取，不包含 approved request。
- CHK-007, CHK-008, CHK-014：通过 `tests/check_dashboard_realtime_static.mjs` 和 locale JSON 校验覆盖 SSE / reconnecting / polling fallback 文案和前端标识入口；仍需浏览器人工确认显示效果。
- CHK-009, CHK-010, CHK-013：通过静态检查和现有会议回归测试覆盖 fallback 接口与现有 meeting sidebar 不回归；断线重连视觉流程仍需人工验收。
- CHK-011, CHK-015：通过 `tests/test_meeting_for_ai_phase1.py` 和 `tests/check_sidebar_meeting_direct_detail.mjs` 覆盖会议相关回归；项目摘要未纳入新增 realtime 路径。
- CHK-016, CHK-017, CHK-018：通过 `tests/check_dashboard_realtime_static.mjs` 覆盖新 JS 模块、新 Python 模块和大文件薄接入边界。

### 待人工验收

- 浏览器中确认控制面板能显示 `SSE 实时连接`、`SSE 重连中`、`轮询降级`。
- 浏览器中确认 dashboard status overview 和 meeting summary 在正常情况下 1-3 秒内更新。
- 浏览器中确认活动日志只展示本期 action-required 事件，不被常规状态/聊天/进度刷屏。

## 追加验收记录

- 执行时间：2026-07-04T13:23:55+08:00
- 执行人：Codex
- 结果摘要：临时本地服务和浏览器可视化验收通过 SSE connected 基础场景；SSE 断线到轮询降级仍建议由用户在实际运行环境中确认。

### 已执行验证

```bash
VO_PORT=8097 VO_WS_PORT=8098 VO_STATUS_DIR=<temp> VO_GATEWAY_ENABLED=false VO_HERMES_ENABLED=false VO_CODEX_ENABLED=false VO_CLAUDE_CODE_ENABLED=false .venv/bin/python app/server.py
curl -sS http://127.0.0.1:8097/status
curl -sS -N --max-time 4 http://127.0.0.1:8097/api/dashboard/events
curl -sS -I http://127.0.0.1:8097/dashboard-realtime.js
```

### 真实服务验证结果

- `/api/dashboard/events` 返回 `event: dashboard.snapshot`，payload 包含 `status.counts`、`meetings.active`、`meetings.pendingRequests`、`actions` 和 signatures。
- `/api/dashboard/events` 返回 `event: dashboard.heartbeat`。
- `/dashboard-realtime.js` 通过 HTTP 200 正常加载，Content-Type 为 `text/javascript`。
- In-app Browser 打开 `http://127.0.0.1:8097/` 后，控制面板出现可见标识：`控制面板：SSE 实时连接`，元素 class 为 `dashboard-realtime-status sse`。

### 覆盖更新

- CHK-007：已通过浏览器确认 SSE connected 标识可见。
- CHK-014：已通过浏览器确认中文 SSE connected 文案可见。
- CHK-016, CHK-017, CHK-018：已通过真实页面加载和 SSE 路由首包验证补强。

## 追加验收记录

- 执行时间：2026-07-04T13:28:56+08:00
- 执行人：Codex
- 结果摘要：临时服务断开后，浏览器中的控制面板已自动切换到轮询降级标识。

### 断线降级验证结果

- 临时本地服务停止后，`http://127.0.0.1:8097/status` 返回 HTTP `000`，确认服务不可达。
- In-app Browser 中控制面板的实时状态元素仍然存在。
- 状态元素文本为 `控制面板：轮询降级`。
- 状态元素 class 为 `dashboard-realtime-status polling`。
- 状态元素 title 为 `SSE 当前不可用，控制面板正在使用轮询降级刷新。`

### 覆盖更新

- CHK-008：已通过浏览器确认 SSE 不可用后会进入轮询降级状态，而不是继续展示 SSE connected。
- CHK-009：已通过浏览器确认降级状态下控制面板保留可见状态入口。
- CHK-014：已通过浏览器确认中文轮询降级文案和说明 title 可见且语义明确。

### 仍建议用户确认

- 在实际 agent/meeting 工作流中确认 1-3 秒更新感知和 action-required 活动日志噪音水平。

## 追加自动化覆盖记录

- 执行时间：2026-07-04T13:30:38+08:00
- 执行人：Codex
- 结果摘要：补充 dashboard realtime 差分事件和 action-required 噪音过滤的自动化测试后，关键检查继续通过。

### 新增覆盖

- `tests/test_dashboard_realtime.py::test_dashboard_diff_emits_meetings_and_actions_when_needed` 覆盖会议摘要变化和 action-required 变化会分别产出 `dashboard.meetings` 与 `dashboard.actions`。
- `tests/test_dashboard_realtime.py::test_dashboard_actions_exclude_routine_and_resolved_items` 覆盖 routine working 状态、resolved conflict、未超时 pending call、approved/rejected meeting request 不进入 action-required 活动项。

### 已复跑命令

```bash
python3 -m py_compile app/dashboard_realtime.py app/server.py
.venv/bin/python tests/test_dashboard_realtime.py
node --check app/dashboard-realtime.js
node --check app/game.js
node tests/check_dashboard_realtime_static.mjs
python3 -m json.tool app/locales/zh.json
python3 -m json.tool app/locales/en.json
python3 -m json.tool .cosh-docs/requirment/dashboard-realtime-status/status.json
```

### 覆盖更新

- CHK-003, CHK-004：补强会议摘要与 pending request 差分事件自动化覆盖。
- CHK-005, CHK-006, CHK-012：补强 action-required 日志过滤自动化覆盖，明确 routine/resolved/approved/rejected 项不会刷屏。
- CHK-008, CHK-009, CHK-014：保留此前浏览器真实断线降级验证作为 UI 证据。
