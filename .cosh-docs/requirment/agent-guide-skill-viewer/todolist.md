# Todolist: Agent Guide Skill Viewer

状态：已完成

完成时间：2026-07-07T23:12:00+08:00

验收摘要：用户已验收通过；Agent 指南入口、分类浏览、只读卡片和点击展示完整 `SKILL.md` 的二级弹窗均已交付。

## TODO-001 Confirm Existing UI Integration Points

- 目标：确认底部 toolbar、modal、Skills Library 和本地化文件的现有结构，避免实现时误改已有功能。
- 涉及区域：`app/index.html`、`app/style.css`、`app/locales/zh.json`、`app/locales/en.json`、现有技能库相关脚本。
- 输入：已确认的 requirement / checklist、现有前端结构。
- 输出：明确的接入点和需要编辑的文件清单。
- 依赖：无。
- 完成标准：确认 Agent Guide 可以作为独立按钮和独立 modal 接入，且不会复用 editable Skills Library 的行为。
- 关联 checklist：CHK-001, CHK-002, CHK-011, CHK-012, CHK-019。

## TODO-002 Define The VO Exposed Skill Data Source

- 目标：建立 Agent Guide 使用的 VO 内置暴露 skill 数据来源。
- 涉及区域：`skills/catalog.md`、`skills/*/SKILL.md`、可能新增或复用的前端数据结构。
- 输入：`skills/catalog.md` 当前列出的 VO 内置 skill。
- 输出：只包含 VO 内置暴露 skill 的数据结构，字段覆盖名称、用途、触发场景、分类。
- 依赖：TODO-001。
- 完成标准：数据来源或静态数据边界明确，不扫描全局 Codex skill、不混入用户自定义 skill、不包含内部 debug skill。
- 关联 checklist：CHK-004, CHK-005, CHK-016, CHK-017, CHK-018。

## TODO-003 Add Agent Guide Toolbar Button

- 目标：在底部 toolbar 增加 "Agent Guide" 入口。
- 涉及区域：`app/index.html`、相关本地化文案、必要的事件绑定。
- 输入：现有 toolbar DOM 结构和本地化 key。
- 输出：可见、可点击、可本地化的 Agent Guide 按钮。
- 依赖：TODO-001。
- 完成标准：按钮在主界面可见，点击后打开 Agent Guide modal，不遮挡或破坏 Projects、Archive Room、Reset、SMS、Browser 等既有按钮。
- 关联 checklist：CHK-001, CHK-002, CHK-015, CHK-019。

## TODO-004 Build Read-Only Agent Guide Modal

- 目标：新增中心 modal，用于展示 Agent Guide 内容。
- 涉及区域：`app/index.html`、`app/style.css`、必要的前端脚本。
- 输入：现有 modal 设计模式、TODO-002 的 skill 数据。
- 输出：独立的 Agent Guide modal，包含标题、关闭控件、分类过滤区、skill 卡片区和空状态。
- 依赖：TODO-002, TODO-003。
- 完成标准：modal 可打开和关闭；内容区域独立于 Skills Library；没有 add/edit/delete/upload/save/apply 控件。
- 关联 checklist：CHK-002, CHK-003, CHK-009, CHK-010, CHK-011, CHK-016。

## TODO-005 Render Skill Information Cards

- 目标：以信息卡片形式展示每个 VO 内置暴露 skill。
- 涉及区域：Agent Guide 前端渲染逻辑和样式。
- 输入：TODO-002 的 skill 数据。
- 输出：每个 skill 的名称、用途、触发 / 适用场景、分类。
- 依赖：TODO-004。
- 完成标准：所有暴露 VO skill 都能以卡片显示，字段完整，文案不包含推荐、排名或 best-fit 暗示。
- 关联 checklist：CHK-004, CHK-005, CHK-007, CHK-018。

## TODO-006 Implement Category Filtering

- 目标：支持用户按分类浏览 Agent Guide skill。
- 涉及区域：Agent Guide 前端渲染逻辑、filter 控件样式、本地化文案。
- 输入：skill category 字段。
- 输出：分类 filter 控件和按分类切换的卡片列表。
- 依赖：TODO-005。
- 完成标准：分类切换只做显示过滤；不提供搜索框；不排序推荐；空分类显示可理解的空状态。
- 关联 checklist：CHK-006, CHK-007, CHK-008, CHK-016, CHK-018。

## TODO-007 Add Localization Copy

- 目标：补齐中英文 UI 文案。
- 涉及区域：`app/locales/zh.json`、`app/locales/en.json`。
- 输入：Agent Guide 按钮、modal、字段标签、filter、空状态文案。
- 输出：中英文 locale key。
- 依赖：TODO-003, TODO-004, TODO-006。
- 完成标准：新增 UI 文案不硬编码单语言；JSON 可解析；中文文案清楚表达“查看”而非“推荐”。
- 关联 checklist：CHK-015, CHK-018, CHK-020。

## TODO-008 Polish Responsive Layout

- 目标：确保 Agent Guide modal 在桌面和窄视口下可读可用。
- 涉及区域：`app/style.css`、modal/card/filter 样式。
- 输入：现有 VO 视觉规范和 checklist 验收项。
- 输出：桌面和窄视口均稳定的布局。
- 依赖：TODO-004, TODO-005, TODO-006。
- 完成标准：卡片、分类控件和长文本不重叠、不溢出；modal 内部可滚动；视觉上与现有 VO 风格一致。
- 关联 checklist：CHK-013, CHK-014, CHK-019。

## TODO-009 Add Or Update Automated Checks

- 目标：用轻量自动化覆盖 Agent Guide 的关键静态行为。
- 涉及区域：`tests/` 下现有 JS 静态检查或新增检查脚本。
- 输入：实现后的 DOM、脚本和 locale 文件。
- 输出：能验证按钮、modal、scope 文案、无 search / no recommendation / read-only 行为的测试或静态检查。
- 依赖：TODO-003, TODO-004, TODO-005, TODO-006, TODO-007。
- 完成标准：自动化检查覆盖关键回归点，并能在本地命令中运行。
- 关联 checklist：CHK-001, CHK-002, CHK-004, CHK-007, CHK-008, CHK-009, CHK-010, CHK-015, CHK-017, CHK-018, CHK-020。

## TODO-010 Run Verification And Record Results

- 目标：执行 checklist 对应的静态检查和必要的人工 / 浏览器验证，并把结果回写交付说明或 checklist。
- 涉及区域：`checklist.md`、测试命令、浏览器验证记录。
- 输入：实现代码和 checklist。
- 输出：测试执行记录、覆盖说明、剩余人工验收点。
- 依赖：TODO-009。
- 完成标准：静态检查通过；UI 打开、过滤、关闭、布局和 existing toolbar / Skills Library 回归已验证；结果能追溯到 `CHK-*`。
- 关联 checklist：CHK-001 至 CHK-020。
