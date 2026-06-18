# Auto Project Workspace Todolist

## 执行说明

- 本 todolist 基于已确认 checklist 生成。
- 每个任务都必须保持可追溯到一个或多个 `CHK-*`。
- 开发完成后必须按 [checklist.md](checklist.md) 执行验证，并记录结果。

## TODO-001 梳理现有项目创建与删除路径

- 目标：确认所有项目创建入口、模板创建入口、更新入口和删除入口的实际代码路径。
- 涉及区域：`app/projects.js`、`app/server.py`、`app/project_store.py`、项目 CRUD 测试。
- 输入：现有创建项目表单、`POST /api/projects`、`POST /api/projects/from-template`、`DELETE /api/projects/{id}`、已确认需求。
- 输出：明确哪些路径需要接入默认可执行项目、自动工作区和删除询问。
- 依赖：无。
- 完成标准：实现前已确认不会遗漏模板创建、API 创建、前端创建和删除路径。
- 关联 checklist：CHK-001、CHK-006、CHK-009、CHK-010、CHK-019。

## TODO-002 定义项目类型与工作区来源字段

- 目标：让系统能表达“可执行项目/普通项目”和“自动工作区/用户工作区”的产品状态。
- 涉及区域：项目数据模型、Markdown project store、API 响应、前端状态。
- 输入：需求中的普通项目开关、自动工作区删除确认、安全边界。
- 输出：项目持久化字段支持工作区来源记录，例如系统创建与用户提供的区分，以及必要的创建时间或元信息。
- 依赖：TODO-001。
- 完成标准：自动创建和手动绑定的项目可在数据层稳定区分；旧项目有兼容默认值。
- 关联 checklist：CHK-011、CHK-015、CHK-018。

## TODO-003 实现自动工作区创建能力

- 目标：当可执行项目没有提供工作区路径时，创建正式项目工作区。
- 涉及区域：`app/server.py` workspace validation/create helper、运行时状态目录或受控项目工作区根。
- 输入：项目标题、创建时间、自动工作区命名规则、现有 workspace 校验规则。
- 输出：创建成功时返回有效路径、workspace kind、workspace status；失败时返回明确错误。
- 依赖：TODO-002。
- 完成标准：工作区名称包含项目名安全化形式和时间戳；失败不会静默降级为普通项目。
- 关联 checklist：CHK-002、CHK-003、CHK-008、CHK-009。

## TODO-004 调整后端项目创建语义

- 目标：让 API 层完整支持默认可执行项目、空路径自动创建、普通项目不创建工作区。
- 涉及区域：`_handle_project_create`、`_handle_project_from_template`、workspace validation/update helper。
- 输入：TODO-002 字段、TODO-003 自动工作区 helper。
- 输出：后端创建接口按项目类型决定是否创建或校验工作区。
- 依赖：TODO-002、TODO-003。
- 完成标准：API 创建可执行项目且空路径会自动创建工作区；手动路径仍校验；普通项目不自动创建。
- 关联 checklist：CHK-002、CHK-005、CHK-009、CHK-010、CHK-019。

## TODO-005 调整前端创建表单

- 目标：把“是否可执行项目”从工作区路径是否为空中解耦。
- 涉及区域：`app/projects.js` 创建/编辑表单、项目类型控件、提交 payload。
- 输入：已确认产品决策：可执行项目默认开启，普通项目通过明确开关可选。
- 输出：创建表单默认选中可执行项目；工作区路径可为空；普通项目可显式选择。
- 依赖：TODO-004。
- 完成标准：用户不填写路径也能提交默认可执行项目；切换普通项目后不会创建工作区或显示 Project Execution 专属入口。
- 关联 checklist：CHK-001、CHK-004、CHK-006、CHK-007。

## TODO-006 展示自动工作区路径和状态

