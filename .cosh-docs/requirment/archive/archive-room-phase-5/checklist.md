# Archive Room Phase 5 Checklist

确认状态：已确认

## Project Maintenance Eligibility

### CHK-001: Maintenance Attribute Exists

- 关联需求点：项目需要新增“是否需要长期维护档案”的属性。
- 验证方法：创建或读取项目，查看项目数据和 Archive Room 项目数据。
- 预期结果：项目能表达是否需要长期档案维护；未显式设置时可根据项目状态推导默认值。

### CHK-002: Maintenance Default By Project Status

- 关联需求点：进行中项目默认开启维护，完成/暂停/归档项目默认关闭维护。
- 验证方法：准备 active、completed、paused、archived 等不同状态项目并查看维护状态。
- 预期结果：active/ongoing 项目默认为维护开启；completed/paused/archived/inactive 项目默认为维护关闭；显式用户设置优先于默认推导。

### CHK-003: Maintenance Control Visibility

- 关联需求点：维护属性在项目详情页和档案室项目详情页都可见、可管理。
- 验证方法：分别打开项目详情和 Archive Room 项目详情，切换维护状态。
- 预期结果：两处都能看到当前维护状态；变更后另一处刷新可见同一状态。

### CHK-004: Maintenance-Off Explanation

- 关联需求点：关闭长期维护时应轻量说明定时巡检和低价值事件跳过，高价值事件仍归档。
- 验证方法：关闭某项目长期维护并查看 UI 文案。
- 预期结果：用户能理解这不是彻底禁止归档；高价值事件仍会被保留。

## Event-Triggered整理

### CHK-005: Task Completion Trigger

- 关联需求点：任务完成是高价值事件，应触发整理。
- 验证方法：将任务移动到完成列或通过项目执行完成任务。
- 预期结果：相关项目档案更新，维护记录包含 task completion 触发来源、任务 ID 和结果。

### CHK-006: Task Failure Or Blocker Trigger

- 关联需求点：任务失败和阻塞是高价值事件，应触发整理。
- 验证方法：制造任务失败或 blocker 记录。
- 预期结果：项目档案风险/阻塞信息更新；维护记录包含失败或 blocker 来源。

### CHK-007: Project Status Change Trigger

- 关联需求点：项目状态变化是高价值事件，应触发整理。
- 验证方法：修改项目状态为 active、paused、completed 或 archived。
- 预期结果：档案中的项目状态、当前阶段或维护默认状态被刷新，并记录 project status change 来源。

### CHK-008: Important Artifact Trigger

- 关联需求点：重要产物生成或更新是高价值事件，应触发整理。
- 验证方法：创建或关联一个重要任务产物。
- 预期结果：产物进入档案产物区或刷新元数据；维护记录包含 artifact 来源和类型。

### CHK-009: Meeting Conclusion Trigger

- 关联需求点：会议结论是高价值协作事件，应触发整理。
- 验证方法：完成一次关联项目的会议并生成结论或结果。
- 预期结果：项目档案记录会议结论或待确认摘要；维护记录包含 meeting conclusion 来源。

### CHK-010: Conflict Reminder Trigger

- 关联需求点：冲突提醒是高价值协作事件，应触发整理。
- 验证方法：模拟或触发一条项目相关冲突提醒。
- 预期结果：档案中产生冲突/风险相关条目或 pending confirmation；维护记录包含 conflict reminder 来源。

### CHK-011: AI Stage Summary Trigger

- 关联需求点：AI 阶段总结属于协作链路事件，应触发整理。
- 验证方法：准备一条关联项目的 AI stage summary。
- 预期结果：档案 current state、timeline 或 summary 信息更新；维护记录包含 stage summary 来源和分类理由。

### CHK-012: Maintenance-Off High-Value Event Still Archives

- 关联需求点：关闭长期维护后，高价值事件仍触发整理。
- 验证方法：关闭项目长期维护后触发任务完成、项目状态变化或会议结论。
- 预期结果：对应高价值事件仍进入整理；维护记录说明项目维护关闭但高价值事件被保留。

### CHK-013: Maintenance-Off Low-Value Event Skips

- 关联需求点：关闭长期维护后，低价值事件和 routine 整理跳过。
- 验证方法：关闭项目长期维护后触发低价值补充或普通活动。
- 预期结果：不新增档案正文或 pending confirmation；如记录活动，应为简短 skipped 结果且不刷屏。

### CHK-014: Trigger Idempotency

- 关联需求点：自动整理不能因为重复事件或重复请求产生大量重复档案项。
- 验证方法：重复提交同一 task completion、meeting conclusion 或 artifact trigger。
- 预期结果：同一 source reference 不产生重复 archive entries；维护记录能体现已处理或幂等跳过。

