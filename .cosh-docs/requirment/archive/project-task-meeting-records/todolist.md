# Project Task Meeting Records Todolist

## TODO-001 Audit existing task meeting data flow

状态：已完成

- 目标：确认任务触发会议从 request、meeting result、task update 到 UI 展示的完整路径。
- 涉及区域：`app/server.py` meeting request/result handling、task persistence、`app/projects.js` task detail rendering、相关测试。
- 输入：`requirement.md`、`review.md`、`checklist.md`、现有 `meetingDecisionHistory`、`meetingDiscussionPoints`、`meetingActionItems` 实现。
- 输出：实现前的改动点清单和现有字段兼容判断。
- 依赖：无。
- 完成标准：明确是否复用 `meetingDiscussionPoints` 或引入独立 meeting records 字段，并列出需要覆盖的 outcome。
- 关联 checklist：CHK-001、CHK-008、CHK-013。

## TODO-002 Formalize task meeting record model

状态：已完成

- 目标：建立稳定的任务会议记录契约，能表达 task-triggered meeting 的 outcome、conclusion、risks、action item summary 和 timestamps。
- 涉及区域：task data model、Markdown project store serialization/deserialization、task create/update field allowlist。
- 输入：现有 task meeting fields 和 checklist 中的记录要求。
- 输出：可持久化、可重复读取、向后兼容的任务会议记录数据。
- 依赖：TODO-001。
- 完成标准：任务记录至少包含 meetingId、requestId、outcome/status、decision/summary、risks、action item summary/count、created/applied time；旧任务不报错。
- 关联 checklist：CHK-001、CHK-003、CHK-004、CHK-006、CHK-007、CHK-013。

## TODO-003 Apply meeting results to task records for all relevant outcomes

状态：已完成

- 目标：在 task-triggered meeting 完成或进入用户决策态时，把会议结论写入任务会议记录。
- 涉及区域：`_project_execution_apply_meeting_result`、`_project_execution_apply_meeting_output_to_task`、meeting transition/arbitration result paths。
- 输入：approved、no_consensus、rejected、needs_user_decision meeting result payload。
- 输出：每类结果都能生成或更新任务会议记录，并保持任务状态流不变。
- 依赖：TODO-002。
- 完成标准：approved、no_consensus、rejected、needs_user_decision 都有任务内会议记录；非 task meeting 不写入任务记录。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-006、CHK-007、CHK-008。

## TODO-004 Guarantee idempotency and chronological multi-meeting history

状态：已完成

- 目标：确保同一会议重复应用不重复记录，同一任务多次会议按时间完整保留。
- 涉及区域：meeting record key generation、dedupe logic、task record ordering。
- 输入：重复 meeting result application、多 meeting fixture。
- 输出：稳定去重和可追溯排序行为。
- 依赖：TODO-002、TODO-003。
- 完成标准：同一 meetingId/requestId 重放不增加重复记录；多个会议记录按时间顺序展示和保存。
- 关联 checklist：CHK-005、CHK-009、CHK-013。

## TODO-005 Update task detail meeting record UI

状态：已完成

- 目标：把任务详情中的会议相关区块改造成清晰的“会议记录”模块。
- 涉及区域：`app/projects.js`、`app/projects.css`、locales。
- 输入：任务会议记录、会议行动项、风险和结论数据。
- 输出：任务详情中可扫读的会议记录模块，显示结论、状态、风险、行动项摘要和会议来源信息。
- 依赖：TODO-002、TODO-003。
- 完成标准：用户不用进入会议详情即可看到会议结论；多条记录不重叠、不撑破布局；行动项仍在独立区域或有明确分离。
- 关联 checklist：CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-010、CHK-014。

## TODO-006 Complete localization and terminology cleanup

状态：已完成

- 目标：补齐会议记录模块的中文/英文文案，并移除任务详情中现有硬编码或不准确的标题。
- 涉及区域：`app/locales/zh.json`、`app/locales/en.json`、`app/projects.js`。
- 输入：会议记录模块 UI 文案和状态标签。
- 输出：中文/英文一致的标题、状态、字段标签和空状态文本。
- 依赖：TODO-005。
- 完成标准：中文界面无英文占位，英文界面无中文硬编码；“会议记录”“会议结论”“风险”“需要用户决策”等状态表达准确。
- 关联 checklist：CHK-012、CHK-014。

## TODO-007 Add backend regression tests

状态：已完成

- 目标：覆盖任务会议记录的数据契约、结果应用和边界条件。
- 涉及区域：`tests/test_project_execution.py`、`tests/test_meeting_request_blocks_task.py` 或新增 focused tests。
- 输入：task-triggered meetings with approved/no_consensus/rejected/needs_user_decision outcomes。
- 输出：可重复运行的后端测试。
- 依赖：TODO-002、TODO-003、TODO-004。
- 完成标准：测试覆盖 outcome 记录、风险记录、行动项摘要、幂等、多会议、非任务会议隔离、旧字段兼容。
- 关联 checklist：CHK-001、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010、CHK-011、CHK-013、CHK-015。

## TODO-008 Add UI/DOM verification

状态：已完成

- 目标：验证任务详情会议记录模块的真实展示效果。
- 涉及区域：现有 Chrome/CDP 测试脚本或新增 `tests/chrome_*` 脚本、fixture seed。
- 输入：包含多条会议记录、风险和行动项的项目任务 fixture。
- 输出：UI 验证脚本和结果记录。
- 依赖：TODO-005、TODO-006。
- 完成标准：验证会议记录标题、本地化文案、结论/风险/行动项摘要、多会议顺序、无重叠布局。
- 关联 checklist：CHK-002、CHK-003、CHK-004、CHK-005、CHK-012、CHK-014、CHK-015。

## TODO-009 Run focused regression suite

状态：已完成

- 目标：确保新增会议记录能力不破坏 Project Execution、会议行动项和 checklist 门禁。
- 涉及区域：Python backend tests、JS syntax/i18n tests、UI verification。
- 输入：TODO-007 和 TODO-008 的测试，以及现有相关回归。
- 输出：测试执行记录。
- 依赖：TODO-007、TODO-008。
- 完成标准：相关测试通过；如有环境限制，明确记录替代验证方式和风险。
- 关联 checklist：CHK-010、CHK-011、CHK-012、CHK-015。

## TODO-010 Update requirement artifacts after implementation

状态：已完成

- 目标：开发完成后更新 checklist/status，记录实现摘要、测试结果和待用户验收项。
- 涉及区域：`.cosh-docs/requirment/project-task-meeting-records/`。
- 输入：实现摘要、测试输出、已知限制。
- 输出：checklist 测试记录和 status 阶段更新。
- 依赖：TODO-009。
- 完成标准：进入 `implementation_done` 后等待用户确认 tested/done；最终 done 后按流程归档到 archive。
- 关联 checklist：CHK-001 至 CHK-015。

## 实现完成摘要

- 完成时间：2026-06-26T00:18:40+08:00
- 新增任务 `meetingRecords` 持久化和读写兼容，覆盖 approved、no_consensus、rejected、needs_user_decision 等任务会议结果。
- 任务详情新增本地化“会议记录”模块，展示结论、状态、风险、行动项摘要、meetingId、requestId 和时间；会议行动项仍保留在独立区域。
- 已补充后端、静态 UI、i18n 和真实 Chrome DOM 验证；用户最终验收仍待确认。
