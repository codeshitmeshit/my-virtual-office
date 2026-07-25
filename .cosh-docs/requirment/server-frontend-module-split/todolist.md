# Server And Frontend Module Split Todolist

## 执行说明

本 todolist 基于已确认的 checklist 生成。后续创建执行 plan 时，每一步都应追溯到一个或多个 `TODO-*`，并在实现完成后按 `CHK-*` 验证结果。

## Tasks

### TODO-001：建立后端路由包骨架

- 目标：新增 `app/server_routes/` 包和统一 route dispatch 约定，为后续路由迁移提供稳定入口。
- 涉及区域：`app/server_routes/__init__.py`、`app/server.py`、新增结构性测试。
- 输入：`review.md` 推荐方案、`CHK-001`、现有 `OfficeHandler.do_GET/do_POST/do_PUT/do_DELETE`。
- 输出：`server_routes` 包存在，暴露按 method/path/query 分发的入口；`OfficeHandler` 可以调用 route dispatcher 并在未处理时回退原逻辑。
- 依赖：无。
- 完成标准：结构性测试能确认 route 包和 dispatch 入口存在；未迁移路由仍保持原行为。
- 关联 checklist：CHK-001、CHK-009、CHK-016。

### TODO-002：实现公共 HTTP helper

- 目标：提供统一 `send_json()`、`read_json()`、`require_origin()` 和可选错误响应 helper，减少重复 JSON/CORS 代码。
- 涉及区域：`app/server_routes/http.py`、迁移后的 route 模块、相关单测。
- 输入：现有 `server.py` 中重复 `send_response`、`send_header("Content-Type", "application/json")`、`Access-Control-Allow-Origin` 和 `json.loads(self.rfile.read(length))` 代码。
- 输出：`send_json(handler, data, status=None, headers=None)`、`read_json(handler, max_bytes=None)`、`require_origin(handler, allowed=None)`；至少一个 GET 和一个 POST route 使用 helper。
- 依赖：TODO-001。
- 完成标准：空 body、合法 JSON、非法 JSON、`_status` 字段、CORS header、origin 校验均有测试或结构性验证覆盖。
- 关联 checklist：CHK-002、CHK-003、CHK-004、CHK-010、CHK-018。

### TODO-003：迁移 Projects 路由委派

- 目标：将 projects 域路径分支从 `OfficeHandler.do_*` 抽到 `app/server_routes/projects.py`。
- 涉及区域：`app/server_routes/projects.py`、`app/server.py`、`tests/test_project_execution.py`、project/cron/browser check 相关测试。
- 输入：`/api/projects*`、project tasks、project execution、scheduled cron、project artifacts 相关分支和 `_handle_project*`、`_handle_task*`、`_handle_score*` 函数。
- 输出：projects route 模块处理代表性 GET/POST/PUT/DELETE 路径；业务逻辑首阶段可继续调用现有 `_handle_*` 函数。
- 依赖：TODO-001、TODO-002。
- 完成标准：项目列表、详情、创建、更新、删除、执行、cron 代表路径响应结构兼容；未迁移路径能回退。
- 关联 checklist：CHK-005、CHK-009、CHK-010、CHK-015、CHK-016。

### TODO-004：迁移 Providers 路由委派

- 目标：将 provider 相关路径分支抽到 `app/server_routes/providers.py`，并保留 handler context 兼容。
- 涉及区域：`app/server_routes/providers.py`、`app/server.py`、`app/providers/*`、provider runtime/config 测试。
- 输入：`/api/hermes/test`、`/api/codex/test`、`/api/claude-code/test`、provider key/model config、`OfficeHandler` 内 `_send_watcher_request`、`_get_models`、`_set_agent_model` 等方法。
- 输出：providers route 模块处理 provider test/config/key/model 代表路径；需要 handler 方法的路由通过 `handler` 调用，不强行搬迁内部状态方法。
- 依赖：TODO-001、TODO-002。
- 完成标准：provider 测试、保存、删除、模型配置行为兼容；敏感 key/token 不泄露到响应或日志。
- 关联 checklist：CHK-006、CHK-010、CHK-015、CHK-018。

### TODO-005：迁移 Meetings 路由委派

- 目标：将 meetings 域路径分支抽到 `app/server_routes/meetings.py`。
- 涉及区域：`app/server_routes/meetings.py`、`app/server.py`、meeting request/executable meeting 相关测试。
- 输入：`/api/meetings/active`、`/api/meetings/history`、`/api/meetings/requests`、request confirm/reject、executable meeting actions、action items 相关 `_handle_meeting*` 函数。
- 输出：meetings route 模块处理会议列表、请求、确认/拒绝、executable meeting action 代表路径。
- 依赖：TODO-001、TODO-002。
- 完成标准：会议状态流、请求状态、executable meeting 操作和 action item 路径响应兼容。
- 关联 checklist：CHK-007、CHK-010、CHK-015、CHK-016。

### TODO-006：迁移 Notifications 路由委派

- 目标：将 Feishu notification 和 card action 相关路径抽到 `app/server_routes/notifications.py`。
- 涉及区域：`app/server_routes/notifications.py`、`app/server.py`、`app/feishu_notifications.py`、Feishu notification 测试。
- 输入：Feishu notification config、test、card action 相关分支和 `_handle_feishu_card_action` 等函数。
- 输出：notifications route 模块处理 Feishu 配置读取/保存、测试发送、卡片 action 代表路径。
- 依赖：TODO-001、TODO-002。
- 完成标准：Feishu masked secret 再保存不清空旧 secret；错误响应和 test card 行为兼容。
- 关联 checklist：CHK-008、CHK-010、CHK-015、CHK-018。