## Scheduled Inspection

### CHK-015: Startup Inspection For Maintained Projects

- 关联需求点：VO 启动后对长期维护项目巡检一次，用于补漏。
- 验证方法：启动 VO 后查看 Archive Room 管理记录和项目 latest inspection。
- 预期结果：长期维护项目被巡检；latest startup inspection time 更新；跳过未维护项目。

### CHK-016: Daily Inspection For Maintained Projects

- 关联需求点：每天对长期维护项目巡检一次。
- 验证方法：通过可控时间或调度入口触发每日巡检。
- 预期结果：长期维护项目每日巡检运行；同一天重复运行不会创建重复整理内容。

### CHK-017: Inspection No-Update Behavior

- 关联需求点：巡检无更新时只更新最近巡检时间，不生成完整整理记录。
- 验证方法：对没有变化的维护项目运行启动/每日巡检。
- 预期结果：latest inspection time 更新；最近维护记录不被“无更新”记录刷屏。

### CHK-018: Inspection Skips Paused Archive Manager

- 关联需求点：档案管理员暂停时不主动自动整理。
- 验证方法：暂停档案管理员后触发启动/每日巡检。
- 预期结果：巡检被跳过；记录简短 skip reason；已有档案仍可浏览。

### CHK-019: Inspection Failure Logged Quietly

- 关联需求点：Phase 5 自动整理失败只记录日志，不主动打扰用户。
- 验证方法：模拟巡检或整理失败。
- 预期结果：失败进入维护记录或错误日志；不弹出强提醒，不阻断主应用。

## Important Chat Intake

### CHK-020: User-Marked Important Message Enters整理 Queue

- 关联需求点：用户标记重要消息后进入待整理队列，由档案管理员总结后入档。
- 验证方法：将一条项目相关聊天标记为重要。
- 预期结果：该消息不会作为原始聊天直接成为正式事实；它进入待整理队列并保留来源。

### CHK-021: Important Message Summarized Into Archive Entry

- 关联需求点：重要消息需要被整理为稳定档案条目。
- 验证方法：处理待整理重要消息。
- 预期结果：生成稳定 archive entry，包含摘要、来源消息、置信度和分类原因。

### CHK-022: Archive AI Important Chat Classification

- 关联需求点：未标记聊天中包含决策/风险/阻塞/产物上下文时，可由档案管理员识别为重要。
- 验证方法：准备一条未标记但包含决策或风险的项目聊天。
- 预期结果：系统创建候选整理项或 archive entry，并记录为什么被分类为重要。

### CHK-023: Low-Value Chat Does Not Flood Archive

- 关联需求点：Phase 5 不把每条聊天都变成档案。
- 验证方法：产生多条闲聊、进度寒暄或无长期价值消息。
- 预期结果：低价值聊天不会产生正式 archive entries 或 pending confirmations。

## Archive Output And Pending Confirmation

### CHK-024: High-Confidence Source-Backed Fact Directly Archives

- 关联需求点：高置信、有来源的事实可直接进入档案。
- 验证方法：触发任务完成或重要产物事件。
- 预期结果：档案记录为 confirmed/source-backed fact 或合适的高置信条目，并带 source reference。

### CHK-025: Low-Confidence Or Conflicting Content Enters Pending Confirmation

- 关联需求点：低置信、冲突或高影响推断进入 pending confirmation。
- 验证方法：制造与现有档案冲突的 AI 推断或低置信总结。
- 预期结果：不覆盖已有确认内容；新内容进入 pending confirmation 或 conflict state。

### CHK-026: Pending Confirmation Limited To High-Impact Changes

- 关联需求点：影响项目状态、任务结论、风险判断的内容需要确认，普通摘要不制造噪音。
- 验证方法：分别触发状态影响型整理和普通摘要整理。
- 预期结果：状态/任务/风险影响项进入 pending confirmation；普通摘要静默入档或仅记录维护结果。

### CHK-027: Source References Preserved

- 关联需求点：自动整理条目必须可追溯来源。
- 验证方法：打开自动整理生成的任务、会议、产物、聊天条目。
- 预期结果：每个条目包含可识别的 source type、source id、时间或文件引用；来源缺失时显示明确状态。

## User Visibility And Regression

### CHK-028: Important Results And Pending Entry Points Visible

- 关联需求点：重要整理结果和待确认入口应突出，普通整理静默记录。
- 验证方法：触发重要整理和普通整理后打开 Archive Room。
- 预期结果：重要结果或 pending confirmation 入口可见；普通整理只在最近维护记录或详情中可查。

### CHK-029: Maintenance Activity Records Include Trigger And Outcome

