# Project Execution Project Start Todolist

## TODO-001 Confirm Existing Project Execution Data Model
- 目标：梳理当前 project/task/workflow 字段和 Project Execution 状态机，确定新增字段最小集。
- 涉及区域：`app/server.py`、`app/project_store.py`、`app/projects.js`、现有测试。
- 输入：`requirement.md`、`review.md`、`checklist.md`、现有 Project Execution task start/status/review/accept 逻辑。
- 输出：实现前的字段和状态流判断；避免重复旧 workflow autoMode。
- 依赖：无。
- 完成标准：明确 task manual acceptance 字段、项目启动模式字段是否需要持久化，以及连续流复用点。
- 关联 checklist：CHK-001、CHK-001A、CHK-011、CHK-011A、CHK-011B。

## TODO-002 Add Task Manual Acceptance Field
- 目标：为 Project Execution task 增加是否需要人工验收的字段，并保证读写兼容旧数据。
- 涉及区域：任务创建、任务更新、项目持久化、任务详情。
- 输入：现有 task schema、任务 CRUD API。
- 输出：默认安全的 `requiresUserAcceptance` 或等价字段；旧任务有稳定默认值。
- 依赖：TODO-001。
- 完成标准：创建任务时可保存该字段；旧任务读取不会报错；任务详情可更新该字段。
- 关联 checklist：CHK-011A、CHK-011B、CHK-015。

## TODO-003 Add Project Execution Start Mode Support
- 目标：为项目级启动增加“启动下一个任务 / 连续启动任务”模式。
- 涉及区域：项目状态、前端 toolbar 状态、项目启动 API body/response。
- 输入：用户确认的默认模式“连续启动任务”。
- 输出：`single`/`continuous` 或等价启动模式；默认连续启动；响应包含启动模式。
- 依赖：TODO-001。
- 完成标准：Project Execution 项目打开后默认连续模式；普通项目 workflow autoMode 不受影响。
- 关联 checklist：CHK-001、CHK-001A、CHK-002、CHK-013、CHK-014。

## TODO-004 Implement Project-Level Start Coordinator API
- 目标：新增 Project Execution 项目级启动入口，选择 next eligible task 并复用任务级启动逻辑。
- 涉及区域：`app/server.py` API route、task selection helper、现有 `_handle_project_execution_start`。
- 输入：现有任务级 start API、done-column 判断、active task 判断。
- 输出：例如 `POST /api/projects/{projectId}/project-execution/start` 的项目级启动 API。
- 依赖：TODO-001、TODO-003。
- 完成标准：API 能按列顺序和任务顺序选择第一个 eligible task；跳过 Done 类列；返回 selected task、attempt、mode、requiresUserAcceptance；错误可操作。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010、CHK-014。

## TODO-005 Implement Continuous Task Flow Stop And Continue Rules
- 目标：实现连续模式下的自动推进与停止条件。
- 涉及区域：Project Execution review/accept/status 逻辑、项目状态同步。
- 输入：任务级审查结果、manual acceptance 字段、selected start mode。
- 输出：审查通过且不需人工验收时自动继续；需要人工验收或发生阻塞时停止并展示状态。
- 依赖：TODO-002、TODO-003、TODO-004。
- 完成标准：不会并发启动多个任务；遇到缺角色、dirty confirmation、审查失败、阻塞、错误、无 eligible task、需要人工验收都会停止并说明原因。
- 关联 checklist：CHK-003A、CHK-003B、CHK-009、CHK-011C、CHK-011D、CHK-017A。

## TODO-006 Update Frontend Toolbar And Control Panel
- 目标：在 Project Execution 项目 toolbar 中加入项目级启动按钮、启动模式单选和状态展示。
- 涉及区域：`app/projects.js` board toolbar、workflow status render、toast/error handling。
- 输入：项目级启动 API、Project Execution status API。
- 输出：用户可直接点击“启动项目”；可选择“启动下一个任务/连续启动任务”；状态能显示 active task 和等待人工验收。
- 依赖：TODO-003、TODO-004、TODO-005。
- 完成标准：不打开任务详情也能启动；普通项目旧 workflow 控件不变；错误和停止原因清晰展示。
- 关联 checklist：CHK-001、CHK-001A、CHK-002、CHK-013、CHK-017、CHK-017A。

## TODO-007 Update Task Creation And Task Detail UI
- 目标：在创建任务和任务详情/control panel 中暴露“需要人工验收”配置。
- 涉及区域：`app/projects.js` task create/edit/detail UI、task update API 调用。
- 输入：TODO-002 新增字段。
- 输出：创建任务时明确选择人工验收；任务详情可查看和调整。
- 依赖：TODO-002。
- 完成标准：字段保存后刷新仍存在；连续流能按该字段决定是否等待人工验收。
- 关联 checklist：CHK-011A、CHK-011B、CHK-011C、CHK-011D。

## TODO-008 Preserve Existing Task-Level Start And Normal Workflow
- 目标：确保任务详情“启动此任务”和普通项目旧 workflow 仍保持原行为。
- 涉及区域：Project Execution task actions、legacy workflow start/stop/auto-mode。
- 输入：现有行为和测试。
- 输出：回归保护。
- 依赖：TODO-004、TODO-006。
- 完成标准：任务详情启动可用；普通项目 start/stop/auto-mode 控件和 API 不变。
- 关联 checklist：CHK-002、CHK-012、CHK-015。

## TODO-009 Add Backend Focused Tests
- 目标：补充项目级启动、任务选择、连续流、人工验收字段和错误场景测试。
- 涉及区域：`tests/test_project_execution.py` 或相邻测试。
- 输入：TODO-002 到 TODO-005 的后端行为。
- 输出：覆盖 API、状态和边界条件的自动化测试。
- 依赖：TODO-002、TODO-003、TODO-004、TODO-005。
- 完成标准：覆盖 first eligible、Done skip、no task、no eligible、missing executor/reviewer、active conflict、dirty confirmation、manual acceptance stop、no acceptance auto-continue。
- 关联 checklist：CHK-003、CHK-003A、CHK-003B、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010、CHK-011C、CHK-011D、CHK-014、CHK-017A、CHK-018。

## TODO-010 Add Frontend And Integration Validation
- 目标：验证前端语法、关键 UI 行为和项目 CRUD/Project Execution 回归。
- 涉及区域：`app/projects.js`、CRUD shell tests、可用 MCP/browser 验证。
- 输入：完成后的前后端实现。
- 输出：测试运行记录和人工验证结果。
- 依赖：TODO-006、TODO-007、TODO-008、TODO-009。
- 完成标准：`node --check app/projects.js`、Python 编译/测试、Project CRUD 回归、必要的 MCP/UI 验证通过。
- 关联 checklist：CHK-001、CHK-001A、CHK-002、CHK-012、CHK-013、CHK-016、CHK-017、CHK-018。

## TODO-011 Update Requirement Status And Test Evidence
- 目标：开发和验证完成后更新需求归档状态与测试记录。
- 涉及区域：`.cosh-docs/requirment/project-execution-project-start/checklist.md`、`status.json`。
- 输入：自动化测试结果、人工验证结果。
- 输出：checklist 测试记录；等待用户确认 tested/done。
- 依赖：TODO-010。
- 完成标准：记录每项关键验证结果；`status.json` 推进到实现完成或测试完成对应阶段，但最终 done 等待用户确认。
- 关联 checklist：CHK-018。
