# Archive Room Phase 5 Todolist

## TODO-001: Add Project Archive Maintenance Eligibility

- 目标：为项目增加“是否需要长期维护档案”的产品属性，并支持默认推导。
- 涉及区域：project data model、Archive Room derivation、project update/create paths。
- 输入：项目 status、用户显式设置、Phase 5 requirement。
- 输出：可持久化或可推导的 archive maintenance enabled state。
- 依赖：Phase 1-4 archive project records。
- 完成标准：active/ongoing 默认开启；completed/paused/archived/inactive 默认关闭；显式设置优先。
- 关联 checklist：CHK-001、CHK-002。

## TODO-002: Expose Maintenance Control In Project And Archive UI

- 目标：让用户在项目详情和档案室项目详情都能看到并切换长期维护状态。
- 涉及区域：app/game.js project detail UI、Archive Room detail UI、server endpoints。
- 输入：项目 ID、当前维护状态、用户切换动作。
- 输出：维护开关 UI、状态保存、两处 UI 一致显示。
- 依赖：TODO-001。
- 完成标准：两处都可见可管理；关闭时显示轻量说明“定时巡检和低价值事件跳过，高价值事件仍归档”。
- 关联 checklist：CHK-003、CHK-004。

## TODO-003: Define Archive Maintenance Trigger Model

- 目标：建立统一的自动整理触发模型，避免事件处理逻辑分散且不可追踪。
- 涉及区域：app/server.py archive-room helpers、archive manager state、project archive records。
- 输入：event type、project ID、source reference、value level、classification reason、idempotency key。
- 输出：统一 trigger result，包括 ok/skipped/error/no_update、maintenance record、source references。
- 依赖：Phase 4 archive manager state and activity records。
- 完成标准：所有 Phase 5 自动整理入口都走同一套触发/记录规则。
- 关联 checklist：CHK-005 到 CHK-014、CHK-024 到 CHK-029。

## TODO-004: Implement High-Value Event Rules And Maintenance-Off Behavior

- 目标：明确高价值事件即使维护关闭也继续整理，低价值事件在维护关闭时跳过。
- 涉及区域：archive maintenance trigger helper、project archive records。
- 输入：事件类型、项目维护状态、高价值事件列表。
- 输出：high-value / low-value 分流和 skip reason。
- 依赖：TODO-001、TODO-003。
- 完成标准：任务完成/失败、项目状态变化、重要产物、阻塞、冲突提醒、会议结论始终可整理；维护关闭时低价值事件跳过。
- 关联 checklist：CHK-012、CHK-013。

## TODO-005: Hook Task Completion And Task Failure/Blocker Events

- 目标：在任务完成、任务失败或 blocker 变化时触发项目档案整理。
- 涉及区域：project task move/update paths、project execution completion/failure paths、archive trigger helper。
- 输入：task ID、project ID、完成/失败/blocker source reference。
- 输出：项目档案刷新、维护记录、必要的 risk/blocker archive entry。
- 依赖：TODO-003、TODO-004。
- 完成标准：任务完成和任务失败/阻塞能更新档案；重复事件幂等。
- 关联 checklist：CHK-005、CHK-006、CHK-014、CHK-024、CHK-027。

## TODO-006: Hook Project Status Change Events

- 目标：项目状态变化时自动刷新档案状态和维护默认语义。
- 涉及区域：project update paths、Archive Room derivation、archive trigger helper。
- 输入：project ID、old status、new status。
- 输出：项目档案 current state/status 更新，维护记录包含 status change source。
- 依赖：TODO-001、TODO-003、TODO-004。
- 完成标准：active/paused/completed/archived 等变化能触发整理并保留来源。
- 关联 checklist：CHK-007、CHK-012、CHK-014、CHK-027。

## TODO-007: Hook Important Artifact Events

