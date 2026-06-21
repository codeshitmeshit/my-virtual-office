# Archive Room Phase 8 Todolist

## TODO-001: Inspect Existing Archive Maintenance Model

- 目标：确认 Phase5-7 已有 archive record、maintenance、pending confirmation、authority 和 trigger flow 的当前结构。
- 涉及区域：`app/server.py`, `app/archive-room.js`, `app/archive-room.css`, existing archive-room tests.
- 输入：Phase8 requirement/review/checklist, existing Phase5-7 code.
- 输出：实现前确认现有字段、触发入口和可复用 helper。
- 依赖：无。
- 完成标准：明确 schedule state、maintenance records、governance entries 应挂载到哪个现有结构；不引入重复存储模型。
- 关联 checklist：CHK-001 至 CHK-033。

## TODO-002: Add Per-Project Maintenance Schedule State

- 目标：为每个项目档案增加长期维护频率配置和运行时间状态。
- 涉及区域：archive-room project record helpers in `app/server.py`.
- 输入：项目 archive record, maintenance state.
- 输出：持久化字段，包括 frequency/mode、next scheduled time、last scheduled time、last event-triggered time、last skipped reason。
- 依赖：TODO-001。
- 完成标准：默认值为事件触发 + 每日巡检；刷新和重启后配置仍保留；关闭长期维护不删除配置。
- 关联 checklist：CHK-001, CHK-003, CHK-004, CHK-005, CHK-006。

## TODO-003: Add Frequency Control API

- 目标：提供项目级频率查询和更新能力。
- 涉及区域：`app/server.py` Archive Room API routing.
- 输入：项目 id, requested schedule mode.
- 输出：可更新 event-only/daily/weekly/custom-if-supported 的 API response，并返回最新项目 archive detail。
- 依赖：TODO-002。
- 完成标准：非法 mode 返回清晰错误；成功更新后前端可立即展示新配置；维护关闭时配置仍可读但前端灰置。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004。

## TODO-004: Implement Scheduled Maintenance Decision Logic

- 目标：根据项目频率决定是否执行计划整理。
- 涉及区域：startup/daily inspection helpers, archive manager maintenance helpers in `app/server.py`.
- 输入：schedule mode, now, last scheduled run, manager paused state, project maintenance state.
- 输出：run/skip decision and reason。
- 依赖：TODO-002。
- 完成标准：daily/weekly/event-only 按预期运行或跳过；暂停管理员和关闭长期维护记录 skip reason。
- 关联 checklist：CHK-007, CHK-008, CHK-009, CHK-011, CHK-012。

## TODO-005: Preserve Event-Triggered Maintenance Independence

- 目标：保证事件触发整理不被计划频率阻塞，并单独记录 last event-triggered time。
- 涉及区域：task completion, meeting, important message, artifact/blocker/conflict event archive triggers.
- 输入：现有 event-triggered整理 flow。
- 输出：事件触发记录独立更新，和 scheduled fields 区分。
- 依赖：TODO-002, TODO-004。
- 完成标准：任意频率配置下重要事件仍可触发整理；last event-triggered 和 last scheduled 不互相污染。
- 关联 checklist：CHK-006, CHK-010。

## TODO-006: Add Duplicate/Cooldown Protection

- 目标：避免启动、计划和事件触发靠近时重复整理同类内容。
- 涉及区域：archive maintenance trigger helpers and event dedupe state.
- 输入：trigger type, source event key, recent maintenance history.
- 输出：deduped/skip decision and clear record.
- 依赖：TODO-004, TODO-005。
- 完成标准：短时间同类重复触发不会刷出大量重复档案和维护记录；用户能看到去重或跳过原因。
- 关联 checklist：CHK-013。

## TODO-007: Add Archive-Manager-First Governance Classification

- 目标：让档案管理员先分类冲突和变更，再决定自动处理或升级人工。
- 涉及区域：archive manager governance helpers in `app/server.py`.
- 输入：new archive entry, existing active/stale entries, authority/status/source metadata.
- 输出：classification: wording drift, stale old context, stronger new source, true owner decision, high-trust conflict。
- 依赖：TODO-001。
- 完成标准：分类结果记录在治理/维护历史中，可用于 UI 和 AI context。
- 关联 checklist：CHK-014 至 CHK-020, CHK-023, CHK-025。

