# Archive Room Phase 6 Todolist

## TODO-001: Derive Project Archive Introduction Data

- 目标：为项目档案详情生成可读的档案说明数据。
- 涉及区域：Archive Room backend project derivation、project archive records。
- 输入：项目基础数据、summary、entries、artifacts、maintenance metadata、pending confirmations。
- 输出：archive introduction，包括档案用途、当前包含内容、未来补充内容、人类/AI 使用方式。
- 依赖：Phase 1-5 archive project detail data。
- 完成标准：真实项目详情能返回非机械化的档案说明，并能反映项目当前数据状态。
- 关联 checklist：CHK-001、CHK-003、CHK-004、CHK-005。

## TODO-002: Add Project Basic Information Model

- 目标：让档案基础情况包含项目基础信息。
- 涉及区域：Archive Room backend derivation、project summaries/detail API。
- 输入：project title、description、status、tasks、updatedAt、active AI/participants、artifact count、pending count、maintenance state、source types。
- 输出：structured projectBasicInfo 或等价字段。
- 依赖：TODO-001。
- 完成标准：项目名称、描述、状态、任务进度、最近更新、长期维护状态、活跃 AI/参与者、产物数量、待确认数量和主要来源类型可被前端渲染；缺失字段有明确 missing 状态。
- 关联 checklist：CHK-005、CHK-006、CHK-007。

## TODO-003: Build Archive Contents And Usage Map

- 目标：展示档案里有什么以及能用来做什么。
- 涉及区域：Archive Room backend derivation、frontend detail UI。
- 输入：entries kinds、artifacts kinds/sources、pending confirmations、maintenance records、summary fields、task/meeting/chat source refs。
- 输出：content map and usage map。
- 依赖：TODO-001、TODO-002。
- 完成标准：按内容类型展示存在/缺失状态；按使用目的展示人类验收、交接、AI 入场、任务执行上下文、风险治理、产物浏览等能力。
- 关联 checklist：CHK-002、CHK-004、CHK-005。

## TODO-004: Redesign Archive Detail Top Sections

- 目标：调整档案室项目详情首屏，让人先理解项目和档案。
- 涉及区域：app/archive-room.js、app/archive-room.css。
- 输入：archive introduction、projectBasicInfo、content map、usage map、existing summary。
- 输出：新的项目详情顶部 UI。
- 依赖：TODO-001、TODO-002、TODO-003。
- 完成标准：机械 Goal/Current State/Next Step 不再是唯一基础情况；第一屏同时包含项目身份、档案用途、完整度/覆盖状态和可用动作。
- 关联 checklist：CHK-001、CHK-005、CHK-006、CHK-007。

## TODO-005: Generate Standard AI Onboarding Package

- 目标：提供标准项目级 AI 入场包。
- 涉及区域：Archive Room backend onboarding derivation、project detail API。
- 输入：project basic info、summary、confirmed rules、decisions、risks/blockers、artifacts、archive index、source references、missing context。
- 输出：structured onboarding package and copy text。
- 依赖：TODO-001、TODO-002、TODO-003。
- 完成标准：请求项目 onboarding context 时返回项目目标、当前状态、关键规则、当前任务、关键决策、风险/阻塞、目录索引、产物和来源引用。
- 关联 checklist：CHK-008、CHK-009、CHK-012。

## TODO-006: Add Task-Level Context Package

- 目标：为当前任务生成任务优先的 AI 上下文。
- 涉及区域：Archive Room backend helpers、project/task APIs or workflow context path。
- 输入：project ID、task ID、task details、related entries、decisions、risks、artifacts、source refs。
- 输出：task-level context package。
- 依赖：TODO-005。
- 完成标准：任务上下文先返回任务目标、依赖、历史决策、风险、阻塞、相关产物和来源，再补项目背景。
- 关联 checklist：CHK-010、CHK-011、CHK-013。

## TODO-007: Implement AI Context Query Response Shape

- 目标：提供 AI/system-facing 上下文查询结构。
- 涉及区域：Archive Room backend API/helper, workflow context integration points。
- 输入：project ID、optional task ID、query purpose、archive entries、artifacts、sources。
- 输出：conclusions first、source references second、optional next-load entries third 的结构化响应。
- 依赖：TODO-005、TODO-006。
- 完成标准：复杂项目不会默认展开全部历史；响应包含可继续加载的 archive entries/artifacts。
- 关联 checklist：CHK-011、CHK-012、CHK-013。

## TODO-008: Preserve Confidence, Stale, Pending Markers In Context

- 目标：防止 AI 把推断或待确认内容当成事实。
- 涉及区域：Archive Room context package generation。
- 输入：entry confidence、stale flag、pending confirmations、source references。
- 输出：context items with confidence/state markers。
- 依赖：TODO-005、TODO-007。
- 完成标准：confirmed_fact、ai_inference、pending_confirmation_suggestion、stale 在上下文包中可区分。
- 关联 checklist：CHK-012。

## TODO-009: Add Project-Characterized Context Injection