- 关联需求点：用户能理解何时因什么触发整理以及结果如何。
- 验证方法：查看最近维护记录。
- 预期结果：记录包含触发类型、项目、来源、时间、结果、错误摘要或 skip reason。

### CHK-030: Archive Manager Pause/Resume Regression

- 关联需求点：Phase 4 pause/resume 行为不能回归。
- 验证方法：暂停、恢复档案管理员，并触发自动整理。
- 预期结果：暂停时自动整理跳过；恢复后自动整理可继续；手动当前项目整理仍按 Phase 4 规则工作。

### CHK-031: Phase 1-4 Regression

- 关联需求点：Phase 5 不破坏已验收的档案室基础能力和档案管理员生命周期。
- 验证方法：打开档案室概览、项目详情、产物预览、档案管理员状态、普通任务/会议边界。
- 预期结果：Phase 1-4 已验收能力继续可用。

### CHK-032: Existing Project, Task, Chat, Meeting Regression

- 关联需求点：Archive Room 不替代或破坏已有业务流程。
- 验证方法：执行项目创建/编辑、任务移动/完成、聊天、会议创建/完成、产物查看。
- 预期结果：原有流程仍可使用；自动整理不改变业务结果或阻断操作。

### CHK-033: Phase Boundary

- 关联需求点：Phase 6/7 不属于本期。
- 验证方法：检查 UI、API 和行为。
- 预期结果：不要求完整 AI context query/onboarding API；不要求完整 confirmation queue 治理 UI、批量确认、升级处理；如有入口应标记为后续阶段或轻量占位。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-20T15:20:07+08:00
- 用户确认摘要：用户回复 `continue`，确认 Archive Room Phase 5 checklist 可以进入 todolist 生成。确认范围包含项目长期维护属性、事件触发整理、启动/每日补漏巡检、重要聊天整理、pending confirmation 分级、维护记录可见性、Phase 1-4 回归和 Phase 6/7 边界。

## 实现与自测记录

- 记录时间：2026-06-20T16:26:41+08:00
- 实现摘要：已完成项目长期维护属性、维护开关 API 与档案室详情展示；统一自动整理触发模型；任务完成/阻塞、项目状态变化、会议结论、重要消息等高价值事件整理；维护关闭时低价值事件跳过但高价值事件保留；启动/每日巡检；维护记录、来源引用、pending confirmation 基础路由；Phase 4 档案管理员暂停状态对自动整理生效。
- 自动化覆盖：`tests/test_archive_room_phase_5.py` 覆盖 CHK-001、CHK-002、CHK-004、CHK-005、CHK-009、CHK-012、CHK-013、CHK-014、CHK-016、CHK-017、CHK-018、CHK-020、CHK-024、CHK-025、CHK-027、CHK-030 的核心路径。
- 回归覆盖：已运行 Phase 1-4 档案室回归、会议相关回归、项目执行回归、后端编译检查和前端 JS 语法检查。
- Live smoke：已用 `./start.sh` 启动的本地服务验证维护项目每日巡检与重要消息入档；临时项目 `fb6db40e-4c32-4e62-9609-e62a5406d17b` 开启维护后 `checkedProjectCount=1`，项目存在 `lastDailyInspectionAt`，重要消息生成 `important_message` 条目。
- 真实数据 MCP/P2P 验证：已基于真实项目 `7692ca8b-2d88-44cf-9dbb-765f2e4eb855`（金融分析项目）开启长期维护并触发每日巡检与重要消息入档；项目详情显示 `archiveMaintenance.enabled=true`、`lastDailyInspectionAt=2026-06-20T08:33:27.926053+00:00`、`important_message` 条目和可追溯 chat source。
- P2P 通信验证：通过 `/api/agent-platform-communications/send` 从 `codex-local` 向 `archive-manager` 发送 `codex__archive-manager__phase5-real-data-mcp`，history 中存在 request/reply；档案管理员返回稳定 JSON，声明 `available=true`、`usable_for_archive_maintenance=true`、`ordinary_project_task_execution=false`。该回复约 31 秒落库，客户端 30 秒同步等待会超时，验收时应以 history 查询作为异步确认补充。
- 边界说明：完整 AI 上下文查询/onboarding API 仍归 Phase 6；完整 confirmation queue 治理 UI、批量确认、升级处理仍归 Phase 7。本期只保留 Phase 5 需要的 pending confirmation 数据与轻量可见性。

## 验收通过记录

- 确认项：tested + done
- 确认时间：2026-06-20T16:49:40+08:00
- 用户确认摘要：用户回复 `phase5应该没什么问题了，验收通过`，确认 Archive Room Phase 5 已通过验收并可归档为完成。