## TODO-008: Auto-Confirm Low-Risk Source-Backed Content

- 目标：低风险、来源明确内容由档案管理员自动确认，不进入人工队列。
- 涉及区域：archive entry creation/update logic.
- 输入：task summaries, artifact descriptions, important message classifications, low-risk source-backed content.
- 输出：archive_manager_confirmed 或合适 authority 的 active archive entry。
- 依赖：TODO-007。
- 完成标准：低风险内容不出现在 pending_human_confirmation；保留来源、判断者和时间。
- 关联 checklist：CHK-014, CHK-032。

## TODO-009: Auto-Merge Wording Drift And Mark Stale Content

- 目标：普通表述差异和旧非人工内容由档案管理员自动合并/标记过期。
- 涉及区域：archive entry update/stale relation helpers.
- 输入：new content and existing non-human-confirmed entries.
- 输出：new/merged active entry, old stale entry, replacement relation and reason.
- 依赖：TODO-007。
- 完成标准：旧内容不静默删除；UI/API 可查看 stale 标记和替代关系。
- 关联 checklist：CHK-015, CHK-016, CHK-017, CHK-024, CHK-026, CHK-028。

## TODO-010: Preserve Human-Confirmed Rule Boundary

- 目标：任何替换或反驳 human_confirmed 的内容必须升级人工，不自动覆盖。
- 涉及区域：governance conflict resolution helpers.
- 输入：new suggestion conflicting with human_confirmed entry.
- 输出：pending human item with archive manager judgment, automation insufficiency reason, and required human choice.
- 依赖：TODO-007。
- 完成标准：human_confirmed 保持 active；新建议进入人工队列；pending item 说明清楚。
- 关联 checklist：CHK-018, CHK-020, CHK-025, CHK-027, CHK-029。

## TODO-011: Escalate Unresolvable High-Trust Conflicts

- 目标：两个高可信来源冲突且无法自动裁决时进入人工队列。
- 涉及区域：governance conflict detection and pending confirmation creation.
- 输入：conflicting source/system/archive-manager confirmed entries.
- 输出：pending item with source comparison and decision prompt.
- 依赖：TODO-007。
- 完成标准：pending item 包含双方来源、管理员判断和需要人选择的内容。
- 关联 checklist：CHK-019, CHK-023, CHK-025。

## TODO-012: Add Source Comparison Metadata

- 目标：为自动替换、自动标记过期和人工冲突提供来源对比摘要。
- 涉及区域：archive entry metadata, governance history, context package.
- 输入：old source references, new source references, source type, timestamp, manager judgment.
- 输出：sourceComparison object or equivalent display-ready data.
- 依赖：TODO-007, TODO-009, TODO-011。
- 完成标准：UI/API 可显示旧来源、新来源、来源类型、时间和判断摘要。
- 关联 checklist：CHK-023, CHK-024, CHK-025, CHK-028。

## TODO-013: Update Archive Room Long-Term Maintenance UI

- 目标：在项目详情长期维护区域展示频率、调整入口、计划/事件时间和跳过原因。
- 涉及区域：`app/archive-room.js`, `app/archive-room.css`.
- 输入：project archive maintenance schedule fields.
- 输出：长期维护 UI，包括当前频率、调整按钮、灰置状态、last/next times。
- 依赖：TODO-002, TODO-003。
- 完成标准：UI 不干扰主档案阅读；关闭长期维护时配置灰置保留。
- 关联 checklist：CHK-001 至 CHK-006。

## TODO-014: Add Frequency Adjustment Interaction

- 目标：实现当前频率 + 调整按钮的内部交互。
- 涉及区域：`app/archive-room.js`, `app/archive-room.css`.
- 输入：available frequency modes.
- 输出：可选择 event-only/daily/weekly/custom-if-supported 的 VO 内部控件。
- 依赖：TODO-003, TODO-013。
- 完成标准：保存后 UI 更新并持久化；取消不改变配置；不使用浏览器原生 prompt。
- 关联 checklist：CHK-002, CHK-003, CHK-004。

## TODO-015: Add Automatic Governance Notices

