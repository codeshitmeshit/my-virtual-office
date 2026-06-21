# Phase 6 Reasoning Summary Visibility Todo List

执行状态：实现与自动化完成，等待用户浏览器验收。

- TODO-RS-001 至 TODO-RS-004：已完成。
- TODO-RS-005：真实 Codex 协议验证已完成，浏览器人工确认待完成。

## TODO-RS-001 Normalize reasoning notifications

- 目标：将 Codex reasoning 通知从通用工具活动中分离。
- 涉及区域：`app/providers/codex_bridge.py`、bridge 单元测试。
- 输入：`summaryTextDelta`、`summaryPartAdded`、`textDelta`。
- 输出：带 item、section、delta kind 和 sequence 的独立 reasoning 事件。
- 依赖：无。
- 完成标准：三类通知均被识别，普通 command/MCP 行为不变。
- 关联 checklist：CHK-RS-001、CHK-RS-003。

## TODO-RS-002 Preserve safe reasoning history

- 目标：通过现有活动存储安全持久化 reasoning 事件。
- 涉及区域：`app/server.py`、server 测试。
- 输入：TODO-RS-001 标准事件。
- 输出：脱敏、截断、可按 sequence 恢复的历史事件。
- 依赖：TODO-RS-001。
- 完成标准：刷新读取不丢失、不重复；敏感值不进入持久化文件。
- 关联 checklist：CHK-RS-004、CHK-RS-006。

## TODO-RS-003 Render incremental Thinking cards

- 目标：为每个 reasoning item 渲染一张增量更新的 Thinking 卡。
- 涉及区域：`app/chat.js`、`app/style.css`。
- 输入：reasoning activity history 与 live delta。
- 输出：分段、去重、可展开、准确措辞的 Thinking 卡。
- 依赖：TODO-RS-001、TODO-RS-002。
- 完成标准：20 delta/3 section 只产生一张卡；无事件时不产生空卡。
- 关联 checklist：CHK-RS-002、CHK-RS-003、CHK-RS-005、CHK-RS-007。

## TODO-RS-004 Add deterministic regression coverage

- 目标：覆盖 bridge、server 和浏览器聚合行为。
- 涉及区域：`tests/test_codex_bridge.py`、`tests/test_codex_server.py`、Phase 6 E2E 或前端专项测试。
- 输入：多 delta、多 section、多 item、敏感值和刷新 fixture。
- 输出：可重复自动化测试。
- 依赖：TODO-RS-001 至 TODO-RS-003。
- 完成标准：10 项 checklist 中可自动化部分全部有断言，原 Phase 6 测试继续通过。
- 关联 checklist：CHK-RS-001 至 CHK-RS-007、CHK-RS-009、CHK-RS-010。

## TODO-RS-005 Run live acceptance and document results

- 目标：使用真实 Codex 复杂只读任务验证 runtime reasoning 行为。
- 涉及区域：本需求 checklist/status、运行服务。
- 输入：`_VO_INT=1`、`demo=false` 的本地服务。
- 输出：真实事件证据、浏览器验收入口和测试记录。
- 依赖：TODO-RS-001 至 TODO-RS-004。
- 完成标准：若 runtime 发出 reasoning，正确展示；若未发出，记录协议证据且不伪造卡片。
- 关联 checklist：CHK-RS-008、CHK-RS-009、CHK-RS-010。
