# 项目定时任务 Todolist

## Phase 1：扩展现有 Cron 支持项目绑定

### TODO-001 梳理现有 Cron 存储、RPC 和运行状态字段

- 目标：确认现有 cron job 的保存位置、字段结构、`cron.add/list/update/remove/run` 行为和 last/next run 状态来源。
- 涉及区域：`app/cron.html`、`app/server.py`、现有 cron RPC/网关相关代码、cron 存储文件或 provider。
- 输入：现有 Cron Manager 代码、现有 cron 测试、当前 checklist。
- 输出：实现前的字段映射结论，明确哪些字段复用、哪些字段新增。
- 依赖：无。
- 完成标准：能明确回答项目绑定字段应加在 cron job 顶层、payload 里还是 metadata/scope 字段里，并确认不会破坏普通 Agent cron。
- 关联 checklist：CHK-001、CHK-002、CHK-006。

### TODO-002 扩展 cron job 元数据以支持项目绑定

- 目标：让现有 cron job 能保存 `projectId`、`targetType`、可选 `taskId`，并区分普通 Agent cron 与项目定时任务。
- 涉及区域：cron job 创建、更新、列表、序列化、反序列化逻辑。
- 输入：TODO-001 字段映射结论。
- 输出：项目绑定 cron job 的持久化字段和兼容读取逻辑。
- 依赖：TODO-001。
- 完成标准：带项目绑定的 cron job 可创建、查询、更新、启停、删除；不带项目字段的旧 cron job 正常读取。
- 关联 checklist：CHK-001、CHK-002、CHK-006。

### TODO-003 增加项目绑定 cron 的项目资格校验

- 目标：创建或更新带 `projectId` 的 cron job 时，校验项目存在且有负责人或绑定 Agent。
- 涉及区域：项目读取逻辑、cron add/update 校验逻辑、错误响应。
- 输入：现有项目数据模型、项目负责人或绑定 Agent 字段。
- 输出：项目资格校验和清晰错误信息。
- 依赖：TODO-002。
- 完成标准：不满足条件的项目无法保存项目绑定 cron，且不会留下半成品记录。
- 关联 checklist：CHK-003。

### TODO-004 复用现有 Cron schedule 校验并覆盖项目绑定 cron

- 目标：确保项目绑定 cron 和普通 Agent cron 使用一致的 cron、循环间隔、一次性时间校验。
- 涉及区域：cron schedule parser/validator、cron add/update。
- 输入：现有 schedule 结构和校验逻辑。
- 输出：项目绑定 cron 的 schedule 校验路径。
- 依赖：TODO-002。
- 完成标准：三类 schedule 的合法和非法输入都有一致行为。
- 关联 checklist：CHK-004。

### TODO-005 增加项目目标校验

- 目标：校验 `targetType=projectWorkflow` 和 `targetType=projectTask` 的项目目标元数据。
- 涉及区域：cron add/update、项目任务读取逻辑。
- 输入：项目任务列表、`projectId`、`targetType`、`taskId`。
- 输出：目标校验逻辑和错误响应。
- 依赖：TODO-002、TODO-003。
- 完成标准：整个项目目标合法；当前项目内任务合法；不存在任务或其他项目任务被拒绝。
- 关联 checklist：CHK-005。

### TODO-006 为 Phase 1 增加后端回归测试

- 目标：覆盖项目绑定 cron 的持久化、校验和普通 Agent cron 兼容性。
- 涉及区域：`tests/` 下 cron 或 server 相关测试。
- 输入：TODO-002 至 TODO-005 的行为。
- 输出：自动化测试。
- 依赖：TODO-002、TODO-003、TODO-004、TODO-005。
- 完成标准：测试覆盖 CHK-001 至 CHK-006，且现有 cron 测试仍通过。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006。

## Phase 2：项目详情页配置体验与全局定时任务总览

