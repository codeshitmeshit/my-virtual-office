# Project Reset Actions Todolist

状态：已完成

完成时间：2026-07-08T11:56:00+08:00

验收摘要：用户已验收通过；项目级重置入口、双模式选择、高风险确认、任务回 backlog、顺序保持、历史/配置/定时任务保留均已交付。

## TODO-001 Server Reset Contract

- 目标：新增服务端项目 reset 能力，作为重置行为的唯一权威入口。
- 涉及区域：`app/server.py` Project API handlers、Project Execution reset helpers。
- 输入：project id、reset mode (`task_state` / `project_flow`)、confirmed flag。
- 输出：reset 后的 project、resetTaskCount、是否需要确认的错误响应。
- 依赖：已确认的 reset 产品语义。
- 完成标准：
  - 支持两种 reset mode。
  - 对危险状态不带 confirmed 时返回 `confirmationRequired` 与 409。
  - reset 成功后返回更新后的 project。
- 关联 checklist：CHK-003, CHK-004, CHK-005, CHK-006, CHK-008, CHK-009。

## TODO-002 Reset State Semantics

- 目标：实现任务状态与项目执行流状态的清理规则。
- 涉及区域：`app/server.py` task/project execution fields。
- 输入：包含 backlog、executing、blocked、review、done 等状态的项目。
- 输出：任务回 backlog，当前执行上下文清理，历史保留。
- 依赖：TODO-001。
- 完成标准：
  - 清理 activeAttemptId、blockedReason、lastError、reviewResult、meetingBlocker、当前 meeting action fields、completedAt、executionState。
  - 保留 comments、attempts、stateHistory、meetingBlockerHistory、历史记录和 artifacts。
  - 清理 project active fields，使项目可重新启动。
- 关联 checklist：CHK-005, CHK-008。

## TODO-003 Task Order Preservation

- 目标：定义并实现 reset 后任务顺序稳定规则。
- 涉及区域：`app/server.py` reset sorting/order assignment。
- 输入：跨多列、多状态、含新增任务的项目任务列表。
- 输出：所有任务回 backlog 后保持可预期顺序。
- 依赖：TODO-001, TODO-002。
- 完成标准：
  - 不依赖 dict/file iteration 的偶然顺序。
  - reset 后每个任务有连续稳定 `order`。
  - 两种 reset mode 都覆盖顺序保持。
- 关联 checklist：CHK-007。

## TODO-004 Persistence Compatibility

- 目标：确保 reset 后项目可通过现有 markdown/json 存储稳定保存和读取。
- 涉及区域：`app/project_store.py`、`app/server.py` save/load paths。
- 输入：已有项目、新建项目、包含历史字段的项目。
- 输出：reset 后重读数据一致。
- 依赖：TODO-001, TODO-002, TODO-003。
- 完成标准：
  - 旧项目无需新增必填字段也可 reset。
  - reset 结果持久化后再次读取仍正确。
  - 不破坏现有项目归档和 markdown project store。
- 关联 checklist：CHK-010。

## TODO-005 Frontend API Client

- 目标：在前端项目 API client 中加入 reset 调用。
- 涉及区域：`app/projects.js` api object。
- 输入：project id、mode、confirmed。
- 输出：reset API response。
- 依赖：TODO-001。
- 完成标准：
  - 前端可以调用服务端 reset。
  - 正确处理成功、confirmationRequired、错误 toast。
- 关联 checklist：CHK-002, CHK-003, CHK-009。

## TODO-006 Toolbar Button and Choice Dialog

- 目标：在项目 toolbar 新增 "重置" 按钮，并实现双选项弹窗。
- 涉及区域：`app/projects.js` board toolbar/modal logic、`app/projects.css`。
- 输入：用户点击 "重置"。
- 输出：展示 "重置任务状态" 与 "彻底重置项目" 两个操作选择。
- 依赖：TODO-005。
- 完成标准：
  - 按钮位置符合截图标注区域。
  - 弹窗说明两种 reset 的差异。
  - 取消不改变数据。
  - UI 不挤压现有按钮。