- 目标：在长期维护区域展示最近 3-5 条自动治理轻提示。
- 涉及区域：archive detail API, `app/archive-room.js`, `app/archive-room.css`.
- 输入：automatic governance/maintenance history.
- 输出：recent automatic governance notices.
- 依赖：TODO-008, TODO-009, TODO-012, TODO-013。
- 完成标准：提示不要求用户处理；超过 5 条只显示最近 3-5 条；完整历史仍可查看。
- 关联 checklist：CHK-021, CHK-022。

## TODO-016: Update Stale And Source Comparison Display

- 目标：让 stale 内容和来源对比在档案详情/治理区域可理解。
- 涉及区域：`app/archive-room.js`, `app/archive-room.css`.
- 输入：stale markers, replacement relations, sourceComparison metadata.
- 输出：stale badge, replacement reason, source comparison summary.
- 依赖：TODO-009, TODO-012。
- 完成标准：用户能看懂旧内容为什么被替换或标记过期。
- 关联 checklist：CHK-023, CHK-024。

## TODO-017: Update AI Context Package Trust Behavior

- 目标：AI context 不把 stale/replaced 内容作为 active guidance，并保留可追溯入口。
- 涉及区域：Archive Room context package builder in `app/server.py`.
- 输入：active/stale/replaced/pending entries.
- 输出：current context prioritizes active entries; stale/pending are marked or moved to optional references.
- 依赖：TODO-009, TODO-012。
- 完成标准：stale 不作为当前指导；pending 保持低可信；自动治理可追溯。
- 关联 checklist：CHK-026, CHK-027, CHK-028。

## TODO-018: Add Backend Tests For Scheduling

- 目标：覆盖频率配置、运行/跳过决策、事件独立性和去重。
- 涉及区域：new or updated archive room tests.
- 输入：test fixtures and temporary VO_STATUS_DIR.
- 输出：automated tests for CHK-001 to CHK-013.
- 依赖：TODO-002 至 TODO-006。
- 完成标准：测试覆盖 daily/weekly/event-only、paused/disabled skip、event-triggered independence、dedupe。
- 关联 checklist：CHK-001 至 CHK-013。

## TODO-019: Add Backend Tests For Archive-Manager-First Governance

- 目标：覆盖自动确认、自动合并、stale、human boundary 和 high-trust conflict。
- 涉及区域：new or updated archive room tests.
- 输入：governance fixtures.
- 输出：automated tests for CHK-014 to CHK-028 and CHK-032.
- 依赖：TODO-007 至 TODO-012, TODO-017。
- 完成标准：同一批事件能证明 Phase8 相比 Phase7 人工队列减少。
- 关联 checklist：CHK-014 至 CHK-028, CHK-032。

## TODO-020: Add Frontend And Live Acceptance Checks

- 目标：验证 Archive Room UI 的频率配置、自动治理提示、来源对比、stale 展示和回归流程。
- 涉及区域：Chrome MCP acceptance scripts/manual validation, `app/archive-room.js`, `app/archive-room.css`.
- 输入：real fixture project with schedule and governance scenarios.
- 输出：live verification notes and screenshots if needed.
- 依赖：TODO-013 至 TODO-016。
- 完成标准：使用真实数据和 Chrome MCP 验证关键 UI；主应用流程不破坏。
- 关联 checklist：CHK-001 至 CHK-006, CHK-021 至 CHK-025, CHK-029 至 CHK-033。

## TODO-021: Seed Real Phase8 Acceptance Data

- 目标：提供真实数据项目用于验收。
- 涉及区域：tests/seed fixtures or equivalent helper.
- 输入：Phase8 governance and schedule scenarios.
- 输出：真实 `data/` 下可打开的验收项目。
- 依赖：TODO-002 至 TODO-017。
- 完成标准：项目包含频率配置、自动治理记录、source comparison、stale 内容、仍需人工确认的 owner-level item、产物回归数据。
- 关联 checklist：CHK-001 至 CHK-033。

## TODO-022: Update Documentation And Requirement Records

- 目标：记录 Phase8 实现、测试结果和剩余边界。
- 涉及区域：`.cosh-docs/requirment/archive-room-phase-8/`, parent archive-room notes if needed.
- 输入：implementation/test results.
- 输出：checklist implementation record, status updates.
- 依赖：TODO-018 至 TODO-021。
- 完成标准：测试命令、真实数据项目、Chrome MCP 验收结果和未做范围清楚记录。
- 关联 checklist：CHK-001 至 CHK-033。