### TODO-007 设计项目详情页的定时任务数据加载和 API 调用封装

- 目标：让项目页可以读取、创建、更新、删除、启停项目绑定 cron。
- 涉及区域：`app/projects.js` API 封装、项目详情渲染数据模型。
- 输入：Phase 1 后端能力。
- 输出：项目页使用的 scheduled task API 方法。
- 依赖：TODO-006。
- 完成标准：项目页可以拿到当前项目的项目绑定 cron 列表，普通 Agent cron 不混入项目列表。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-010。

### TODO-008 实现项目详情页定时任务列表和空状态

- 目标：在项目详情页展示项目定时任务列表、状态、目标、schedule、last/next run。
- 涉及区域：`app/projects.js`、`app/projects.css`、中英文 locale。
- 输入：TODO-007 API 数据。
- 输出：项目定时任务列表 UI。
- 依赖：TODO-007。
- 完成标准：满足条件项目能看到列表或空状态；不满足条件项目不展示创建入口或展示原因。
- 关联 checklist：CHK-007、CHK-012、CHK-027。

### TODO-009 实现项目定时任务创建和编辑表单

- 目标：项目负责人可以配置 schedule、目标类型、目标任务、启用状态和必要说明。
- 涉及区域：`app/projects.js`、`app/projects.css`、locale。
- 输入：项目任务列表、Phase 1 校验规则。
- 输出：创建/编辑弹窗或内联表单。
- 依赖：TODO-008。
- 完成标准：可创建整个项目 workflow 定时任务和指定任务定时任务；指定任务只允许当前项目任务。
- 关联 checklist：CHK-008、CHK-009、CHK-012、CHK-027。

### TODO-010 实现项目页定时任务管理操作

- 目标：支持编辑、启用/禁用、删除、立即运行入口。
- 涉及区域：`app/projects.js`、后端 run/update/delete 调用。
- 输入：TODO-009 表单和 Phase 1 后端能力。
- 输出：管理操作按钮和状态刷新逻辑。
- 依赖：TODO-009。
- 完成标准：每个操作后 UI 和后端数据一致，错误时有明确提示。
- 关联 checklist：CHK-010。

### TODO-011 实现项目级暂停/恢复配置入口

- 目标：项目负责人可以暂停或恢复某个项目下全部定时任务。
- 涉及区域：项目 metadata、项目更新接口、项目详情 UI。
- 输入：项目状态和定时任务列表。
- 输出：项目级暂停/恢复状态和 UI 控制。
- 依赖：TODO-008。
- 完成标准：暂停状态清晰可见，恢复后保留原有任务配置。
- 关联 checklist：CHK-011。

### TODO-012 为 Phase 2 增加 UI 和 API 回归测试

- 目标：覆盖项目页展示、表单、管理操作、暂停/恢复、全局定时任务页总览和文案边界。
- 涉及区域：前端测试、server/API 测试、locale 测试。
- 输入：TODO-007 至 TODO-011，以及 TODO-032 至 TODO-034。
- 输出：自动化或可重复的手动测试脚本。
- 依赖：TODO-007、TODO-008、TODO-009、TODO-010、TODO-011、TODO-032、TODO-033、TODO-034。
- 完成标准：覆盖 CHK-007 至 CHK-012、CHK-031 至 CHK-033，且 locale 检查通过。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-010、CHK-011、CHK-012、CHK-027、CHK-031、CHK-032、CHK-033。

### TODO-032 扩展全局定时任务页的数据加载

- 目标：让 `/cron.html` 同时加载普通 Agent cron 和项目绑定 cron。
- 涉及区域：`app/cron.html`、项目 scheduled-cron API、项目列表 API。
- 输入：Phase 1 后端项目绑定 cron 能力。
- 输出：全局定时任务页可识别项目绑定 cron 的数据模型。
- 依赖：TODO-006。
- 完成标准：全局页能显示项目绑定 cron，不破坏普通 Agent cron 列表。
- 关联 checklist：CHK-031。

