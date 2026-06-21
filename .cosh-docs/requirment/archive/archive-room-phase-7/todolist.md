# Archive Room Phase 7 Todolist

## TODO-001: Audit Existing Archive Data And API Shape

- 目标：确认当前档案数据结构、项目详情 API、AI context API 和维护事件中已有的 pending、confirmed、source、confidence 字段。
- 涉及区域：archive room backend, archive data persistence, project context API, existing tests.
- 输入：Phase 1-6 已实现代码、`requirement.md`、`review.md`、`checklist.md`。
- 输出：实现前的字段映射结论，明确哪些字段复用、哪些字段新增。
- 依赖：无。
- 完成标准：能列出 pending confirmations、archive entries、processed history、source references 和 context package 的实际读写路径；后续任务不需要重新猜测数据入口。
- 关联 checklist：CHK-006, CHK-007, CHK-028, CHK-031, CHK-033。

## TODO-002: Define Governance State And Authority Schema

- 目标：为档案治理建立稳定状态和 authority 表示。
- 涉及区域：archive data model, serialization/deserialization, fixture data.
- 输入：`system_confirmed` / `source_confirmed`、`archive_manager_confirmed`、`human_confirmed`、`pending_human_confirmation`、`deferred`、`rejected` 产品定义。
- 输出：统一字段结构，包含 status/authority、actor、timestamp、optional reason、sources、confidence、impact area、original suggestion、edited value。
- 依赖：TODO-001。
- 完成标准：所有新增/迁移数据都能表达 source/system 客观确认、档案管理员确认、人工确认、暂缓、拒绝和待人工确认；旧数据能兼容显示。
- 关联 checklist：CHK-003, CHK-010, CHK-011, CHK-012, CHK-013, CHK-014, CHK-035, CHK-036, CHK-038。

## TODO-003: Implement Pending Queue Eligibility And Priority Rules

- 目标：控制哪些内容进入人工待确认队列，并按治理优先级排序。
- 涉及区域：archive manager processing, pending confirmation generation, project archive summary/index.
- 输入：长期规则、高影响建议、confirmed 冲突、普通低影响推断、deferred 排序规则。
- 输出：pending queue eligibility 和 sorting 实现。
- 依赖：TODO-002。
- 完成标准：长期规则、高影响建议、与 confirmed 尤其 human_confirmed 冲突的内容进入 `pending_human_confirmation`；普通低影响内容不淹没主队列；排序满足严重冲突、高影响、长期规则、普通待确认、暂缓。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-009, CHK-016, CHK-026, CHK-027, CHK-037。

## TODO-004: Implement Source/System Auto-Confirmation For Objective Facts

- 目标：让客观来源事实可以自动入档，不进入人工待确认队列。
- 涉及区域：task/project/meeting/artifact event ingestion, archive entries, source mapping.
- 输入：任务完成、产物生成、会议结束、项目状态变化、产物路径和来源映射事件。
- 输出：`system_confirmed` / `source_confirmed` archive entries。
- 依赖：TODO-002。
- 完成标准：客观事件入档时保留来源和时间；不会进入主人工队列；UI/API 能识别 authority。
- 关联 checklist：CHK-004, CHK-007, CHK-029, CHK-035, CHK-037, CHK-038。

## TODO-005: Implement Archive Manager Confirmation Judgment

- 目标：由档案室管理员判断 AI 处理内容是否可作为低风险来源支持内容入档。
- 涉及区域：archive manager prompt/config, archive manager processing pipeline, archive persistence.
- 输入：会议摘要、任务结果摘要、重要消息分类、产物描述、普通业务 AI 产出的建议和来源。
- 输出：`archive_manager_confirmed` entries 或 `pending_human_confirmation` items。
- 依赖：TODO-002, TODO-003。
- 完成标准：普通业务 AI 不能直接写入 `archive_manager_confirmed` 或 `human_confirmed`；档案管理员判断后才能标记 `archive_manager_confirmed`；不满足低风险条件的内容进入人工队列或保持普通 entry。
- 关联 checklist：CHK-004, CHK-036, CHK-037, CHK-038, CHK-040。