- 目标：让用户创建后能明确看到系统生成的正式工作区。
- 涉及区域：项目看板 toolbar、项目编辑表单、Project Execution 状态显示。
- 输入：项目 API 返回的 `workspacePath`、`workspaceKind`、`workspaceStatus`、工作区来源字段。
- 输出：项目页面显示生成路径与状态，不显示“未配置工作区”。
- 依赖：TODO-004、TODO-005。
- 完成标准：自动工作区项目创建后打开看板即可看到有效路径和状态。
- 关联 checklist：CHK-004、CHK-016、CHK-017。

## TODO-007 实现项目删除时的自动工作区选择

- 目标：删除系统自动创建工作区的项目时，询问用户是否一并删除工作区。
- 涉及区域：前端删除确认、`DELETE /api/projects/{id}` 请求语义、后端删除处理。
- 输入：工作区来源字段、用户删除选择。
- 输出：用户可选择保留或删除自动工作区；用户提供的工作区不被默认删除。
- 依赖：TODO-002、TODO-004。
- 完成标准：自动工作区项目删除前出现明确选择；保留和删除两种路径均可验证；手动工作区不被误删。
- 关联 checklist：CHK-012、CHK-013、CHK-014、CHK-015。

## TODO-008 补充后端自动化测试

- 目标：用自动化覆盖 API 层和数据状态的关键行为。
- 涉及区域：`tests/test_project_execution.py` 或项目 CRUD 相关测试。
- 输入：TODO-003、TODO-004、TODO-007 的实现。
- 输出：覆盖默认可执行项目、自动工作区命名、普通项目、手动路径、失败路径、删除选项、兼容性。
- 依赖：TODO-003、TODO-004、TODO-007。
- 完成标准：新增测试可稳定验证 CHK-002、CHK-003、CHK-005、CHK-008 至 CHK-015、CHK-018、CHK-019。
- 关联 checklist：CHK-002、CHK-003、CHK-005、CHK-008、CHK-009、CHK-010、CHK-011、CHK-012、CHK-013、CHK-014、CHK-015、CHK-018、CHK-019。

## TODO-009 补充前端和静态检查

- 目标：验证创建表单默认状态、普通项目开关、删除确认和语法正确性。
- 涉及区域：`app/projects.js`、前端测试或可用的静态检查。
- 输入：TODO-005、TODO-006、TODO-007 的实现。
- 输出：前端逻辑测试或人工验证步骤，确保 UI 行为符合 checklist。
- 依赖：TODO-005、TODO-006、TODO-007。
- 完成标准：创建表单默认可执行；普通项目可选；删除自动工作区项目时确认文案清楚；`app/projects.js` 语法检查通过。
- 关联 checklist：CHK-001、CHK-004、CHK-006、CHK-007、CHK-012。

## TODO-010 验证 Project Execution 与 Artifact 回归

- 目标：确认自动工作区不会破坏执行、审查、验收和产物管理。
- 涉及区域：Project Execution API、artifact list/read API、项目看板。
- 输入：默认创建的自动工作区项目、执行/审查 Agent 配置、测试 Markdown 产物。
- 输出：回归记录，包含 Project Execution 启动、artifact 空状态和有 Markdown 时的展示。
- 依赖：TODO-004、TODO-006、TODO-008。
- 完成标准：自动工作区项目可以启动任务；产物入口可打开；空状态与 Markdown 列表正常；现有 Project Execution 回归通过。
- 关联 checklist：CHK-016、CHK-017、CHK-020。

## TODO-011 更新需求归档与测试记录

- 目标：把实现结果、测试结果和剩余风险写回需求归档。
- 涉及区域：`.cosh-docs/requirment/auto-project-workspace/checklist.md`、`status.json`、交付说明。
- 输入：全部实现和测试结果。
- 输出：checklist 测试记录、实施状态、未解决风险；等待用户测试确认。
- 依赖：TODO-008、TODO-009、TODO-010。
- 完成标准：开发完成后 status 进入 `done`；测试结果可追溯到 checklist，用户已于 2026-06-17T02:40:45+08:00 确认完成。
- 关联 checklist：CHK-020。