### TODO-033 在全局定时任务页展示项目上下文

- 目标：项目绑定 cron 在 `/cron.html` 中显示项目名、目标类型、目标任务，并提供跳转或定位入口。
- 涉及区域：`app/cron.html`、项目数据查询、locale。
- 输入：TODO-032 数据模型。
- 输出：项目 cron 的列表展示、详情展示和项目定位入口。
- 依赖：TODO-032。
- 完成标准：用户能在全局页看出哪些定时任务属于哪个项目，以及作用于整个项目还是具体任务。
- 关联 checklist：CHK-032。

### TODO-034 增加全局定时任务页类型/项目过滤

- 目标：支持在 `/cron.html` 按普通 Agent cron、项目 cron、指定项目筛选。
- 涉及区域：`app/cron.html` 过滤控件和列表渲染。
- 输入：TODO-032、TODO-033。
- 输出：类型过滤和项目过滤。
- 依赖：TODO-033。
- 完成标准：过滤准确，原有 Agent 过滤能力不退化。
- 关联 checklist：CHK-033。

## Phase 3：调度派发与项目执行绑定

### TODO-013 梳理现有 cron 到期执行入口

- 目标：找到 cron job 到期后实际执行 payload 的入口，确定项目绑定 cron 的派发插入点。
- 涉及区域：cron runtime、WebSocket gateway、server cron handling。
- 输入：Phase 1 项目绑定字段。
- 输出：派发设计结论，明确项目绑定 cron 如何从普通 Agent prompt 路径分流。
- 依赖：TODO-006。
- 完成标准：明确项目绑定 cron 到期时不会走普通 prompt，而是走项目派发路径。
- 关联 checklist：CHK-013、CHK-014、CHK-015、CHK-018。

### TODO-014 实现 whole-project 目标派发到项目 workflow

- 目标：到期的 `targetType=projectWorkflow` cron 在项目空闲时启动项目 workflow。
- 涉及区域：cron runtime、项目 workflow start 逻辑、workflow active 状态检查。
- 输入：TODO-013 派发入口、现有 workflow start 能力。
- 输出：项目 workflow 派发逻辑。
- 依赖：TODO-013。
- 完成标准：空闲项目可被定时任务启动 workflow。
- 关联 checklist：CHK-013。

### TODO-015 实现 workflow 已运行时的跳过逻辑

- 目标：避免同一个项目被定时任务重复启动 workflow。
- 涉及区域：cron runtime、workflow status、run state 更新。
- 输入：TODO-014。
- 输出：active workflow skip 逻辑和 skip reason。
- 依赖：TODO-014。
- 完成标准：workflow 已运行时不重复启动，运行状态记录为 skipped。
- 关联 checklist：CHK-014。

### TODO-016 实现 specific-task 目标派发到项目任务执行

- 目标：到期的 `targetType=projectTask` cron 启动对应项目任务。
- 涉及区域：cron runtime、项目任务执行 start 逻辑。
- 输入：TODO-013 派发入口、现有 task execution 能力。
- 输出：指定任务派发逻辑。
- 依赖：TODO-013。
- 完成标准：指定项目任务进入预期执行流程，运行记录关联任务。
- 关联 checklist：CHK-015。

### TODO-017 实现暂停、删除、归档、缺失目标的派发保护

- 目标：调度器在不应执行时拒绝派发，且不崩溃。
- 涉及区域：cron runtime、项目状态校验、任务存在性校验。
- 输入：项目暂停状态、项目状态、任务状态。
- 输出：派发前保护逻辑。
- 依赖：TODO-014、TODO-016。
- 完成标准：暂停、删除、归档、缺失、不满足条件场景均不会启动执行。
- 关联 checklist：CHK-016、CHK-017。

### TODO-018 更新项目绑定 cron 的 last/next run 状态

