# Phase 7 Artifact Management Todolist

## 执行规则

- 每个 TODO 必须在实施和验证时回溯到一个或多个 `CHK-*`。
- 本期只实现 Markdown 产物管理，不展示非 Markdown 产物。
- 产物管理必须拆成通用产物核心、通用 UI 组件、Phase 7 项目适配层。
- 本期不实现会议产物入口，但核心能力和 UI 不能写死在 Project Execution 任务看板中。
- checklist 测试通过后必须等待用户确认，才能推进 `tested` 和最终 `done`。

## TODO-001 通用产物核心模型与边界

- 目标：定义通用 artifact 数据结构、source record 结构、上下文 adapter 输入输出和安全边界。
- 涉及区域：`app/server.py` 或新增后端 artifact helper 模块。
- 输入：业务上下文 adapter 提供的根目录、可读扩展名、排除目录、source records。
- 输出：通用 artifact item、source record、workspace/root metadata、错误结构。
- 依赖：现有 Project Execution workspace validation 规则。
- 完成标准：核心模型不依赖 Project Execution task/board 字段；可以表达 project 和 future meeting 两类上下文；只读语义清晰。
- 关联 checklist：CHK-001、CHK-004、CHK-022。

## TODO-002 通用 Markdown 扫描能力

- 目标：实现可被不同 adapter 复用的 Markdown artifact discovery。
- 涉及区域：后端 artifact core/helper。
- 输入：adapter 提供的受控根目录、排除目录、深度/数量限制。
- 输出：Markdown artifact 列表，包含 path、name、size、modifiedAt、extension。
- 依赖：TODO-001。
- 完成标准：只列出 `.md` 和 `.markdown`；排除 VCS、依赖、缓存、虚拟环境和构建目录；支持空状态；工作区失效安全失败。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-010、CHK-011。

## TODO-003 通用 Markdown 安全读取能力

- 目标：实现上下文内 Markdown 文件读取。
- 涉及区域：后端 artifact core/helper。
- 输入：adapter 根目录、artifact relative path。
- 输出：Markdown 内容、size、truncated、path、错误状态。
- 依赖：TODO-001、TODO-002。
- 完成标准：拒绝非 Markdown；拒绝绝对路径、`../`、编码穿越和 symlink escape；大文件截断并标记；读取不修改文件。
- 关联 checklist：CHK-012、CHK-014、CHK-015、CHK-016、CHK-022。

## TODO-004 Phase 7 项目 Adapter

- 目标：把通用 artifact core 接入 Project Execution 项目。
- 涉及区域：`app/server.py` Project API / Project Execution workspace helpers。
- 输入：projectId、项目 workspacePath、projectExecutionEnabled、workspaceStatus。
- 输出：项目 artifact context、可读根目录、项目级错误、Project source record provider。
- 依赖：TODO-001 至 TODO-003。
- 完成标准：Project Execution 项目可用；非 Project Execution 或无 workspace 项目不可误用；复用通用核心而不是复制扫描/读取逻辑。
- 关联 checklist：CHK-003、CHK-005、CHK-006、CHK-011、CHK-023。

## TODO-005 Phase 7 来源记录 Adapter

- 目标：从 Project Execution task evidence 推断 evidence-backed source records。
- 涉及区域：Project adapter、task/attempt evidence 读取。
- 输入：项目任务列表、task evidence changedFiles、attempt evidence changedFiles、providerRef、executor、attempt 时间。
- 输出：每个 Markdown artifact 的 source records 或 unassociated 标记。
- 依赖：TODO-004。
- 完成标准：按相对路径精确匹配；记录 task title、taskId、attemptId、executor agentId、providerKind、evidence time；Reviewer 不被误标为生成者；同一文件多次记录时至少保留最新来源，不丢失最新任务和 Agent。
- 关联 checklist：CHK-017、CHK-018、CHK-019、CHK-020、CHK-021。

## TODO-006 项目 Artifact API

- 目标：提供 Project-scoped artifact list/read API，同时内部走通用 artifact core。
- 涉及区域：`app/server.py` GET routes。
- 输入：projectId、artifact path。
- 输出：artifact list/read JSON，包含 generic artifact fields 和 Phase 7 source records。
- 依赖：TODO-001 至 TODO-005。
- 完成标准：成功、项目不存在、非 Project Execution、workspace 失效、非 Markdown 读取、路径穿越、大文件截断都有明确响应；API 不暴露任意文件浏览能力。
- 关联 checklist：CHK-006、CHK-007、CHK-008、CHK-011、CHK-012、CHK-016、CHK-017、CHK-018、CHK-019。

## TODO-007 通用 Artifact Manager UI