### TODO-007：补齐后端结构性和契约测试

- 目标：新增后端拆分守门测试，并把四个路由域的代表接口纳入回归。
- 涉及区域：`tests/check_server_frontend_module_split.mjs` 或 Python 等价测试、现有 provider/projects/meetings/Feishu 测试。
- 输入：TODO-001 至 TODO-006 的输出、已确认 checklist。
- 输出：结构性测试覆盖 route 文件、dispatch 入口、helper 使用、回退逻辑；契约测试覆盖代表路径。
- 依赖：TODO-001、TODO-002、TODO-003、TODO-004、TODO-005、TODO-006。
- 完成标准：相关 Python/Node 测试通过；环境依赖无法运行的测试记录原因。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010、CHK-015、CHK-016。

### TODO-008：抽出前端设置共享模块

- 目标：新增设置逻辑共享模块，消除 `setup.html` 和 `game.js` 设置逻辑中的基础重复。
- 涉及区域：`app/settings-common.js`、`app/setup.html`、`app/index.html`、`app/game.js`。
- 输入：现有 escape、fetch JSON、masked Feishu 判断、weather location、默认 browser URL 等函数。
- 输出：`settings-common.js` 提供共享工具，并通过普通 script 顺序在 setup 和首页加载。
- 依赖：无。
- 完成标准：共享函数可用；页面加载无 `ReferenceError`；缓存版本参数已更新。
- 关联 checklist：CHK-011、CHK-014、CHK-017。

### TODO-009：抽出 Setup Wizard 设置模块

- 目标：将 `setup.html` 内联设置脚本迁移到独立 `app/setup-settings.js`，保留旧入口兼容。
- 涉及区域：`app/setup.html`、`app/setup-settings.js`、setup browser/JS 检查。
- 输入：license、step navigation、provider prefill/test、Browser/SMS/PC Metrics/Feishu/weather、finish setup 相关内联脚本。
- 输出：`setup-settings.js` 承接 setup wizard 行为；必要函数挂到 `window`，例如 `finishSetup`、`testCodexConnection`、`testClaudeCodeConnection`、`testBrowserConnection`。
- 依赖：TODO-008。
- 完成标准：setup 页面开关、测试按钮、配置保存、finish setup 行为保持可用；HTML 内联脚本显著减少。
- 关联 checklist：CHK-011、CHK-012、CHK-014、CHK-017、CHK-018。

### TODO-010：抽出主菜单设置模块

- 目标：将 `game.js` 中主菜单设置面板逻辑迁移到 `app/main-menu-settings.js`，并保留全局 `mm*` 入口。
- 涉及区域：`app/game.js`、`app/main-menu-settings.js`、`app/index.html`、主菜单 browser checks。
- 输入：`toggleMainMenu`、`_mmLoadCurrentSettings`、`mmTestHermes`、`mmTestCodex`、`mmTestClaudeCode`、`mmTestCdp`、`mmTestViewer`、`mmSaveSettings`、Feishu 主菜单设置函数。
- 输出：主菜单设置逻辑位于独立模块；`window.mmSaveSettings`、`window.mmTestHermes`、`window.mmTestCodex`、`window.mmTestClaudeCode`、`window.mmTestWeather` 等入口保持可用。
- 依赖：TODO-008。
- 完成标准：首页主菜单能打开、字段回填、设置保存、provider/weather/browser/Feishu 测试入口可用；`game.js` 行数下降。
- 关联 checklist：CHK-011、CHK-013、CHK-014、CHK-016、CHK-017、CHK-018。

### TODO-011：补齐前端浏览器冒烟测试

- 目标：用浏览器或 Node 检查覆盖 setup 和主菜单设置模块拆分后的真实加载和交互入口。
- 涉及区域：`tests/check_provider_runtime_settings_ui.mjs`、新增或更新 setup/main-menu 检查脚本。
- 输入：TODO-008、TODO-009、TODO-010 的输出。
- 输出：测试覆盖 script 加载、全局入口、开关显示隐藏、配置回填、保存/测试按钮主要路径。
- 依赖：TODO-008、TODO-009、TODO-010。
- 完成标准：setup 和首页主菜单无 console error，无缺失全局函数；关键入口可被调用。
- 关联 checklist：CHK-012、CHK-013、CHK-014、CHK-015、CHK-017。

### TODO-012：执行完整回归并记录结果

- 目标：在完成后端和前端拆分后运行相关回归，形成交付说明。
- 涉及区域：测试命令输出、`checklist.md` 测试结果记录、最终交付说明。
- 输入：TODO-001 至 TODO-011 的实现结果。
- 输出：相关 Python/Node/browser 测试结果；无法运行项的原因；按 checklist 的验证记录。
- 依赖：TODO-007、TODO-011。
- 完成标准：所有可运行相关测试通过；失败项已修复或明确记录为环境依赖；checklist 中可追溯到测试结果。
- 关联 checklist：CHK-015、CHK-016、CHK-017、CHK-018。

### TODO-013：更新维护文档和迁移边界说明

- 目标：记录新的模块边界、route 添加方式、设置模块入口约定，帮助后续维护不再回填巨型文件。
- 涉及区域：可选 `docs/` 文档、需求交付说明、代码注释中极少量边界说明。
- 输入：最终模块结构、route dispatch 约定、前端全局入口兼容策略。
- 输出：简短维护说明，包含新增 route 的放置规则、helper 使用规则、设置模块新增函数的挂载规则。
- 依赖：TODO-001 至 TODO-012。
- 完成标准：后续开发者能从文档判断新 projects/providers/meetings/notifications 或设置逻辑应放到哪个模块。
- 关联 checklist：CHK-016、CHK-018。