- 目标：重要产物生成或关联时刷新档案产物区和维护记录。
- 涉及区域：project artifact listing/association、artifact metadata、archive trigger helper。
- 输入：artifact path/metadata、project ID、source task or event。
- 输出：档案产物元数据刷新、maintenance record。
- 依赖：TODO-003、TODO-004、Phase 3 artifact preview。
- 完成标准：重要产物可见并带来源；重复关联不产生重复条目。
- 关联 checklist：CHK-008、CHK-014、CHK-024、CHK-027、CHK-031。

## TODO-008: Hook Meeting Conclusion Events

- 目标：项目相关会议结束并产生结论时触发档案整理。
- 涉及区域：executable meeting completion paths、meeting events store、archive trigger helper。
- 输入：meeting ID、project ID、meeting result/conclusion。
- 输出：会议结论 archive entry 或 pending confirmation，维护记录包含 meeting source。
- 依赖：TODO-003、TODO-004。
- 完成标准：完成会议后项目档案可看到结论或待确认摘要；重复完成事件幂等。
- 关联 checklist：CHK-009、CHK-012、CHK-014、CHK-025、CHK-027。

## TODO-009: Support Conflict Reminder And AI Stage Summary Intake

- 目标：支持冲突提醒和 AI 阶段总结进入整理流程。
- 涉及区域：workflow/project execution status, conflict/risk recording paths, archive trigger helper。
- 输入：conflict reminder、AI stage summary、project ID、source reference。
- 输出：风险/冲突/summary archive update 或 pending confirmation。
- 依赖：TODO-003、TODO-004。
- 完成标准：冲突和阶段总结能被归档或进入待确认，并记录分类理由。
- 关联 checklist：CHK-010、CHK-011、CHK-025、CHK-026、CHK-027。

## TODO-010: Implement Startup Inspection

- 目标：VO 启动后对长期维护项目执行一次补漏巡检。
- 涉及区域：server startup threads、archive manager state、archive room records。
- 输入：project list、maintenance eligibility、archive manager paused state。
- 输出：latest startup inspection time、skip/no_update/updated results。
- 依赖：TODO-001、TODO-003、TODO-004。
- 完成标准：只巡检长期维护项目；暂停时跳过；无更新只更新时间不刷维护记录。
- 关联 checklist：CHK-015、CHK-017、CHK-018、CHK-019。

## TODO-011: Implement Daily Inspection

- 目标：对长期维护项目执行每日补漏巡检，并避免同日重复噪音。
- 涉及区域：server scheduled/background loop or cron-style helper、archive manager state。
- 输入：current date、project list、maintenance eligibility、last daily inspection。
- 输出：latest daily inspection time、updated/no_update/skipped results。
- 依赖：TODO-001、TODO-003、TODO-004。
- 完成标准：每天一次；重复运行幂等；无更新不刷屏。
- 关联 checklist：CHK-016、CHK-017、CHK-018、CHK-019。

## TODO-012: Add Important Message Marking And Queue

- 目标：用户标记重要消息后进入待整理队列，而不是直接作为正式事实入档。
- 涉及区域：chat/agent communication UI or APIs、archive-room storage、archive trigger helper。
- 输入：message source reference、project ID、user mark action。
- 输出：pending maintenance queue item with source reference。
- 依赖：TODO-003。
- 完成标准：重要消息可标记；进入待整理队列；保留来源和时间。
- 关联 checklist：CHK-020、CHK-027、CHK-032。

## TODO-013: Summarize Important Messages Into Archive Entries

- 目标：将重要消息整理成稳定 archive entry，并记录分类原因。
- 涉及区域：archive manager output contract、archive records、pending queue processing。
- 输入：pending important message item、source message、classification reason。
- 输出：summary archive entry、confidence、source reference、maintenance record。
- 依赖：TODO-012、Phase 4 archive manager profile/output contract。
- 完成标准：原始消息不直接变成正式事实；整理后条目稳定、可追溯。
- 关联 checklist：CHK-021、CHK-024、CHK-025、CHK-027。

## TODO-014: Add Archive AI Important Chat Classification