- 关联 checklist：CHK-001, CHK-002。

## TODO-007 Risk Confirmation UI

- 目标：实现危险状态确认交互。
- 涉及区域：`app/projects.js` modal/confirm flow。
- 输入：服务端返回 `confirmationRequired` 或前端检测到风险状态。
- 输出：用户确认后再次发起 reset；取消则保持原状态。
- 依赖：TODO-005, TODO-006。
- 完成标准：
  - 执行中、阻塞、review、done 等非初始状态会出现高风险确认。
  - 初始 backlog 状态不出现高风险确认。
  - 后端确认要求能被前端正确处理。
- 关联 checklist：CHK-003, CHK-004, CHK-009。

## TODO-008 Locale and Copy

- 目标：补齐中英文文案，并避免误导用户以为历史/配置会被删除。
- 涉及区域：`app/locales/zh.json`、`app/locales/en.json`。
- 输入：reset button、dialog title、option descriptions、confirmation copy、toast copy。
- 输出：中英文 UI 文案。
- 依赖：TODO-006, TODO-007。
- 完成标准：
  - i18n key 完整。
  - 文案明确说明保留历史、任务、项目配置和定时任务。
- 关联 checklist：CHK-001, CHK-002, CHK-013。

## TODO-009 Unit Tests

- 目标：为 reset 服务端行为补充自动化测试。
- 涉及区域：`tests/test_project_execution.py` 或新增 focused test file。
- 输入：不同任务状态、项目执行流状态、scheduled cron fixture、历史字段 fixture。
- 输出：覆盖 reset contract 的单测。
- 依赖：TODO-001, TODO-002, TODO-003, TODO-004。
- 完成标准：
  - 测试重置任务状态。
  - 测试彻底重置项目保留新增任务。
  - 测试风险确认。
  - 测试顺序保持。
  - 测试历史保留。
  - 测试 scheduled cron 不变。
- 关联 checklist：CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012。

## TODO-010 Frontend Static Validation

- 目标：确保 JS 和 i18n 静态质量。
- 涉及区域：`app/projects.js`、locale files、existing JS/i18n tests。
- 输入：改动后的前端代码。
- 输出：静态检查结果。
- 依赖：TODO-005, TODO-006, TODO-007, TODO-008。
- 完成标准：
  - `node --check app/projects.js` 通过。
  - `node tests/test_i18n_integrity.js` 通过。
- 关联 checklist：CHK-013。

## TODO-011 E2E Verification

- 目标：通过真实本地服务和浏览器验证 reset 用户流。
- 涉及区域：local server、browser automation/E2E script。
- 输入：测试项目，包含 backlog、blocked、review、done、active project flow、scheduled cron。
- 输出：E2E 断言和截图/DOM 验证。
- 依赖：TODO-001 到 TODO-010。
- 完成标准：
  - 本地服务启动成功。
  - 页面可见 "重置" 按钮。
  - 选择弹窗出现。
  - 风险确认出现并可取消。
  - 确认后任务回 backlog 且顺序正确。
  - 项目可重新启动。
  - scheduled cron 仍存在。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-006, CHK-007, CHK-008, CHK-011, CHK-014。

## TODO-012 Manual Acceptance Preparation

- 目标：为用户本地验收准备清晰说明和状态。
- 涉及区域：交付说明、local server。
- 输入：测试通过结果。
- 输出：可供用户验收的本地地址、测试摘要、剩余风险。
- 依赖：TODO-009, TODO-010, TODO-011。
- 完成标准：
  - 汇总自动化测试和 E2E 结果。
  - 启动或保持本地服务供用户验收。
  - 等待用户确认 tested 和 done，不擅自归档。
- 关联 checklist：CHK-014, CHK-015。

## 执行完成记录

- 完成时间：2026-07-07T14:51:23+08:00
- TODO-001 至 TODO-012 均已完成实现或交付准备。
- 自动化测试和浏览器 E2E 结果已记录到 `checklist.md`。
- 用户已在 2026-07-08 确认人工验收通过。