## Phase 2 增量 Tasks

### TODO-014：迁移 Setup Wizard 内联设置脚本

- 目标：将 `app/setup.html` 中 setup wizard 的大段内联设置逻辑真实迁入 `app/setup-settings.js`。
- 涉及区域：`app/setup.html`、`app/setup-settings.js`、`app/settings-common.js`、setup 相关结构性测试。
- 输入：现有 `nextStep`、license 激活、provider/browser/SMS/PC metrics/Feishu/weather test/save、`finishSetup` 等函数。
- 输出：`setup-settings.js` 包含实际 setup wizard 设置逻辑；`setup.html` 只保留轻量 i18n/title 辅助和模块 script 引用。
- 依赖：TODO-008、TODO-009。
- 完成标准：`setup.html` 行数明显下降；`window.nextStep`、`window.finishSetup`、`window.testCodexConnection` 等旧入口存在；setup 页面加载和主要按钮调用无错误。
- 关联 checklist：CHK-019、CHK-020、CHK-024、CHK-025。

### TODO-015：迁移 Main Menu 设置块

- 目标：将 `app/game.js` 中主菜单设置相关函数真实迁入 `app/main-menu-settings.js`。
- 涉及区域：`app/game.js`、`app/main-menu-settings.js`、`app/index.html`、主菜单相关结构性测试。
- 输入：`toggleMainMenu`、`_mmLoadCurrentSettings`、`mmApplyFontScaleSetting`、`mmTestHermes`、`mmTestCodex`、`mmTestClaudeCode`、`mmTestCdp`、`mmTestViewer`、`mmTestWeather`、`mmSaveSettings`、Feishu 保存/测试、导入导出/重置等函数。
- 输出：`main-menu-settings.js` 承接主菜单设置职责；`game.js` 移除该设置块但保留非设置相关逻辑。
- 依赖：TODO-008、TODO-010。
- 完成标准：`game.js` 行数明显下降；`window.toggleMainMenu`、`window.mmSaveSettings`、`window.mmTest*`、Feishu 旧入口存在；首页主菜单打开、回填、保存和测试入口可用。
- 关联 checklist：CHK-021、CHK-022、CHK-024、CHK-025。

### TODO-016：删除 `server.py` 中已接管的重复路由分支

- 目标：移除 `OfficeHandler.do_GET/do_POST/do_PUT/do_DELETE` 中已经由 `server_routes.dispatch()` 覆盖的旧路由分支，消除双维护点。
- 涉及区域：`app/server.py`、`app/server_routes/projects.py`、`app/server_routes/providers.py`、`app/server_routes/meetings.py`、`app/server_routes/notifications.py`、route dispatch 测试。
- 输入：Phase 1 已接管的 projects/providers/meetings/notifications 路由和现有 `tests/test_server_routes_module_split.py`。
- 输出：`server.py` 不再保留同一路径的重复实现；未接管路径继续回退旧逻辑。
- 依赖：TODO-001 至 TODO-007。
- 完成标准：route dispatch 测试覆盖 GET/POST/PUT/DELETE 代表路径；`/setup/save`、`/vo-config`、`/browser-status`、archive-room、agent/skills-library 等未迁移路径仍可由旧逻辑处理。
- 关联 checklist：CHK-023、CHK-024、CHK-025。

### TODO-017：强化 Phase 2 结构性守门测试

- 目标：让测试能证明 Phase 2 不是只增加 shim，而是真正迁移代码块。
- 涉及区域：`tests/check_server_frontend_module_split.mjs`、可能新增 setup/main-menu 检查脚本、`tests/test_server_routes_module_split.py`。
- 输入：TODO-014、TODO-015、TODO-016 的迁移结果。
- 输出：结构性测试检查 HTML script 引用、旧全局入口挂载、`setup-settings.js`/`main-menu-settings.js` 中实际函数体、`game.js`/`setup.html` 中重复块已移除、`server.py` 重复路由分支减少。
- 依赖：TODO-014、TODO-015、TODO-016。
- 完成标准：结构性测试能在迁移退化为 shim 或旧分支回流时失败。
- 关联 checklist：CHK-019、CHK-020、CHK-021、CHK-022、CHK-023、CHK-025。

### TODO-018：执行 Phase 2 复测并写回验收记录

- 目标：完成 Phase 2 后运行相关测试，并把行数变化和测试结果写回 `checklist.md`。
- 涉及区域：测试命令、`checklist.md`、`status.json`、最终交付说明。
- 输入：TODO-014 至 TODO-017 的实现结果。
- 输出：行数前后对比、结构性测试结果、JS 语法检查、Python route tests、相关 Node/Python 回归结果、无法归因于迁移的既有失败说明。
- 依赖：TODO-017。
- 完成标准：CHK-019 至 CHK-025 均能对应到自动测试或人工验证记录；实现完成后阶段推进到 `implementation_done`，等待用户确认 tested/done。
- 关联 checklist：CHK-024、CHK-025。

## Phase 3-7 Game.js 完整拆分路线图

执行约束：Phase 3-7 必须按“实现 TODO -> 测试闸门 TODO”的顺序推进。任一测试闸门未通过或未记录失败原因时，不得进入下一个 phase 的实现 TODO。

### TODO-019：Phase 3 迁移 Agent Creator Panel