- 目标：调度决策后正确维护运行时间和状态。
- 涉及区域：cron state update、project-bound metadata。
- 输入：started、skipped、failed 等派发结果。
- 输出：`lastRunAt`、`lastStatus`、`nextRunAt` 更新逻辑。
- 依赖：TODO-014、TODO-015、TODO-016、TODO-017。
- 完成标准：cron、循环、一次性、跳过、失败场景的 last/next run 都准确。
- 关联 checklist：CHK-018。

### TODO-019 为 Phase 3 增加调度派发测试

- 目标：覆盖 whole-project、specific-task、active skip、paused、invalid target、last/next run。
- 涉及区域：后端测试、可控时间测试。
- 输入：TODO-014 至 TODO-018。
- 输出：自动化测试。
- 依赖：TODO-014、TODO-015、TODO-016、TODO-017、TODO-018。
- 完成标准：覆盖 CHK-013 至 CHK-018。
- 关联 checklist：CHK-013、CHK-014、CHK-015、CHK-016、CHK-017、CHK-018。

## Phase 4：执行历史与控制面板异常提示

### TODO-020 设计并保存项目定时执行历史记录

- 目标：把项目绑定 cron 的运行决策沉淀到项目详情可读历史中。
- 涉及区域：项目存储、cron runtime、项目详情数据接口。
- 输入：Phase 3 派发结果。
- 输出：项目定时执行历史记录结构和写入逻辑。
- 依赖：TODO-019。
- 完成标准：started、skipped、failed、completed、intervention_required 等状态可以被保存和读取。
- 关联 checklist：CHK-019。

### TODO-021 在项目详情页展示定时执行历史

- 目标：用户可以在项目页看到每次定时执行发生了什么。
- 涉及区域：`app/projects.js`、`app/projects.css`、locale。
- 输入：TODO-020 历史数据。
- 输出：执行历史 UI。
- 依赖：TODO-020。
- 完成标准：展示时间、定时任务名称、目标、状态和原因/错误。
- 关联 checklist：CHK-019、CHK-023、CHK-027。

### TODO-022 控制面板只提示失败和人工介入

- 目标：把 abnormal scheduled execution 接入控制面板，同时避免正常运行提示噪音。
- 涉及区域：控制面板数据源、项目异常状态、前端提示区域。
- 输入：TODO-020 历史状态。
- 输出：失败/人工介入提示逻辑。
- 依赖：TODO-020。
- 完成标准：成功、完成、正常跳过不提示；失败和人工介入提示可见且可定位到项目。
- 关联 checklist：CHK-020、CHK-021、CHK-022。

### TODO-023 控制定时执行历史的展示规模

- 目标：长期项目大量执行记录下仍保持项目页可用。
- 涉及区域：历史查询、UI 展示、截断/分页/过滤策略。
- 输入：TODO-020 历史记录。
- 输出：有界历史展示方案。
- 依赖：TODO-021。
- 完成标准：超过展示上限时 UI 仍响应正常，排序和截断规则清楚。
- 关联 checklist：CHK-023。

### TODO-024 增加调度诊断日志

- 目标：为 due、skipped、failed、paused 等调度决策提供可排查日志。
- 涉及区域：cron runtime、server logging。
- 输入：Phase 3 派发路径和 Phase 4 历史状态。
- 输出：简洁诊断日志。
- 依赖：TODO-020。
- 完成标准：日志包含项目、定时任务、目标类型、决策和错误原因，不输出无关敏感信息。
- 关联 checklist：CHK-024。

### TODO-025 为 Phase 4 增加历史和提示测试

- 目标：覆盖项目历史、控制面板异常提示、正常运行不提示和历史规模。
- 涉及区域：后端测试、前端测试、手动验收脚本。
- 输入：TODO-020 至 TODO-024。
- 输出：自动化测试或稳定手动验证步骤。
- 依赖：TODO-020、TODO-021、TODO-022、TODO-023、TODO-024。
- 完成标准：覆盖 CHK-019 至 CHK-024。
- 关联 checklist：CHK-019、CHK-020、CHK-021、CHK-022、CHK-023、CHK-024。