- 目标：实现可复用的 artifact manager 前端渲染函数/组件。
- 涉及区域：`app/projects.js`、`app/projects.css`，必要时新增前端 helper。
- 输入：通用 artifact payload、context label/config、read action。
- 输出：artifact list、source record display、Preview/Source tabs、empty/error/loading states。
- 依赖：TODO-001 的通用字段约定。
- 完成标准：UI 不硬编码 Project Execution 任务字段；可配置显示 Project context，后续可配置为 Meeting context；文本不溢出或重叠。
- 关联 checklist：CHK-002、CHK-004、CHK-013、CHK-014、CHK-015、CHK-025。

## TODO-008 Phase 7 项目 UI 接入

- 目标：在 Project Manager 中接入通用 Artifact Manager。
- 涉及区域：`app/projects.js`、`app/projects.css`。
- 输入：当前 project、Project artifact API。
- 输出：Project board toolbar 入口、artifact view、返回 board 流程。
- 依赖：TODO-006、TODO-007。
- 完成标准：Project Execution 项目有入口；普通项目不误导；不影响 board、report、template、task detail；来源任务/Agent 信息可读。
- 关联 checklist：CHK-003、CHK-005、CHK-006、CHK-017、CHK-018、CHK-019、CHK-024、CHK-025。

## TODO-009 Markdown Viewer 安全与可读性

- 目标：保证 Markdown preview/source 查看体验可用且安全。
- 涉及区域：通用 Artifact Manager UI、Markdown render helper。
- 输入：Markdown read API 响应。
- 输出：Preview/Source 切换、截断提示、内容安全展示。
- 依赖：TODO-003、TODO-007。
- 完成标准：标题、列表、代码块、链接、表格可读；原文保留换行；危险 HTML/脚本不执行；大文件不会卡死 UI。
- 关联 checklist：CHK-013、CHK-014、CHK-015、CHK-016、CHK-025。

## TODO-010 后端自动化测试

- 目标：覆盖通用核心、Project adapter、API 和来源记录。
- 涉及区域：`tests/test_project_execution.py` 或新增 artifact-focused 测试文件。
- 输入：临时 status dir、临时 workspace、模拟 project/task/evidence。
- 输出：自动化测试。
- 依赖：TODO-001 至 TODO-006。
- 完成标准：覆盖通用核心不依赖 Project Execution、meeting-like adapter stub、Markdown-only、噪音目录、空状态、workspace 失效、路径安全、非 Markdown 拒绝、大文件截断、来源任务/Agent/Provider/attempt、未关联、同名不同目录精确匹配、多来源刷新。
- 关联 checklist：CHK-001、CHK-004、CHK-007、CHK-008、CHK-009、CHK-010、CHK-011、CHK-012、CHK-016、CHK-017、CHK-018、CHK-019、CHK-020、CHK-021、CHK-022。

## TODO-011 前端与浏览器验证

- 目标：验证通用组件在 Phase 7 Project Manager 中的核心浏览器流程。
- 涉及区域：本地服务、Project Manager UI、浏览器人工验收记录。
- 输入：Project Execution 项目、至少两个 Markdown artifacts，一个有 Phase 7 source record，一个 unassociated。
- 输出：浏览器验收结果。
- 依赖：TODO-007 至 TODO-009。
- 完成标准：完成“进入产物列表 -> 查看来源任务/Agent -> 打开 md -> 预览 -> 原文 -> 返回项目”；无明显重叠；空/错/截断状态可理解。
- 关联 checklist：CHK-002、CHK-005、CHK-013、CHK-014、CHK-015、CHK-025。

## TODO-012 回归测试

- 目标：确认产物管理不破坏 Phase 7 和现有项目管理。
- 涉及区域：Project Execution tests、项目 CRUD shell test、现有 Codex/OpenClaw/Hermes 相关回归按可用环境执行。
- 输入：现有测试命令和隔离状态目录。
- 输出：测试结果记录。
- 依赖：TODO-001 至 TODO-010。
- 完成标准：Project Execution 启动、执行完成、审查、返工、用户验收相关自动化继续通过；项目创建、编辑、任务创建、任务更新、报告查看和模板能力不回归；环境缺依赖时明确记录原因。
- 关联 checklist：CHK-023、CHK-024。

## TODO-013 文档和状态更新

- 目标：把实现和验证结果回写需求归档。
- 涉及区域：`.cosh-docs/requirment/phase-7-artifact-management/checklist.md`、`status.json`，必要时更新项目说明文档。
- 输入：实现摘要、测试命令、人工验收结果、未解决风险。
- 输出：checklist 测试记录、状态推进记录、交付说明。
- 依赖：TODO-010、TODO-011、TODO-012。
- 完成标准：测试结果写入 checklist 或交付说明；等待用户确认 tested；最终 done 仍需用户人工确认。
- 关联 checklist：CHK-022、CHK-023、CHK-024、CHK-025。