- 目标：将 Agent Creator Panel 从 `app/game.js` 拆到 `app/agent-creator-panel.js`。
- 涉及区域：`app/game.js`、`app/agent-creator-panel.js`、`app/index.html`、结构性测试。
- 输入：`toggleAgentPanel`、`_buildAgentPanel`、agent 外观编辑、预览、保存、撤销、branch/provider/platform 选择弹窗和相关 DOM 事件。
- 输出：Agent Creator Panel 职责集中到独立模块；旧入口如 `window.toggleAgentPanel` 保持可用。
- 依赖：Phase 2 已完成主菜单设置迁移。
- 完成标准：Agent panel 可打开、列表/预览/保存/撤销/分配选择可用；`game.js` 不再包含 Agent Creator Panel 函数体；行数下降约 900-1500 行或记录实际差异。
- 关联 checklist：后续 Phase 3 checklist 需新增。

### TODO-020：Phase 3 测试闸门

- 目标：验证 Agent Creator Panel 拆分完成且无回归，作为进入 Phase 4 的硬门禁。
- 涉及区域：`app/agent-creator-panel.js`、`app/game.js`、`app/index.html`、结构性测试、浏览器 smoke test。
- 输入：TODO-019 的实现结果。
- 输出：Phase 3 测试记录，包含 JS 语法、结构性检查、旧入口兼容、行数变化和 Agent panel 代表交互结果。
- 依赖：TODO-019。
- 完成标准：`node --check` 通过；结构性测试确认 `agent-creator-panel.js` 被引用、旧入口存在、`game.js` 不含迁移函数体；Agent panel 可打开、保存/撤销/预览可用；失败项已修复或明确记录并得到确认。
- 关联 checklist：后续 Phase 3 checklist 需新增。

### TODO-021：Phase 4 迁移 Edit Mode / Layout Editor

- 目标：将办公室编辑控制层从 `app/game.js` 拆到 `app/office-layout-editor.js`，必要时拆出 `app/office-color-picker.js`。
- 涉及区域：`app/game.js`、`app/office-layout-editor.js`、`app/office-color-picker.js`、`app/index.html`、编辑模式相关测试。
- 输入：edit mode 状态、家具选择、拖拽、多选、撤销、保存、catalog 面板、color picker、desk/branch assign menu、canvas edit overlay 和 edit HUD。
- 输出：编辑控制层职责独立；底层 rendering/collision 暂不在本 phase 大规模迁移。
- 依赖：TODO-020。
- 完成标准：编辑模式开关、拖拽、多选、撤销、保存、颜色编辑、desk/branch 分配菜单可用；`game.js` 行数下降约 2500-4000 行或记录实际差异。
- 关联 checklist：后续 Phase 4 checklist 需新增。

### TODO-022：Phase 4 测试闸门

- 目标：验证 Layout Editor 拆分完成且编辑能力未回退，作为进入 Phase 5 的硬门禁。
- 涉及区域：`app/office-layout-editor.js`、`app/office-color-picker.js`、`app/game.js`、编辑模式结构性测试、浏览器 smoke test。
- 输入：TODO-021 的实现结果。
- 输出：Phase 4 测试记录，包含 JS 语法、结构性检查、编辑模式代表操作和行数变化。
- 依赖：TODO-021。
- 完成标准：`node --check` 通过；结构性测试确认新模块被引用、旧入口存在、`game.js` 不含迁移函数体；编辑模式开关、拖拽、多选、撤销、保存、颜色编辑、desk/branch 分配菜单通过 smoke test。
- 关联 checklist：后续 Phase 4 checklist 需新增。

### TODO-023：Phase 5 迁移 Environment Rendering / Furniture

- 目标：将环境与家具绘制函数从 `app/game.js` 拆到 rendering 模块。
- 涉及区域：`app/game.js`、`app/office-rendering.js`、`app/furniture-renderers.js`、`app/weather-rendering.js`、可选 `app/collision-system.js`、`app/index.html`。
- 输入：`drawEnvironment`、window/weather 绘制、walls/floor/lighting、furniture dispatcher、desk、meeting room、lounge、kitchen、bookshelf、plant、vending 等绘制函数；如果边界清楚，再迁移 collision grid。
- 输出：环境/家具 rendering 职责集中，canvas 主循环继续调用迁移后的绘制入口。
- 依赖：TODO-022。
- 完成标准：canvas 非空，家具/墙体/天气窗口/灯光/交互点显示正常；collision grid 不回退；`game.js` 行数下降约 3500-5500 行或记录实际差异。
- 关联 checklist：后续 Phase 5 checklist 需新增。

### TODO-024：Phase 5 测试闸门

- 目标：验证环境与家具 rendering 拆分完成且 canvas 视觉/交互基础未回退，作为进入 Phase 6 的硬门禁。
- 涉及区域：`app/office-rendering.js`、`app/furniture-renderers.js`、`app/weather-rendering.js`、可选 `app/collision-system.js`、浏览器/canvas smoke test。
- 输入：TODO-023 的实现结果。
- 输出：Phase 5 测试记录，包含 JS 语法、结构性检查、canvas 非空截图或像素检查、家具/天气/碰撞代表验证和行数变化。
- 依赖：TODO-023。
- 完成标准：`node --check` 通过；结构性测试确认新模块被引用、旧入口存在、`game.js` 不含迁移函数体；canvas 非空，家具/墙体/天气窗口/灯光/交互点正常；collision grid 相关测试或人工验证通过。
- 关联 checklist：后续 Phase 5 checklist 需新增。

### TODO-025：Phase 6 迁移 Agents / Bubbles / Idle Animations