## TODO-006: Implement Governance Action APIs

- 目标：提供项目级 confirm/reject/defer/edit-confirm 能力。
- 涉及区域：backend API, archive persistence, action validation, error handling.
- 输入：pending item id、action、optional reason、edited content。
- 输出：状态转换、confirmed entry/rule、processed history、action record。
- 依赖：TODO-002, TODO-003。
- 完成标准：confirm/reject/defer/edit-confirm 可用；重复点击或请求重试不会产生重复 confirmed entry 或损坏状态；原因可选。
- 关联 checklist：CHK-010, CHK-011, CHK-012, CHK-013, CHK-014, CHK-015, CHK-020, CHK-033, CHK-034。

## TODO-007: Implement Human-Confirmed Protection And Conflict Handling

- 目标：保护 `human_confirmed` 内容不被 AI 自动覆盖，并把冲突转成治理项。
- 涉及区域：archive manager update logic, conflict detection, pending item detail model.
- 输入：已确认规则/事实、新建议、新来源、冲突摘要。
- 输出：conflict pending item，包含 summary-first 解释、双方内容和双方来源。
- 依赖：TODO-002, TODO-003, TODO-006。
- 完成标准：human_confirmed 内容不会被自动覆盖；冲突建议进入 pending/conflict；详情先展示人可读冲突摘要，再展示双方内容和来源。
- 关联 checklist：CHK-003, CHK-008, CHK-016, CHK-027。

## TODO-008: Build Project Detail Governance UI

- 目标：在档案室项目详情页提供可操作的待确认治理区域。
- 涉及区域：Archive Room frontend project detail, pending card/list components, action dialogs/forms.
- 输入：pending confirmations API、governance action APIs、processed history。
- 输出：待确认区域、pending item 卡片、操作按钮、可选理由、编辑后确认流程、冲突详情。
- 依赖：TODO-006, TODO-007。
- 完成标准：用户能在项目详情页查看建议内容、置信度、影响范围、原因、来源、创建时间、状态、冲突摘要，并完成确认/拒绝/暂缓/编辑确认。
- 关联 checklist：CHK-005, CHK-006, CHK-007, CHK-008, CHK-010, CHK-011, CHK-012, CHK-013, CHK-014。

## TODO-009: Build Processed History And Deferred Presentation

- 目标：让已处理项和暂缓项可追溯但不干扰主治理流程。
- 涉及区域：Archive Room project detail UI, processed history API/data, sorting/collapse behavior.
- 输入：confirmed/rejected/deferred action records。
- 输出：轻量 processed history 入口、deferred 排后或默认折叠表现。
- 依赖：TODO-006, TODO-008。
- 完成标准：已确认/已拒绝/已暂缓历史可查看，包含状态、操作者、时间、可选理由和来源摘要；历史不淹没主待确认区。
- 关联 checklist：CHK-009, CHK-020, CHK-021, CHK-034。

## TODO-010: Update Archive Room Overview Discovery

- 目标：让用户在总览页快速发现有治理工作的项目。
- 涉及区域：Archive Room overview list, filters, sorting, project cards/counts.
- 输入：项目 pending/risk/conflict counts、recent update time。
- 输出：pending/risk 优先展示、pending filter、risk filter、recent update sorting。
- 依赖：TODO-003。
- 完成标准：总览页默认优先展示 pending/risk 项目；可过滤只看 pending 或 risk；最近更新排序不破坏默认优先能力。
- 关联 checklist：CHK-022, CHK-023, CHK-024, CHK-025。

## TODO-011: Update Archive Index And AI Context Authority Rendering

