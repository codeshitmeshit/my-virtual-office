# Todolist: Dashboard Realtime Status

## TODO-001 Establish Focused Module Boundaries

- 目标：为 dashboard realtime 功能建立独立前后端模块边界，避免继续扩大 `app/game.js` 和 `app/server.py`。
- 涉及区域：frontend dashboard code, backend event stream code, HTML script loading, server route wiring.
- 输入：`requirement.md`, `review.md`, `checklist.md`, current `app/game.js`, current `app/server.py`.
- 输出：明确的新 JS 文件和新 Python 文件命名与职责边界；现有大文件仅保留薄集成点。
- 依赖：无。
- 完成标准：实施方案可追溯到新增 JS/Python 模块，且不要求在大文件中承载主要新逻辑。
- 关联 checklist：CHK-016, CHK-017, CHK-018。

## TODO-002 Add Backend Dashboard Event Stream Module

- 目标：新增后端 dashboard event stream 专用 Python 模块，负责事件形态、订阅/推送、心跳、连接状态与快照辅助。
- 涉及区域：new backend Python module, server route integration, status and meeting data sources.
- 输入：现有 `/status`, `/agent-chat`, `/api/meetings/active`, meeting request data, meeting event append points.
- 输出：可被 `server.py` 薄路由调用的 dashboard realtime event stream 能力。
- 依赖：TODO-001。
- 完成标准：后端主要事件流逻辑位于新 Python 文件；`server.py` 只做路由注册/调用；支持状态概览、会议摘要、pending request、action-required events、heartbeat 或等价连接保活。
- 关联 checklist：CHK-001, CHK-003, CHK-004, CHK-005, CHK-009, CHK-017。

## TODO-003 Add Frontend Dashboard Realtime Module

- 目标：新增前端 dashboard realtime 专用 JS 文件，负责连接事件流、处理事件、维护连接模式、协调 fallback refresh。
- 涉及区域：new frontend JS module, dashboard/sidebar DOM integration, script inclusion.
- 输入：后端 dashboard event stream, existing sidebar state, existing polling functions, dashboard DOM elements.
- 输出：控制面板可以通过独立 JS 模块接收 realtime updates 并更新状态概览与会议摘要。
- 依赖：TODO-001, TODO-002。
- 完成标准：主要连接、事件处理、sync-state、fallback 逻辑位于新 JS 文件；`game.js` 只保留必要 hook；正常情况下关键状态 1-3 秒内反映。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-007, CHK-016, CHK-018。

## TODO-004 Implement Dashboard Update Mode Indicator

- 目标：在控制面板上明确显示当前更新模式：SSE connected、SSE reconnecting、Polling fallback。
- 涉及区域：dashboard/sidebar UI, i18n copy, frontend realtime module.
- 输入：连接状态、重连状态、fallback 状态。
- 输出：低噪音但清楚的更新模式标识和异常提示。
- 依赖：TODO-003。
- 完成标准：用户能分辨当前是 SSE 实时连接、SSE 重连中，还是轮询降级；中文文案简洁且不夸大实时保证。
- 关联 checklist：CHK-007, CHK-008, CHK-014。

## TODO-005 Implement Action-Required Activity Log Events

- 目标：让活动日志只接收本期定义的 action-required 事件，避免变成完整过程流。
- 涉及区域：backend event taxonomy, frontend activity log rendering, meeting/user-action event sources.
- 输入：pending meeting request、conflict、approval、timeout、failure、arbitration 等事件。
- 输出：活动日志展示需要用户关注或处理的关键事件。
- 依赖：TODO-002, TODO-003。
- 完成标准：正常 chatter、token progress、常规 provider 进度不会刷屏；关键待处理事件含义清楚。
- 关联 checklist：CHK-005, CHK-006, CHK-012。

## TODO-006 Preserve Snapshot Initialization And Fallback

- 目标：保留现有快照接口作为初始化、断线 fallback 和重连校准来源。
- 涉及区域：frontend realtime module, existing polling functions, backend snapshot endpoints.
- 输入：`/status`, `/api/meetings/active`, pending meeting requests, existing local dashboard state.
- 输出：页面初始快照、SSE 增量更新、断线轮询降级、重连校准的完整体验。
- 依赖：TODO-002, TODO-003, TODO-004。
- 完成标准：实时不可用时 dashboard 仍可用并明确提示降级；重连后状态收敛到后端快照，不产生重复或矛盾状态。
- 关联 checklist：CHK-002, CHK-008, CHK-009, CHK-010, CHK-013。

## TODO-007 Keep Meeting Detail And Out-Of-Scope Areas Stable

- 目标：确保 dashboard realtime 不破坏会议详情页、项目摘要、技能库、聊天气泡等本期非目标区域。
- 涉及区域：meeting detail, sidebar meetings, project summary, existing polling consumers.
- 输入：existing meeting controls, existing detail polling/live behavior.
- 输出：本期只改善控制面板摘要和会议摘要，不引入项目摘要实时化要求。
- 依赖：TODO-003, TODO-006。
- 完成标准：会议详情和控制动作保持可用；项目摘要不被纳入新 realtime 验收；无明显 UI 回归。
- 关联 checklist：CHK-011, CHK-013, CHK-015。

## TODO-008 Add Focused Tests And Verification Coverage

- 目标：补充覆盖 dashboard realtime event stream、frontend module behavior、fallback/reconnect、活动日志事件过滤、模块边界的测试或可执行检查。
- 涉及区域：Python tests, JS/static checks, browser/manual verification where needed.
- 输入：implementation from TODO-002 through TODO-007.
- 输出：自动化测试和人工验证记录，覆盖 checklist 核心项。
- 依赖：TODO-002, TODO-003, TODO-004, TODO-005, TODO-006, TODO-007。
- 完成标准：测试能验证关键状态更新、会议摘要、action-required log、SSE/fallback mode indicator、模块边界；人工验证步骤覆盖 UI copy 和 meeting detail regression。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012, CHK-013, CHK-014, CHK-015, CHK-016, CHK-017, CHK-018。

## TODO-009 Update Documentation Or Inline Operational Notes

- 目标：记录 dashboard realtime 的产品边界、更新模式、降级行为和模块职责，避免后续误解为全应用实时化。
- 涉及区域：requirement docs, README or internal docs if appropriate, code comments only where useful.
- 输入：final implementation behavior and checklist outcomes.
- 输出：简洁说明或文档更新。
- 依赖：TODO-002 through TODO-008。
- 完成标准：文档说明本期覆盖 status overview + meeting summary、action-required log、SSE/polling fallback 标识、项目摘要不在范围内。
- 关联 checklist：CHK-014, CHK-016, CHK-017, CHK-018。