- 目标：将 agent 模型、agent 渲染、气泡和 idle 动画系统从 `app/game.js` 拆出。
- 涉及区域：`app/game.js`、`app/agent-model.js`、`app/agent-rendering.js`、`app/bubble-system.js`、`app/office-ambient-animations.js`、`app/pet-system.js`、`app/index.html`。
- 输入：Agent class、agent appearance drawing、bubbles/chat bubbles、paper airplane、RPS、social interactions、gatherings、dart games、pong、pets，以及 agent update/draw 相关循环函数。
- 输出：agent runtime 与装饰动画职责独立，主 loop 保持调用兼容。
- 依赖：TODO-024。
- 完成标准：agent 正常出现、移动、聊天气泡、会议状态、idle 动画和 pet 动画不报错；`game.js` 行数下降约 5000-7000 行或记录实际差异。
- 关联 checklist：后续 Phase 6 checklist 需新增。

### TODO-026：Phase 6 测试闸门

- 目标：验证 agent runtime、气泡和 idle 动画拆分完成且核心运行循环未回退，作为进入 Phase 7 的硬门禁。
- 涉及区域：`app/agent-model.js`、`app/agent-rendering.js`、`app/bubble-system.js`、`app/office-ambient-animations.js`、`app/pet-system.js`、浏览器/canvas smoke test。
- 输入：TODO-025 的实现结果。
- 输出：Phase 6 测试记录，包含 JS 语法、结构性检查、agent 出现/移动/气泡/动画代表验证和行数变化。
- 依赖：TODO-025。
- 完成标准：`node --check` 通过；结构性测试确认新模块被引用、旧入口存在、`game.js` 不含迁移函数体；agent 正常出现、移动、聊天气泡、会议状态、idle 动画和 pet 动画无 console error。
- 关联 checklist：后续 Phase 6 checklist 需新增。

### TODO-027：Phase 7 迁移 Meetings / Sidebar / Workspace / Skills 并收口 Bootstrap

- 目标：迁移剩余大型 UI 面板，并把 `game.js` 收敛为薄启动/编排层。
- 涉及区域：`app/game.js`、`app/meeting-ui.js`、`app/sidebar-ui.js`、`app/agent-workspace-panel.js`、`app/skills-library-ui.js`、可选 `app/game-bootstrap.js`、`app/index.html`。
- 输入：meeting modals、meeting request、action items、sidebar widgets、agent workspace panel、skills library、skill editor、最终 script 加载顺序和兼容导出。
- 输出：`game.js` 只保留 canvas/context 初始化、全局配置读取、主 loop 调度、模块加载顺序说明和必要 `window.*` 兼容入口。
- 依赖：TODO-026。
- 完成标准：meeting/sidebar/workspace/skills 代表入口均可用；首页加载无 console error；`game.js` 目标控制在 1-3k 行以内，若未达到需记录剩余原因和下一步拆分点。
- 关联 checklist：后续 Phase 7 checklist 需新增。

### TODO-028：Phase 7 最终测试闸门与 Bootstrap 验收

- 目标：验证 Phase 3-7 全部拆分闭环，确认 `game.js` 已成为薄启动/编排层。
- 涉及区域：所有新增前端模块、`app/game.js`、`app/index.html`、结构性测试、浏览器 smoke test、需求验收记录。
- 输入：TODO-027 的实现结果。
- 输出：最终测试记录，包含所有新增模块 JS 语法、结构性测试、HTML 加载顺序、旧全局入口兼容、canvas 非空、主流程 UI smoke 和最终行数对比。
- 依赖：TODO-027。
- 完成标准：所有 phase 代表入口通过；首页无 console error；`game.js` 行数达到 1-3k 目标或记录剩余原因；需求文档记录最终测试结果，等待用户确认 tested/done。
- 关联 checklist：后续 Phase 7 checklist 需新增。

## Phase 8-11 Python 服务拆分路线图

执行约束：Phase 8-11 继续执行“一拆一测”。每个服务域必须先完成实现 TODO，再完成对应测试闸门 TODO；测试闸门未通过或未记录失败原因时，不得进入下一个 phase 的实现 TODO。

### TODO-029：Phase 8 迁移 Projects Service

- 目标：将 project 业务函数从 `app/server.py` 迁入 `app/server_services/projects.py`。
- 涉及区域：`app/server.py`、`app/server_routes/projects.py`、`app/server_services/projects.py`、project execution/cron 相关测试。
- 输入：project CRUD、task update/delete、project execution start/cancel/review/accept、checklist 状态计算、scheduled cron/project load repair 相关 `_handle_*` 函数。
- 输出：project route 通过 service 执行业务逻辑；`server.py` 中已迁移 project 函数体删除或降级为薄 wrapper。
- 依赖：TODO-028。
- 完成标准：API path、HTTP method、响应字段、workspace 安全门禁和 `_status` 语义不变；`server.py` project 业务重复逻辑减少；行数变化已记录。
- 关联 checklist：CHK-036、CHK-037。

### TODO-030：Phase 8 测试闸门

- 目标：验证 Projects Service 拆分完成且 project execution/cron 行为未回退，作为进入 Phase 9 的硬门禁。
- 涉及区域：`app/server_services/projects.py`、`app/server_routes/projects.py`、project execution/cron 测试、结构性测试。
- 输入：TODO-029 的实现结果。
- 输出：Phase 8 测试记录，包含 Python 编译、结构性检查、project pytest/Node 子集、行数变化和既有失败归因。
- 依赖：TODO-029。
- 完成标准：`py_compile` 通过；结构性测试确认 route 调用 service 且 `server.py` 不保留已迁移函数体；project execution、scheduled cron、project start payload 相关测试通过，或失败被明确标注为既有且经用户确认。
- 关联 checklist：CHK-037。

### TODO-031：Phase 9 迁移 Meetings Service