## Phase 5：长期项目推荐、体验打磨和回归加固

### TODO-026 实现长期项目推荐创建定时任务

- 目标：长期项目创建或标记后，推荐用户创建项目定时任务，但不自动启用。
- 涉及区域：项目创建/编辑流程、项目模板或项目类型 UI。
- 输入：产品默认策略和项目属性。
- 输出：推荐入口和确认流程。
- 依赖：TODO-012、TODO-019。
- 完成标准：用户确认前不创建启用状态的定时任务。
- 关联 checklist：CHK-025。

### TODO-027 完成旧项目兼容和空状态处理

- 目标：没有任何定时任务字段的旧项目可以正常加载和使用。
- 涉及区域：项目读取、项目详情 UI、迁移兼容逻辑。
- 输入：现有项目数据。
- 输出：兼容读取和空状态。
- 依赖：TODO-020。
- 完成标准：旧项目无报错，定时任务区域显示合理空状态。
- 关联 checklist：CHK-026。

### TODO-028 补全中英文本地化

- 目标：所有新增 UI 文案、状态、错误和提示都有中英文。
- 涉及区域：`app/locales/zh.json`、`app/locales/en.json`、前端调用。
- 输入：Phase 2 至 Phase 5 新增文案。
- 输出：完整 locale key。
- 依赖：TODO-009、TODO-021、TODO-022、TODO-026。
- 完成标准：locale 完整性检查通过，人工检查中英文 UI 无缺词。
- 关联 checklist：CHK-027。

### TODO-029 执行项目 workflow 和项目执行回归测试

- 目标：确认项目定时任务没有破坏现有项目 workflow 和项目执行。
- 涉及区域：`tests/test_workflow_e2e.py`、`tests/test_project_execution.py` 或相关测试。
- 输入：全部核心实现。
- 输出：回归测试结果和必要修复。
- 依赖：TODO-019、TODO-025。
- 完成标准：现有项目 workflow/执行测试通过，新增测试通过。
- 关联 checklist：CHK-028。

### TODO-030 执行 Agent 级 Cron Manager 回归测试

- 目标：确认项目绑定扩展没有破坏普通 Agent cron。
- 涉及区域：`app/cron.html`、cron RPC、cron route contract tests。
- 输入：Phase 1 至 Phase 4 实现。
- 输出：Cron Manager 回归测试结果和必要修复。
- 依赖：TODO-006、TODO-019。
- 完成标准：普通 Agent cron 可以创建、查询、运行、编辑、删除。
- 关联 checklist：CHK-029。

### TODO-031 完成端到端人工验收脚本

- 目标：用一个完整场景验收 5 个 phase 的串联体验。
- 涉及区域：项目创建、项目详情页、cron 调度、项目执行、历史、控制面板。
- 输入：所有实现和测试结果。
- 输出：端到端人工验收步骤和结果记录。
- 依赖：TODO-026、TODO-027、TODO-028、TODO-029、TODO-030。
- 完成标准：能创建满足条件的长期项目，接受推荐，创建两类定时任务，触发执行，暂停/恢复，检查历史和异常提示。
- 关联 checklist：CHK-030。

## 父需求完成记录

- 2026-06-20T07:52:08+08:00：父需求拆分出的 Phase 1、Phase 2-3、Phase 4、Phase 5 均已独立完成并归档。
- 2026-06-20T07:52:08+08:00：补充修正“任务级允许没有 Reviewer 时跳过独立审查”已完成并通过用户验收。
- 2026-06-20T07:52:08+08:00：用户确认 project-scheduled-tasks 父需求可以归档，父需求闭环完成。