- 目标：识别未标记聊天中的决策、风险、阻塞、产物上下文，并生成候选整理项。
- 涉及区域：communication history readers、archive manager classification path、archive queue。
- 输入：project-related chat messages、classification criteria。
- 输出：candidate archive entry or pending queue item with reason。
- 依赖：TODO-003、TODO-013。
- 完成标准：重要聊天可被识别并说明原因；低价值聊天不会刷 archive entries。
- 关联 checklist：CHK-022、CHK-023、CHK-026、CHK-027。

## TODO-015: Implement Pending Confirmation Routing Rules

- 目标：将低置信、冲突、高影响推断路由到 pending confirmation，普通摘要静默入档。
- 涉及区域：archive entry creation、pending confirmation data、Archive Room project records。
- 输入：archive update kind、confidence、impact area、conflict state。
- 输出：direct archive entry or pending confirmation suggestion。
- 依赖：TODO-003、Phase 1 confidence model。
- 完成标准：影响项目状态/任务结论/风险判断的内容进入 pending confirmation；普通摘要不制造噪音。
- 关联 checklist：CHK-024、CHK-025、CHK-026、CHK-027、CHK-028。

## TODO-016: Improve Maintenance Activity Visibility

- 目标：让用户能看到自动整理触发原因、来源和结果，同时保持普通整理低打扰。
- 涉及区域：Archive Room overview/detail UI、archive manager recent activity、project archive maintenance records。
- 输入：trigger outcomes、maintenance records、pending confirmation counts。
- 输出：重要结果和 pending entry points 可见；普通整理可查但不打扰。
- 依赖：TODO-003、TODO-015。
- 完成标准：记录包含 trigger type、project、source、time、result、error or skip reason。
- 关联 checklist：CHK-028、CHK-029。

## TODO-017: Preserve Pause/Resume And Manual Maintenance Behavior

- 目标：确保 Phase 4 档案管理员控制在 Phase 5 自动整理加入后不回归。
- 涉及区域：archive manager state, automatic triggers, manual maintain endpoint。
- 输入：paused/resumed state、manual maintain action、automatic trigger。
- 输出：paused skip behavior、resumed automatic behavior、manual maintain compatibility。
- 依赖：TODO-003、Phase 4 implementation。
- 完成标准：暂停时自动触发和巡检跳过；恢复后可继续；手动当前项目整理仍可用。
- 关联 checklist：CHK-018、CHK-030、CHK-031。

## TODO-018: Add Phase 5 Tests

- 目标：用自动化测试覆盖 Phase 5 核心验收路径和噪音控制。
- 涉及区域：tests/test_archive_room_phase_5.py and related fixtures。
- 输入：Phase 5 checklist、existing archive room tests。
- 输出：focused backend tests plus selected regression coverage。
- 依赖：TODO-001 到 TODO-017。
- 完成标准：覆盖维护属性默认/显式设置、事件触发、维护关闭、高价值/低价值分流、巡检、重要消息、pending confirmation、pause/skip、幂等。
- 关联 checklist：CHK-001 到 CHK-033。

## TODO-019: Run Regression And Live Smoke

- 目标：确认 Phase 5 不破坏 Phase 1-4 和既有项目/任务/聊天/会议流程。
- 涉及区域：test suite, live local service, Archive Room UI。
- 输入：implemented Phase 5 code。
- 输出：test results and smoke notes written back to checklist/status。
- 依赖：TODO-018。
- 完成标准：相关 Python tests 通过；`./start.sh` 启动后 Archive Room 可用；事件触发/巡检/维护开关基本路径可验证。
- 关联 checklist：CHK-030、CHK-031、CHK-032、CHK-033。

## TODO-020: Update Requirement Archive Status

- 目标：按实现和测试结果更新 Phase 5 需求归档。
- 涉及区域：.cosh-docs/requirment/archive-room-phase-5/checklist.md、status.json。
- 输入：实现摘要、测试命令、用户验收状态。
- 输出：implementation/test records and status transitions。
- 依赖：TODO-019。
- 完成标准：开发完成后进入 implementation_done/tested；最终等待用户验收后才标记 done。
- 关联 checklist：CHK-033。