- 目标：将 meeting 业务函数从 `app/server.py` 迁入 `app/server_services/meetings.py`。
- 涉及区域：`app/server.py`、`app/server_routes/meetings.py`、`app/server_services/meetings.py`、meeting for AI 相关测试。
- 输入：meeting request、confirm/reject、executable meeting lifecycle、active/history 查询、conflict/action item、quality gate 和 meeting for AI 相关 `_handle_*` 函数。
- 输出：meeting route 通过 service 执行业务逻辑；`server.py` 中已迁移 meeting 函数体删除或降级为薄 wrapper。
- 依赖：TODO-030。
- 完成标准：meeting 状态机、通知触发、project 关联和响应字段不变；行数变化已记录。
- 关联 checklist：CHK-038、CHK-039。

### TODO-032：Phase 9 测试闸门

- 目标：验证 Meetings Service 拆分完成且 meeting for AI 行为未回退，作为进入 Phase 10 的硬门禁。
- 涉及区域：`app/server_services/meetings.py`、`app/server_routes/meetings.py`、meeting for AI 测试、project meeting records UI 检查。
- 输入：TODO-031 的实现结果。
- 输出：Phase 9 测试记录，包含 Python 编译、结构性检查、meeting pytest/Node 子集、行数变化和既有失败归因。
- 依赖：TODO-031。
- 完成标准：`tests/test_meeting_for_ai_phase4.py`、`tests/test_meeting_for_ai_phase5.py`、`tests/test_meeting_for_ai_phase6.py` 和 `node tests/check_project_meeting_records_ui.mjs` 通过，或失败被明确标注为既有且经用户确认。
- 关联 checklist：CHK-039。

### TODO-033：Phase 10 迁移 Providers Service

- 目标：将 provider runtime/config/test 业务函数从 `app/server.py` 迁入 `app/server_services/providers.py`。
- 涉及区域：`app/server.py`、`app/server_routes/providers.py`、`app/server_services/providers.py`、provider runtime 相关测试。
- 输入：provider runtime config、Hermes/Codex/Claude Code 测试、provider execution contract、gateway/origin/token 相关业务逻辑。
- 输出：provider route 通过 service 执行业务逻辑；`server.py` 中已迁移 provider 函数体删除或降级为薄 wrapper。
- 依赖：TODO-032。
- 完成标准：provider 配置文件格式、masked secret 规则、runtime watcher、默认 provider 选择策略和测试接口返回结构不变；行数变化已记录。
- 关联 checklist：CHK-040、CHK-041。

### TODO-034：Phase 10 测试闸门

- 目标：验证 Providers Service 拆分完成且 provider runtime 行为未回退，作为进入 Phase 11 的硬门禁。
- 涉及区域：`app/server_services/providers.py`、`app/server_routes/providers.py`、provider runtime pytest/Node 测试。
- 输入：TODO-033 的实现结果。
- 输出：Phase 10 测试记录，包含 Python 编译、结构性检查、provider pytest/Node 子集、行数变化和既有失败归因。
- 依赖：TODO-033。
- 完成标准：`tests/test_provider_runtime_config.py`、`tests/test_provider_execution_contract.py` 和 `node tests/check_provider_runtime_settings_ui.mjs` 通过，或失败被明确标注为既有且经用户确认。
- 关联 checklist：CHK-041。

### TODO-035：Phase 11 迁移 Notifications Service

- 目标：将 notification/Feishu 业务函数从 `app/server.py` 迁入 `app/server_services/notifications.py`。
- 涉及区域：`app/server.py`、`app/server_routes/notifications.py`、`app/server_services/notifications.py`、Feishu notification 相关测试。
- 输入：Feishu notification config、masked secret 保存、webhook/test/card action、通知状态读写和相关 helper。
- 输出：notification route 通过 service 执行业务逻辑；`server.py` 中已迁移 notification 函数体删除或降级为薄 wrapper。
- 依赖：TODO-034。
- 完成标准：Feishu secret mask、通知 payload 字段、失败降级和测试接口返回结构不变；行数变化已记录。
- 关联 checklist：CHK-042、CHK-043。

### TODO-036：Phase 11 最终测试闸门与 Python 服务拆分验收

- 目标：验证 Phase 8-11 全部服务拆分闭环，确认 `server.py` 的 domain business logic 明显减少。
- 涉及区域：`app/server.py`、`app/server_routes/*.py`、`app/server_services/*.py`、相关 Python/Node 回归、服务 smoke test、需求验收记录。
- 输入：TODO-035 的实现结果。
- 输出：最终测试记录，包含 Python 编译、结构性测试、domain pytest/Node 子集、服务 smoke、行数对比和完整相关 Python 子集结果。
- 依赖：TODO-035。
- 完成标准：Projects、Meetings、Providers、Notifications 四个 service 均被 route 调用；`server.py` 不保留已迁移业务函数体的重复实现；`/health`、`/api/license`、`/browser-status` smoke 通过；失败项已修复或明确记录为既有问题并等待用户确认 tested/done。
- 关联 checklist：CHK-043。

## Phase 12-17 Python 主服务继续瘦身路线图

执行约束：Phase 12-17 继续执行“一拆一测”。每个 phase 必须先完成实现 TODO，再完成对应测试闸门 TODO；测试闸门未通过、未修复或未明确记录失败归因前，不得进入下一个 phase 的实现 TODO。迁移时不改变 API path、HTTP method、响应字段、CORS/origin、secret mask、运行时状态语义；`server.py` 允许保留兼容导出，但不得保留已迁移函数体的重复实现。

### TODO-037：Phase 12 迁移 Workflow Service（已完成）