- 目标：让档案索引、上下文目录和 AI 入场包正确表达治理状态与 authority。
- 涉及区域：archive index UI/API, project context API, AI onboarding/context package generation.
- 输入：governance schema、confirmed/pending/deferred/rejected entries、authority labels。
- 输出：UI/API 中可识别的 authority/status；AI context 按可信度分层。
- 依赖：TODO-002, TODO-004, TODO-005, TODO-006, TODO-007。
- 完成标准：human_confirmed 作为最高可信指导；source/system-confirmed 作为可信客观状态；archive_manager_confirmed 作为来源支持上下文；pending/deferred 标注低可信或未确认；rejected 不作为 active guidance。
- 关联 checklist：CHK-017, CHK-018, CHK-019, CHK-026, CHK-028, CHK-031, CHK-038, CHK-039。

## TODO-012: Preserve Regression Surfaces And Degraded Mode

- 目标：确保 Phase 7 不破坏 Phase 1-6 已验收能力，并处理档案管理员不可用场景。
- 涉及区域：artifact browsing, archive manager status/maintenance, archive room degraded state, existing regression tests.
- 输入：已有真实/fixture 项目、档案管理员可用/不可用状态。
- 输出：兼容性处理和必要回归修复。
- 依赖：TODO-004, TODO-005, TODO-008, TODO-011。
- 完成标准：档案索引仍可见；产物弹窗、来源/路径视图、图片/视频/音频预览仍可用；管理员状态、暂停/恢复、维护记录和事件整理继续可用；管理员不可用时已存在治理数据仍可查看。
- 关联 checklist：CHK-028, CHK-029, CHK-030, CHK-032。

## TODO-013: Add Persistence, API, And Unit Tests

- 目标：覆盖治理状态持久化、API 状态转换、authority schema 和 AI context 输出。
- 涉及区域：backend tests, data fixtures, API tests.
- 输入：新增 schema、governance APIs、context API、archive manager processing。
- 输出：自动化测试。
- 依赖：TODO-002, TODO-006, TODO-011。
- 完成标准：测试覆盖确认/拒绝/暂缓/编辑确认、重复请求、重启后状态保留、authority labels、ordinary business AI cannot self-confirm、rejected 不进入 active guidance。
- 关联 checklist：CHK-010, CHK-011, CHK-012, CHK-013, CHK-015, CHK-018, CHK-019, CHK-033, CHK-035, CHK-036, CHK-038, CHK-039, CHK-040。

## TODO-014: Add UI And End-To-End Verification With Realistic Data

- 目标：使用真实结构数据验证 Phase 7 主要用户流程和回归能力。
- 涉及区域：frontend tests, chrome/manual acceptance, seeded project data.
- 输入：包含客观事件、archive-manager-confirmed 摘要、human pending 项、conflict、deferred、rejected、产物的测试项目。
- 输出：UI 验收记录、截图/日志摘要、必要修复。
- 依赖：TODO-008, TODO-009, TODO-010, TODO-011, TODO-012。
- 完成标准：能在浏览器中完成项目发现、查看 pending、确认/拒绝/暂缓/编辑确认、查看 processed history、查看 authority 标签、验证 artifact browsing 和 AI context 输出。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-020, CHK-021, CHK-022, CHK-023, CHK-024, CHK-025, CHK-029, CHK-034, CHK-038。

## TODO-015: Update Requirement Artifacts After Implementation And Testing

- 目标：把开发结果、测试结果和剩余风险回填到需求归档。
- 涉及区域：`.cosh-docs/requirment/archive-room-phase-7/`, delivery notes.
- 输入：实现 diff、测试命令、UI 验收结果、未覆盖风险。
- 输出：更新后的 checklist 测试记录、状态推进记录、交付摘要。
- 依赖：TODO-013, TODO-014。
- 完成标准：每个 checklist 项都有对应验证说明或残余风险；`status.json` 能反映实现/测试阶段；等待用户验收后再进入 tested/done。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012, CHK-013, CHK-014, CHK-015, CHK-016, CHK-017, CHK-018, CHK-019, CHK-020, CHK-021, CHK-022, CHK-023, CHK-024, CHK-025, CHK-026, CHK-027, CHK-028, CHK-029, CHK-030, CHK-031, CHK-032, CHK-033, CHK-034, CHK-035, CHK-036, CHK-037, CHK-038, CHK-039, CHK-040。