- 目标：让同一个 AI 在不同项目/任务中获得项目特征化上下文。
- 涉及区域：workflow/project execution prompt context, Archive Room context helpers。
- 输入：business background、goals、confirmed rules、user preferences、decision style、important history、risks、artifacts。
- 输出：project/task supplemental context block。
- 依赖：TODO-005、TODO-006、TODO-008。
- 完成标准：不同项目的上下文不只是项目名不同；上下文体现项目目标、规则、历史、风险、产物或偏好差异。
- 关联 checklist：CHK-014、CHK-015。

## TODO-010: Guard Against Global AI Identity Rewrite

- 目标：确保项目特征化上下文不会改写 AI 全局身份和边界。
- 涉及区域：prompt/context templates、archive manager profile guidance if needed。
- 输入：project-characterized context block。
- 输出：bounded supplemental context wording。
- 依赖：TODO-009。
- 完成标准：上下文明确作为项目/任务补充，不覆盖 AI 的基础身份、安全边界或工具规则。
- 关联 checklist：CHK-016。

## TODO-011: Implement Archive Manager Missing Context Reminders

- 目标：上下文查询时返回普通缺失提醒。
- 涉及区域：Archive Room context helpers、archive manager reminder derivation。
- 输入：missing project description、missing rules、missing sources、stale entries。
- 输出：query-time missing context reminders。
- 依赖：TODO-007、TODO-008。
- 完成标准：普通缺失出现在上下文响应中，但不主动打断执行 AI。
- 关联 checklist：CHK-017、CHK-019。

## TODO-012: Implement Severe Conflict Reminder Candidate

- 目标：严重冲突可主动提醒执行 AI。
- 涉及区域：Archive Room reminder helpers、workflow/project execution integration points。
- 输入：confirmed rules、task context、conflicting entries or actions、source refs。
- 输出：severe conflict reminder with sources and suggested handling。
- 依赖：TODO-008、TODO-009、TODO-011。
- 完成标准：严重冲突产生可追溯提醒；普通风险不强制打断。
- 关联 checklist：CHK-018、CHK-019。

## TODO-013: Keep Artifact Browser And Maintenance UI Regression-Safe

- 目标：Phase 6 UI 调整不破坏 Phase 1-5。
- 涉及区域：app/archive-room.js、app/archive-room.css。
- 输入：existing artifact browser, maintenance control, maintenance history。
- 输出：compatible UI layout。
- 依赖：TODO-004。
- 完成标准：产物两栏弹窗、按来源/按路径、图片/视频/音频/文档预览、长期维护状态和整理记录继续可用。
- 关联 checklist：CHK-020、CHK-021、CHK-023。

## TODO-014: Add Degraded/Error States

- 目标：上下文生成或档案管理员异常时 Archive Room 仍可用。
- 涉及区域：backend error handling、frontend empty/error states。
- 输入：context generation failure、archive manager unavailable、missing archive data。
- 输出：degraded context status and readable UI fallback。
- 依赖：TODO-001、TODO-005、TODO-007。
- 完成标准：已有项目档案和产物仍可查看；上下文/提醒能力显示降级或错误，不导致主应用不可用。
- 关联 checklist：CHK-007、CHK-024。

## TODO-015: Add Phase 6 Backend Tests

- 目标：覆盖 Phase 6 数据派生和上下文响应。
- 涉及区域：tests/test_archive_room_phase_6.py。
- 输入：Phase 6 checklist and fixture projects。
- 输出：focused backend tests。
- 依赖：TODO-001 到 TODO-012。
- 完成标准：覆盖档案说明、基础信息、内容/用途地图、onboarding package、task context、confidence markers、project-characterized context、missing/severe reminders、degraded mode。
- 关联 checklist：CHK-001 到 CHK-019、CHK-024。

## TODO-016: Add Frontend/UI Acceptance Fixtures Or Smoke

- 目标：验证人类可读档案详情和回归 UI。
- 涉及区域：Archive Room local service, browser/MCP or deterministic UI smoke。
- 输入：真实或 fixture projects with tasks, artifacts, maintenance records, missing fields。
- 输出：UI acceptance notes/screenshots if applicable。
- 依赖：TODO-004、TODO-013、TODO-014。
- 完成标准：人类可读说明、基础信息、内容地图、用途地图可见；产物和维护 UI 未回归。
- 关联 checklist：CHK-001 到 CHK-007、CHK-020、CHK-021、CHK-022。

## TODO-017: Run Regression Tests

- 目标：确认 Phase 1-5 和现有业务流程不回归。
- 涉及区域：archive room tests, project execution tests, meeting tests, frontend syntax checks。
- 输入：implemented Phase 6 code。
- 输出：test run results。
- 依赖：TODO-015、TODO-016。
- 完成标准：相关 archive room tests、project/task/chat/meeting regression tests、py_compile、frontend syntax checks 通过。
- 关联 checklist：CHK-020、CHK-021、CHK-023、CHK-024。

## TODO-018: Update Requirement Archive Status

- 目标：按实现和测试结果更新 Phase 6 需求归档。
- 涉及区域：.cosh-docs/requirment/archive-room-phase-6/checklist.md、status.json。
- 输入：implementation summary、test commands、user acceptance。
- 输出：implementation/test records and status transitions。
- 依赖：TODO-017。
- 完成标准：开发完成后进入 implementation_done/tested；用户验收后才标记 done。
- 关联 checklist：CHK-001 到 CHK-024。