- 目标：将 workflow execution pipeline 从 `app/server.py` 迁入 `app/server_services/workflow.py`，并补 `app/server_routes/workflow.py`。
- 涉及区域：`app/server.py`、`app/server_routes/projects.py`、`app/server_routes/workflow.py`、`app/server_services/projects.py`、`app/server_services/workflow.py`、workflow/project execution/cron 测试。
- 输入：`_wf_*` 函数、workflow start/stop/auto-mode/status/session/task-file/review/rework/persist/auto-resume 相关逻辑，以及 `/api/projects/{id}/workflow/*` 路由分支。
- 输出：workflow route 通过 workflow service 执行业务逻辑；`server.py` 中 `_wf_*` 函数体删除或降级为薄兼容导出。
- 依赖：TODO-036。
- 完成标准：workflow API、task state、review safety、session cleanup、cron/auto-resume 语义不变；`server.py` 行数和 `_wf_*` 函数数量明显下降；行数变化已记录。
- 关联 checklist：CHK-044、CHK-045。

### TODO-038：Phase 12 测试闸门（已完成）

- 目标：验证 Workflow Service 拆分完成且 workflow/project execution/cron 行为未回退，作为进入 Phase 13 的硬门禁。
- 涉及区域：`app/server_services/workflow.py`、`app/server_routes/workflow.py`、project execution/cron/workflow e2e 测试、结构性测试。
- 输入：TODO-037 的实现结果。
- 输出：Phase 12 测试记录，包含 Python 编译、结构性检查、workflow e2e、project execution/cron pytest 子集、Node start payload check、行数变化和失败归因。
- 依赖：TODO-037。
- 完成标准：`py_compile` 通过；结构性测试确认 workflow route 调用 service 且 `server.py` 不保留 `_wf_*` 函数体；`tests/test_workflow_e2e.py`、project execution/cron 子集和 `node tests/check_project_execution_start_payload.mjs` 通过，或失败被明确标注并经用户确认。
- 关联 checklist：CHK-045。

### TODO-039：Phase 13 迁移 Archive Room Service（已完成）

- 目标：将 archive room/manager/governance 业务从 `app/server.py` 迁入 `app/server_services/archive_room.py`，并补 `app/server_routes/archive_room.py`。
- 涉及区域：`app/server.py`、`app/server_routes/archive_room.py`、`app/server_services/archive_room.py`、archive room Python/Chrome/Node 测试。
- 输入：`_archive_*`、`_handle_archive_*`、archive manager profile、manual maintain、AI refine、daily inspection、important message、meeting/task triggers、project record/context package/governance action 相关逻辑。
- 输出：archive room route 通过 archive service 执行业务逻辑；`server.py` 中 archive 函数体删除或降级为薄兼容导出。
- 依赖：TODO-038。
- 完成标准：档案室数据格式、pending confirmation、authority/confidence、AI refine、maintenance schedule、archive manager profile 语义不变；行数变化已记录。
- 关联 checklist：CHK-046、CHK-047。

### TODO-040：Phase 13 测试闸门（已完成）

- 目标：验证 Archive Room Service 拆分完成且档案室核心行为未回退，作为进入 Phase 14 的硬门禁。
- 涉及区域：`app/server_services/archive_room.py`、`app/server_routes/archive_room.py`、archive room pytest、archive room Chrome/Node checks。
- 输入：TODO-039 的实现结果。
- 输出：Phase 13 测试记录，包含 Python 编译、结构性检查、archive room pytest/Chrome/Node 子集、行数变化和失败归因。
- 依赖：TODO-039。
- 完成标准：`tests/test_archive_room_phase_1_3.py` 到 `phase_8.py`、`tests/test_archive_room_ai_refine.py` 和 archive room Chrome checks 通过，或失败被明确标注并经用户确认。
- 关联 checklist：CHK-047。

### TODO-041：Phase 14 迁移 Agent Provider Bridge Service（已完成）

- 目标：将 Hermes/Codex/Claude Code chat/run/activity/approval 通信桥从 `app/server.py` 迁入 `app/server_services/agent_bridges.py`，并补 `app/server_routes/agent_bridges.py`。
- 涉及区域：`app/server.py`、`app/server_routes/agent_bridges.py`、`app/server_services/agent_bridges.py`、provider bridge 相关 Python/Node 测试。
- 输入：Hermes API/native chat/run/events/approval/history clear、Codex chat/run/events/activity/interaction/approval/cancel/reset/compact、Claude Code chat/run/events/cancel/history clear 相关 `_handle_*` 逻辑。
- 输出：provider bridge route 通过 agent bridge service 执行业务逻辑；`server.py` 中 provider bridge 函数体删除或降级为薄兼容导出。
- 依赖：TODO-040。
- 完成标准：SSE、activity polling、approval pending/respond、cancel/reset/compact、conversation/history 语义不变；行数变化已记录。
- 关联 checklist：CHK-048、CHK-049。

### TODO-042：Phase 14 测试闸门（已完成）

- 目标：验证 Agent Provider Bridge 拆分完成且 Hermes/Codex/Claude 通信行为未回退，作为进入 Phase 15 的硬门禁。
- 涉及区域：`app/server_services/agent_bridges.py`、`app/server_routes/agent_bridges.py`、provider bridge pytest/Node checks。
- 输入：TODO-041 的实现结果。
- 输出：Phase 14 测试记录，包含 Python 编译、结构性检查、Hermes/Codex/Claude bridge pytest/Node 子集、行数变化和失败归因。
- 依赖：TODO-041。
- 完成标准：Hermes native API、Codex server/runs/SSE/bridge、Claude Code server/runs/SSE 和相关 Node bridge/i18n checks 通过，或失败被明确标注并经用户确认。
- 关联 checklist：CHK-049。

### TODO-043：Phase 15 迁移 Agent Workspace / Skills Service（已完成）

- 目标：将 agent workspace、agent platform comm、agent create/delete 和 skills library 业务从 `app/server.py` 拆入独立 service/route。
- 涉及区域：`app/server.py`、`app/server_routes/agents.py`、`app/server_routes/skills.py`、`app/server_services/agents.py`、`app/server_services/skills.py`、agent workspace/skills 测试。
- 输入：agents list/create/delete、agent platform comm send/history、agent workspace update/context、skills library list/get/create/save-from-agent/delete/apply/upload 相关逻辑。
- 输出：agents/skills route 通过独立 service 执行业务逻辑；`server.py` 中对应函数体删除或降级为薄兼容导出。
- 依赖：TODO-042。
- 完成标准：agent workspace 数据边界、project context readonly、skills library 文件读写、agent create/delete 和 comm history 语义不变；行数变化已记录。
- 关联 checklist：CHK-050、CHK-051。

### TODO-044：Phase 15 测试闸门（已完成）

- 目标：验证 Agent Workspace / Skills 拆分完成且 workspace/skills 代表路径未回退，作为进入 Phase 16 的硬门禁。
- 涉及区域：`app/server_services/agents.py`、`app/server_services/skills.py`、`app/server_routes/agents.py`、`app/server_routes/skills.py`、agent workspace/skills pytest/Node/browser checks。
- 输入：TODO-043 的实现结果。
- 输出：Phase 15 测试记录，包含 Python 编译、结构性检查、agent workspace pytest/Node checks、skills library smoke、行数变化和失败归因。
- 依赖：TODO-043。
- 完成标准：`tests/test_agent_workspace_project_context.py`、`node tests/check_agent_workspace_project_context_readonly.mjs`、skills library 相关 UI/API smoke 和 Node full checks 通过，或失败被明确标注并经用户确认。
- 关联 checklist：CHK-051。

### TODO-045：Phase 16 迁移 Browser / Config / Status Runtime（已完成）

- 目标：将 browser runtime、setup/config/license/status 等低层运行时逻辑从 `app/server.py` 拆入独立 service/route。
- 涉及区域：`app/server.py`、`app/server_routes/browser.py`、`app/server_routes/config.py`、`app/server_services/browser_runtime.py`、`app/server_services/config_runtime.py`、settings/browser/status 测试。
- 输入：browser-status、browser-tabs、browser-controller、viewer probe/password/upstream、setup/save、vo-config、office-config、license、health/status、weather/config 相关路径和 helper。
- 输出：browser/config route 通过 service 执行业务逻辑；`server.py` 中对应函数体删除或降级为薄兼容导出。
- 依赖：TODO-044。
- 完成标准：浏览器状态、viewer URL、配置保存、license/status、weather/settings 响应字段和安全策略不变；行数变化已记录。
- 关联 checklist：CHK-052、CHK-053。

### TODO-046：Phase 16 测试闸门（已完成）

- 目标：验证 Browser / Config / Status Runtime 拆分完成且运行时配置代表路径未回退，作为进入 Phase 17 的硬门禁。
- 涉及区域：`app/server_services/browser_runtime.py`、`app/server_services/config_runtime.py`、`app/server_routes/browser.py`、`app/server_routes/config.py`、settings/browser/status tests。
- 输入：TODO-045 的实现结果。
- 输出：Phase 16 测试记录，包含 Python 编译、结构性检查、browser/settings/i18n Node checks、服务 smoke、行数变化和失败归因。
- 依赖：TODO-045。
- 完成标准：`node tests/test_browser_viewer_url.js`、`node tests/test_weather_location_test_ui.js`、`node tests/test_i18n_integrity.js`、`/health`、`/api/license`、`/browser-status` 和设置页 smoke 通过，或失败被明确标注并经用户确认。
- 关联 checklist：CHK-053。

### TODO-047：Phase 17 Server.py 收口与兼容层清理（已完成）

- 目标：收口 `app/server.py`，确认它只保留 startup、`OfficeHandler`、dispatch glue、兼容导出和少量无法独立的共享常量。
- 涉及区域：`app/server.py`、`app/server_routes/__init__.py`、`app/server_routes/*.py`、`app/server_services/*.py`、结构性测试。
- 输入：Phase 12-16 的迁移结果、旧 `server._handle_*`/`server._wf_*` 兼容需求、当前行数和顶层函数清单。
- 输出：`server.py` 残留函数清单、兼容导出清单、最终行数/函数数对比；删除可安全删除的重复 shim 和未使用 helper。
- 依赖：TODO-046。
- 完成标准：`server.py` 行数和顶层函数数量明显下降，目标约 8k-12k 行；若未达到，记录剩余原因和下一轮候选；所有已迁移 domain 不在 `server.py` 重复保留函数体。
- 关联 checklist：CHK-054、CHK-055。

### TODO-048：Phase 17 全量测试闸门与最终验收（已完成）

- 目标：验证 Phase 12-17 全部 Python 主服务瘦身闭环，确认继续拆分没有造成系统回归。
- 涉及区域：所有新增 Python route/service 模块、`app/server.py`、结构性测试、Python 全量、Node/浏览器全量、workflow e2e、CRUD shell、服务 smoke、需求验收记录。
- 输入：TODO-047 的实现结果。
- 输出：最终测试记录，包含 `py_compile`、结构性测试、`pytest` 全量、workflow e2e、Node/browser 全量、CRUD/smoke、最终行数对比和失败归因。
- 依赖：TODO-047。
- 完成标准：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`、`tests/test_workflow_e2e.py`、`tests/*.{js,mjs}`、CRUD shell 和服务 smoke 全部通过；失败项先修复或明确记录并等待用户确认；通过后仍等待用户确认 tested/done 再归档。
- 关联 checklist：CHK-055。
