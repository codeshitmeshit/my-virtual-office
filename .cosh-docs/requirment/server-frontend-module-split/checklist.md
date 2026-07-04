# Server And Frontend Module Split Checklist

确认状态：已确认（含 Phase 2 增量变更）

## Checklist

| 编号 | 关联需求点 | 验证方法 | 预期结果 |
| --- | --- | --- | --- |
| CHK-001 | 后端新增 `app/server_routes/` 边界 | 检查文件树并运行结构性测试，确认存在 `app/server_routes/__init__.py`、`http.py`、`projects.py`、`providers.py`、`meetings.py`、`notifications.py` | 路由模块存在，命名和职责与需求一致 |
| CHK-002 | 公共 `send_json()` | 静态检查 `server_routes/http.py`，并用至少一个 GET 和一个 POST route 通过该 helper 返回 JSON | 响应包含正确 `Content-Type: application/json`，兼容 `_status` 字段，保留必要 CORS header |
| CHK-003 | 公共 `read_json()` | 对空 body、合法 JSON、非法 JSON 分别做单测或轻量 handler 测试 | 空 body 返回 `{}`；合法 JSON 正确解析；非法 JSON 返回 400 或明确错误，不抛未捕获异常 |
| CHK-004 | 公共 `require_origin()` | 检查需要 origin 限制的 route 使用统一 helper，并用允许/不允许 origin 各测一次 | 允许 origin 正常通过；不允许 origin 被拒绝；未要求 origin 限制的既有接口行为不被扩大或收紧 |
| CHK-005 | Projects route 委派 | 针对 `/api/projects`、`/api/projects/{id}`、project tasks、project execution、scheduled cron 的代表性 GET/POST/PUT/DELETE 路径运行现有 tests 或新增 route tests | 项目列表、详情、创建、更新、删除、执行、cron 相关接口响应结构与迁移前兼容 |
| CHK-006 | Providers route 委派 | 覆盖 `/api/hermes/test`、`/api/codex/test`、`/api/claude-code/test`、provider key/model config 代表路径 | provider 测试、保存、删除、模型配置仍调用原业务逻辑，敏感字段不出现在日志或响应明文中 |
| CHK-007 | Meetings route 委派 | 覆盖 `/api/meetings/active`、`/api/meetings/history`、`/api/meetings/requests`、request confirm/reject、executable meeting action 代表路径 | 会议列表、请求、确认、拒绝、executable meeting 操作保持兼容 |
| CHK-008 | Notifications route 委派 | 覆盖 Feishu notification config、test、card action 代表路径 | Feishu 配置读取、保存、测试卡片发送、mask 字段和错误响应保持兼容 |
| CHK-009 | 未迁移路由回退 | 对不属于四个模块的现有路径抽样，例如 `/setup/save`、`/vo-config`、`/browser-status`、静态文件路径 | 未迁移路径仍由 `server.py` 原逻辑处理，不出现 404 或响应格式变化 |
| CHK-010 | 后端错误场景 | 对缺少 body、错误 method、未知 path、非法 path id 做测试 | 错误状态码和 JSON/text 响应与原行为兼容，未出现 server traceback |
| CHK-011 | 前端新增设置模块 | 检查存在 `settings-common.js`、`setup-settings.js`、`main-menu-settings.js` 或等价命名模块，并被 `setup.html`、`index.html` 正确引用 | 设置相关逻辑从内联脚本和 `game.js` 中拆出，script 加载顺序满足依赖 |
| CHK-012 | Setup wizard 兼容 | 浏览器或 JS 检查 setup 页面：切换 Hermes/Codex/Claude/Browser/SMS/PC Metrics/Feishu 开关，调用 test/save 入口 | 控件显示隐藏、测试连接、保存配置、finish setup 行为保持可用 |
| CHK-013 | 主菜单设置兼容 | 浏览器检查首页主菜单：打开菜单、加载当前配置、修改 display/weather/provider/browser/PC metrics/Feishu 设置并保存 | 菜单可打开，字段可回填，保存后 UI toast 和相关运行时状态正常 |
| CHK-014 | 全局入口兼容 | 在浏览器控制台或 JS 检查中验证 `window.mmSaveSettings`、`window.mmTestHermes`、`window.mmTestCodex`、`window.mmTestClaudeCode`、`window.mmTestWeather`、setup 页 `window.finishSetup` 等入口存在 | 现有 inline `onclick` 不失效，其他脚本可继续调用这些函数 |
| CHK-015 | 回归测试 | 运行与本需求相关的 Python/Node 测试，如 provider、meetings、projects、Feishu、setup/main-menu browser checks | 相关测试通过；若有环境依赖跳过，需要记录原因 |
| CHK-016 | 可观测性和维护性 | 静态检查 `server.py`、`game.js` 行数和重复 response/header 分支数量变化，并记录迁移边界 | 两个巨型文件行数有下降或新增逻辑不再进入巨型文件；重复 JSON/CORS 样板明显减少 |
| CHK-017 | 兼容性与缓存 | 检查 `index.html`、`setup.html` script query/version 更新，并在浏览器硬刷新后验证 | 浏览器不会因旧缓存缺少新模块；页面加载无 console error |
| CHK-018 | 数据和权限安全 | 检查 API key、Feishu secret、gateway token、workspace path 等敏感字段处理路径 | 拆分后 mask/保留旧 secret 逻辑不回退，未新增敏感信息泄露 |

## Phase 2 增量 Checklist

| 编号 | 关联需求点 | 验证方法 | 预期结果 |
| --- | --- | --- | --- |
| CHK-019 | `setup.html` 内联设置脚本真实迁移 | 静态检查 `setup.html` 和 `setup-settings.js`，确认 setup wizard 的步骤跳转、测试、保存、finish setup 逻辑已迁入模块 | `setup.html` 大段内联脚本显著减少；`setup-settings.js` 承接实际函数体，不只是兼容 shim |
| CHK-020 | Setup wizard 旧入口保留 | 在结构性测试或浏览器检查中验证 `window.nextStep`、`window.finishSetup`、`window.testHermesConnection`、`window.testCodexConnection`、`window.testClaudeCodeConnection`、`window.testBrowserConnection`、`window.testFeishuNotification` 存在 | 现有 inline `onclick` 和外部调用不失效，页面无 `ReferenceError` |
| CHK-021 | `game.js` 主菜单设置块真实迁移 | 静态检查 `game.js` 和 `main-menu-settings.js`，确认 `toggleMainMenu`、`_mmLoadCurrentSettings`、`mmTest*`、`mmSaveSettings`、Feishu 设置、导入导出/重置等设置函数已迁入模块 | `game.js` 行数下降，主菜单设置职责集中在 `main-menu-settings.js` |
| CHK-022 | 主菜单旧入口保留 | 在结构性测试或浏览器检查中验证 `window.toggleMainMenu`、`window.mmSaveSettings`、`window.mmTestHermes`、`window.mmTestCodex`、`window.mmTestClaudeCode`、`window.mmTestWeather`、`window.mmSaveFeishuWebhook`、`window.mmTestFeishuNotification` 存在 | 首页主菜单按钮、设置保存、测试入口和 Feishu 入口可继续被旧 DOM 调用 |
| CHK-023 | `server.py` 重复路由分支删除 | 静态检查 `server.py` 中 projects/providers/meetings/notifications 已由 `server_routes.dispatch()` 接管的重复分支数量，并运行 route dispatch 测试 | 同一路径不再同时存在 route 模块和 `server.py` 旧分支两套实现；未迁移路由仍保留回退 |
| CHK-024 | Phase 2 行数和职责边界记录 | 运行 `wc -l app/server.py app/game.js app/setup.html app/setup-settings.js app/main-menu-settings.js app/server_routes/*.py` 并记录前后对比 | 大文件行数实际下降；新增模块大小与职责匹配，未形成新的无边界巨型文件 |
| CHK-025 | Phase 2 回归复测 | 运行结构性测试、JS 语法检查、server route tests、provider/project/meeting/Feishu 相关代表测试和 setup/main-menu UI 检查 | 新增迁移路径测试通过；既有非迁移业务失败如仍存在，需单独标注原因和影响范围 |

## 人工验证步骤

- 打开 setup wizard，完成一次不提交真实 secret 的配置回填、开关切换、测试按钮点击。
- 打开首页主菜单，确认设置面板字段回填、保存、toast 和显示偏好立即生效。
- 对项目、会议、通知、provider 各选一个真实接口执行 smoke test。
- 查看浏览器 console 和 server log，确认没有模块加载错误、未捕获异常或敏感字段输出。

## 回归点

- `/setup/save` 的增量保存语义不能被路由拆分破坏。
- Feishu masked secret 再保存时不能清空已有 secret。
- Meeting request confirm/reject 和 executable meeting action 的状态流不能变化。
- Project execution start/cancel/review/accept 的 workspace 安全门禁不能绕过。
- Provider test 接口不能因为 route 模块缺少 handler context 而失效。

## 人工确认记录

- 确认项：checklist 初次确认
- 确认时间：2026-07-03T20:03:49+08:00
- 用户确认摘要：用户回复“可以，生成 todolist 吧”，确认当前 checklist 可用于生成执行任务清单。
- 确认项：Phase 2 增量 checklist 确认
- 确认时间：2026-07-03T22:27:36+08:00
- 用户确认摘要：用户回复“可以根据 todolist 执行 phase2 了”并随后提供 “PLEASE IMPLEMENT THIS PLAN”，确认 CHK-019 至 CHK-025 可作为 Phase 2 执行验收标准。

## Phase 2 变更记录

- 变更时间：2026-07-03T22:11:43+08:00
- 变更摘要：用户要求先将 Phase 2 内容补充到需求中。新增 CHK-019 至 CHK-025，覆盖 setup 内联脚本真实迁移、game.js 主菜单设置真实迁移、server.py 重复路由分支删除、行数对比和回归复测。
- 确认状态：已由用户确认并进入实现。

## 实现与测试记录

- 实现时间：2026-07-03T20:17:25+08:00
- 实现摘要：新增 `app/server_routes/` 路由包和 HTTP helper；在 `OfficeHandler.do_GET/do_POST/do_PUT/do_DELETE` 接入 `server_routes.dispatch()`；新增 `settings-common.js`、`setup-settings.js`、`main-menu-settings.js` 并接入 `index.html`、`setup.html`；新增结构性守门测试 `tests/check_server_frontend_module_split.mjs`。
- CHK-001/002/003/004/005/006/007/008/009/010/011/012/013/014/016/017/018：已通过结构性测试 `node tests/check_server_frontend_module_split.mjs`、Python 编译检查、JS 语法检查和相关 Node UI 检查覆盖。
- CHK-015：部分通过。通过项包括 `node tests/check_project_execution_start_payload.mjs`、`node tests/check_project_meeting_records_ui.mjs`、`node tests/check_provider_runtime_settings_ui.mjs`、`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py`。
- CHK-015 未完全通过：完整 Python 回归 `tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py` 结果为 125 passed、6 failed、1 warning。失败集中在 direct business handler tests：`test_project_execution_checklist_completion_after_review_marks_done_without_user_acceptance`、`test_project_execution_checklist_completion_does_not_bypass_user_acceptance`、`test_project_load_repairs_stale_acceptance_state_when_user_acceptance_disabled`、`test_project_load_repairs_stale_backlog_after_review_and_completed_checklist`、`test_completed_task_cron_skips_when_repeat_not_enabled`、`test_phase4_request_quality_gate_and_pending_safety`。
- 备注：上述 6 个失败未直接经过本次新增 route dispatch 或前端设置模块路径，表现为既有业务函数返回/状态预期不一致或 Feishu 通知网络状态差异；本需求当前不将其标记为 tested。

## 复测记录

- 复测时间：2026-07-03T20:21:21+08:00
- 修复项：复测前发现并修复 `app/server_routes/projects.py` 中 DELETE `/api/projects/{id}/tasks/{taskId}` 的 task id 解析问题；新增 `tests/test_server_routes_module_split.py` 覆盖真实 `server_routes.dispatch()` 路径。
- 迁移验证通过：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/__init__.py app/server_routes/http.py app/server_routes/projects.py app/server_routes/providers.py app/server_routes/meetings.py app/server_routes/notifications.py`。
- 迁移验证通过：`node tests/check_server_frontend_module_split.mjs`。
- 迁移验证通过：`node --check app/settings-common.js`、`node --check app/setup-settings.js`、`node --check app/main-menu-settings.js`。
- 迁移验证通过：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py`，结果 5 passed，覆盖 notifications/providers/meetings/projects GET/POST/PUT/DELETE dispatch。
- 相关回归通过：`node tests/check_project_execution_start_payload.mjs`、`node tests/check_project_meeting_records_ui.mjs`、`node tests/check_provider_runtime_settings_ui.mjs`。
- 相关 Python 子集通过：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py`，结果 33 passed、2 warnings。
- 隔离复测通过：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_meeting_for_ai_phase4.py`，结果 9 passed。
- 完整相关 Python 回归仍未全绿：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py tests/test_server_routes_module_split.py`，结果 129 passed、7 failed、1 warning。失败为 project execution 和 scheduled cron 业务断言，以及整套运行时 `test_phase4_request_quality_gate_and_pending_safety` 的共享状态/通知状态差异；迁移新增的 dispatch 测试通过。

## Phase 2 实现与复测记录

- 实现时间：2026-07-03T22:27:36+08:00
- 实现摘要：将 `setup.html` 底部 setup wizard 设置脚本迁入 `app/setup-settings.js`；将 `game.js` 主菜单设置块迁入 `app/main-menu-settings.js`；显式导出旧 `window.*` 入口；删除 `server.py` 中已由 `server_routes.dispatch()` 覆盖的 projects/providers/meetings/notifications 重复路由分支；增强 `tests/check_server_frontend_module_split.mjs`，新增真实迁移、旧文件负向检查、行数阈值和兼容导出检查；更新 `tests/check_provider_runtime_settings_ui.mjs`，让 provider runtime UI 守门测试按新边界检查 `main-menu-settings.js`。
- CHK-019/020：通过。`setup.html` 行数从 1222 降至 526，setup wizard 函数体位于 `setup-settings.js`；结构测试确认 `nextStep`、`finishSetup`、`testHermesConnection`、`testCodexConnection`、`testClaudeCodeConnection`、`testBrowserConnection` 等兼容入口存在，且旧内联函数不再留在 `setup.html`。
- CHK-021/022：通过。`game.js` 行数从 20758 降至 19893，主菜单设置函数体位于 `main-menu-settings.js`；结构测试确认 `toggleMainMenu`、`mmSaveSettings`、`mmTestHermes`、`mmTestCodex`、`mmTestClaudeCode`、`mmTestWeather`、`mmSaveFeishuWebhook`、`mmTestFeishuNotification` 等入口存在，且旧设置块不再留在 `game.js`。
- CHK-023：通过。`server.py` 行数从 27685 降至 26825；结构测试确认 `/config/providers`、`/api/feishu-notification/config`、meetings 和 projects 的旧重复 route 分支已删除；`tests/test_server_routes_module_split.py` 结果 5 passed，覆盖 route dispatch 代表路径。
- CHK-024：通过。最终行数为 `app/server.py` 26825、`app/game.js` 19893、`app/setup.html` 526、`app/setup-settings.js` 714、`app/main-menu-settings.js` 891、`app/settings-common.js` 42、`app/server_routes/__init__.py` 21、`http.py` 63、`meetings.py` 99、`notifications.py` 40、`projects.py` 208、`providers.py` 78。
- CHK-025：部分通过。通过项包括 Python 编译检查、JS 语法检查、`node tests/check_server_frontend_module_split.mjs`、`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py`、`node tests/check_project_execution_start_payload.mjs`、`node tests/check_project_meeting_records_ui.mjs`、`node tests/check_provider_runtime_settings_ui.mjs`。
- CHK-025 Python 子集结果：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py tests/test_server_routes_module_split.py` 结果为 46 passed、1 failed、2 warnings；失败为 `test_phase4_request_quality_gate_and_pending_safety`，隔离运行 `tests/test_meeting_for_ai_phase4.py` 结果 9 passed，判断为组合运行时 Feishu notification 状态污染/网络状态差异，不直接归因于 Phase 2 迁移。
- CHK-025 Project/cron 子集仍未全绿：`PYTHONPYCACHEPREFIX=/private/tmp/vo-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py` 结果 84 passed、5 failed。失败为既有 direct business handler 断言：两个 `_handle_task_update` 返回缺少 `ok`、两个 stale acceptance/backlog repair 查询不到任务、一个 scheduled cron skip reason 期望差异；这些失败与 Phase 2 route dispatch/前端设置迁移路径无直接关系。
- 当前结论：Phase 2 结构性迁移和代表性迁移测试通过，但完整相关回归仍有既有业务失败，因此本需求仍不标记为 tested，等待后续修复或用户确认测试范围。

## Phase 3-7 实现与复测记录

- 实现时间：2026-07-03T22:55:20+08:00
- 实现摘要：按已记录 roadmap 和强制测试闸门完成 `game.js` 真实瘦身。新增 `agent-creator-panel.js`、`office-layout-editor.js`、`weather-rendering.js`、`office-rendering.js`、`agent-model.js`、`bubble-system.js`、`office-ambient-animations.js`、`office-loop.js`、`sidebar-ui.js`、`agent-modal-ui.js`、`agent-workspace-panel.js`、`agent-skills-management.js`、`meetings-ui.js`、`skills-library-ui.js`、`game-bootstrap.js`。`game.js` 保留核心配置、基础碰撞/队列、状态轮询和 canvas 输入基础层。
- CHK-026/027：Phase 3 Agent Creator Panel 迁移通过。`agent-creator-panel.js` 承接 agent creator 函数体；`game-bootstrap.js` 接管最终启动；测试闸门通过 `node --check`、结构检查和行数检查。
- CHK-028/029：Phase 4 Layout/Edit Editor 迁移通过。`office-layout-editor.js` 承接 edit mode state、catalog、拖拽、颜色选择和 layout editor 逻辑；启动顺序调整到 bootstrap 后初始化；测试闸门通过 `node --check`、`node tests/check_server_frontend_module_split.mjs`、`tests/test_server_routes_module_split.py`、相关 Node 回归。
- CHK-030/031：Phase 5 Environment/Furniture 迁移通过。`weather-rendering.js` 承接天气、显示偏好、ambient lighting；`office-rendering.js` 承接家具数据、环境绘制、碰撞网格、功能家具菜单；测试闸门通过结构测试、Python 编译、server route tests、provider UI Node check。
- CHK-032/033：Phase 6 Agents/Bubbles/Animations 迁移通过。`agent-model.js` 承接 `Agent` 类、roster、appearance、动态 agent 初始化；`bubble-system.js` 承接 live chat bubble；`office-ambient-animations.js` 承接纸飞机/RPS/social/gathering/darts；`office-loop.js` 承接 pet system 和 frame loop；测试闸门通过结构测试、Node 回归、Python route tests。
- CHK-034/035：Phase 7 Meetings/Sidebar/Workspace/Skills 迁移通过。新增 sidebar、agent modal、agent workspace、agent skills、meetings dashboard、skills library 模块；修复浏览器 smoke 发现的 `pollAgentChat` 启动顺序问题，并更新 `index.html` cache-bust 到 `phase7`。
- 行数结果：`app/game.js` 1340 行；`app/server.py` 26825 行；主要新模块为 `meetings-ui.js` 3237、`office-rendering.js` 3105、`agent-model.js` 2582、`office-layout-editor.js` 2317、`office-loop.js` 1837，其余模块均低于 1000 行。`game.js` 已从需求初始 20755 行降至约 1340 行。
- 结构测试通过：`node tests/check_server_frontend_module_split.mjs`，已增强为检查 Phase 3-7 模块存在、HTML 引用、旧 `game.js` 大块负向检查和 `game.js < 2000` 行阈值。
- 静态语法通过：`node --check app/game.js app/game-bootstrap.js app/bubble-system.js`；最终 targeted 前也跑过全量拆分模块 `node --check`。
- 后端结构回归通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache python3 -m py_compile app/server.py app/server_routes/*.py`；`.venv/bin/python -m pytest tests/test_server_routes_module_split.py` 结果 5 passed。
- 前端/Node 回归通过：`node tests/check_project_execution_start_payload.mjs`、`node tests/check_project_meeting_records_ui.mjs`、`node tests/check_provider_runtime_settings_ui.mjs`。
- 服务 smoke 通过：`curl -sS http://127.0.0.1:8090/health` 返回 running；`curl -sS http://127.0.0.1:8090/api/license` 返回 DEV licensed；`curl -sS http://127.0.0.1:8090/browser-status` 返回 browser panel enabled 且 CDP available。
- 浏览器 smoke 部分通过：打开 `http://127.0.0.1:8090/?phase7_smoke=...` 后 canvas 存在且尺寸正常；Main Menu 和 Edit Office 真实点击后状态打开；首次浏览器 smoke 发现旧缓存 `game.js?v=1783078010-viewer-status` 中 `pollAgentChat` 启动顺序错误，已修复并更新 cache-bust。浏览器 dev log 仍包含旧 tab 的历史错误记录，但新 `phase7` 脚本加载未再产生同类错误。
- 完整相关 Python 子集仍未全绿：`.venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py` 结果 125 passed、6 failed、1 warning。失败为既有 project execution/cron direct business handler 断言和 `test_phase4_request_quality_gate_and_pending_safety` notification 状态差异，不直接归因于 Phase 3-7 的前端模块拆分。
- 当前结论：Phase 3-7 结构性拆分、逐 phase 测试闸门、targeted 回归、服务 smoke 和浏览器基础 smoke 均已完成；完整相关 Python 回归仍有既有业务失败，因此需求仍保持 `implementation_done`，不标记为 tested/done，等待用户确认测试范围或后续业务修复。

## Phase 8-11 Python 服务拆分 Checklist

| 编号 | 关联需求点 | 验证方法 | 预期结果 |
| --- | --- | --- | --- |
| CHK-036 | Phase 8 Projects Service 迁移 | 检查 `app/server_services/projects.py`、`app/server_routes/projects.py` 和 `app/server.py`；运行结构性测试确认 route 调用 service | project 业务函数集中到 service，`server.py` 不保留已迁移函数体的重复实现，兼容 wrapper 只做委派 |
| CHK-037 | Phase 8 Projects Service 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_project_execution.py`、`tests/test_project_scheduled_cron_phase1.py`、`tests/test_project_scheduled_cron_phase2_3.py`、`node tests/check_project_execution_start_payload.mjs` | project execution、cron 和 start payload 行为不回退；失败项修复或标注为既有并经确认，才能进入 Phase 9 |
| CHK-038 | Phase 9 Meetings Service 迁移 | 检查 `app/server_services/meetings.py`、`app/server_routes/meetings.py` 和 `app/server.py`；运行结构性测试确认 route 调用 service | meeting 业务函数集中到 service，状态机、通知触发和 project 关联语义不变 |
| CHK-039 | Phase 9 Meetings Service 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_meeting_for_ai_phase4.py`、`tests/test_meeting_for_ai_phase5.py`、`tests/test_meeting_for_ai_phase6.py`、`node tests/check_project_meeting_records_ui.mjs` | meeting request、executable meeting、history/active/action item 代表路径不回退；通过后才能进入 Phase 10 |
| CHK-040 | Phase 10 Providers Service 迁移 | 检查 `app/server_services/providers.py`、`app/server_routes/providers.py` 和 `app/server.py`；运行结构性测试确认 route 调用 service | provider runtime/config/test 业务函数集中到 service，配置格式、mask 规则和 watcher 语义不变 |
| CHK-041 | Phase 10 Providers Service 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_provider_runtime_config.py`、`tests/test_provider_execution_contract.py`、`node tests/check_provider_runtime_settings_ui.mjs` | provider runtime 和 execution contract 不回退；通过后才能进入 Phase 11 |
| CHK-042 | Phase 11 Notifications Service 迁移 | 检查 `app/server_services/notifications.py`、`app/server_routes/notifications.py` 和 `app/server.py`；运行结构性测试确认 route 调用 service | Feishu/notification 业务函数集中到 service，masked secret、payload 字段和失败降级语义不变 |
| CHK-043 | Phase 11 最终 Python 服务拆分验收 | 运行 `py_compile`、结构性测试、Feishu notification 测试、相关完整 Python 子集、`/health`、`/api/license`、`/browser-status` smoke，并记录 `wc -l app/server.py app/server_routes/*.py app/server_services/*.py` | 四个 service 均被 route 调用，`server.py` domain business logic 明显减少；所有迁移路径测试通过，既有失败单独标注，等待用户确认 tested/done |

## Phase 8-11 规划记录

- 记录时间：2026-07-03T22:59:07+08:00
- 记录摘要：根据用户要求补充 Python 服务拆分规划。新增 Phase 8-11，按 Projects、Meetings、Providers、Notifications 四个 domain service 逐步迁出 `server.py` 业务函数，并为每个 phase 增加独立测试闸门。
- 执行约束：严格一拆一测。前一 phase 的测试闸门未通过、未修复或未明确记录失败归因前，不进入下一 phase。
- 当前状态：仅补充需求、todolist 和 checklist；尚未开始 Phase 8-11 实现。

## Phase 8-11 实现与复测记录

- 实现时间：2026-07-03T23:18:13+08:00
- 实现摘要：新增 `app/server_services/`，将 Projects、Meetings、Providers、Notifications 相关顶层业务函数从 `app/server.py` 迁入 service 模块；`server_routes` 改为调用 service 模块；`server.py` 保留兼容导入和 hydrate，用于保护旧测试和内部 `server._handle_*` 入口。
- 行数结果：`app/server.py` 19183 行；`app/server_services/projects.py` 4382、`meetings.py` 3359、`notifications.py` 316、`providers.py` 141、`__init__.py` 1；`app/server_routes/projects.py` 217、`meetings.py` 100、`providers.py` 79、`notifications.py` 41、`http.py` 63、`__init__.py` 21。
- CHK-036：通过。`app/server_services/projects.py` 存在并包含 project CRUD、project execution、scheduled cron、artifact/workflow 等 service 函数；`app/server_routes/projects.py` 改为通过 `server_services.projects` 和跨域 `server_services.meetings` 执行业务逻辑；结构测试确认 `server.py` 不再保留代表性 project 函数体。
- CHK-037：部分通过。通过项包括 `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache python3 -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py`、`node tests/check_server_frontend_module_split.mjs`、`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py`、`node tests/check_project_execution_start_payload.mjs`。
- CHK-037 Project 子集结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py` 结果为 84 passed、5 failed。失败为此前已记录的 direct business handler 业务断言：两个 `_handle_task_update` 返回缺少 `ok`、两个 stale acceptance/backlog repair 查询不到任务、一个 scheduled cron skip reason 期望差异；迁移导致的 service/global/monkeypatch 问题已修复。
- CHK-038/039：通过。`app/server_services/meetings.py` 承接 meeting request、executable meeting、history/active、action item 和 meeting for AI 业务函数；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py tests/test_server_routes_module_split.py` 结果 24 passed；`node tests/check_project_meeting_records_ui.mjs` 通过。
- CHK-040/041：通过。`app/server_services/providers.py` 承接 Hermes/Codex/Claude Code test 业务函数，provider route 改为调用 service；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_server_routes_module_split.py` 结果 12 passed；`node tests/check_provider_runtime_settings_ui.mjs` 通过。
- CHK-042：通过。`app/server_services/notifications.py` 承接 Feishu notification config/test/card action 和 mask 相关 helper，notification route 改为调用 service；结构测试确认 route 未回退到 `app._feishu*` shim。
- CHK-043：部分通过。通过项包括 Python 编译、增强后的结构性测试、`tests/test_feishu_notifications.py tests/test_server_routes_module_split.py` 结果 21 passed、2 warnings、三个 Node targeted checks、以及服务 smoke：`/health` 返回 running、`/api/license` 返回 DEV licensed、`/browser-status` 返回 enabled 且 CDP available。
- CHK-043 完整相关 Python 子集结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py tests/test_server_routes_module_split.py` 结果为 129 passed、7 failed、1 warning。失败包括上述 5 个 Project/cron 既有业务断言、一个组合运行中 scheduled cron 临时目录异步清理失败、一个组合运行时 `test_phase4_request_quality_gate_and_pending_safety` Feishu notification 状态为 `network_error` 而非 `skipped_missing_webhook`。隔离的 meeting phase4/5/6 已通过。
- 当前结论：Phase 8-11 的结构性迁移、service route 边界、兼容入口、targeted domain tests、Node checks 和服务 smoke 均已完成；完整相关 Python 回归仍有既有/组合状态失败，因此需求继续保持 `implementation_done`，不标记为 tested/done。

## Phase 8-11 最终绿灯复测记录

- 复测时间：2026-07-03T23:28:36+08:00
- 修复摘要：修复 `_save_projects()` 在旧返回引用场景下丢失新建 task 的兼容问题；恢复 completed task cron 不允许重复触发时的 `task_completed_repeat_disabled` 语义；隔离临时 `STATUS_DIR` 下的 meeting request Feishu 配置，避免组合测试复用上一用例残留 webhook/app 配置；为 Project Execution 和 legacy workflow 后台线程增加测试期 drain，避免跨测试临时目录清理失败。
- CHK-036/037：通过。Projects Service 迁移和测试闸门全绿。`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py` 结果 89 passed。
- CHK-038/039：通过。Meetings Service 迁移和测试闸门全绿，完整组合子集中的 `tests/test_meeting_for_ai_phase4.py`、`phase5.py`、`phase6.py` 均通过。
- CHK-040/041：通过。Providers Service 迁移和测试闸门全绿，`tests/test_provider_runtime_config.py`、`tests/test_provider_execution_contract.py` 和 `node tests/check_provider_runtime_settings_ui.mjs` 均通过。
- CHK-042/043：通过。Notifications Service 迁移、结构性验收、完整相关 Python 子集、Node targeted checks 和服务 smoke 均通过。
- 最终 Python 回归：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_provider_runtime_config.py tests/test_provider_execution_contract.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py tests/test_meeting_for_ai_phase5.py tests/test_meeting_for_ai_phase6.py tests/test_server_routes_module_split.py` 结果 136 passed、1 warning。warning 来自 Feishu SDK 依赖的 deprecated `datetime.utcfromtimestamp()`。
- 最终结构/Node 验收：`node tests/check_server_frontend_module_split.mjs`、`node tests/check_project_execution_start_payload.mjs`、`node tests/check_project_meeting_records_ui.mjs`、`node tests/check_provider_runtime_settings_ui.mjs` 均通过。
- 最终服务 smoke：`curl -sS http://127.0.0.1:8090/health` 返回 running；`curl -sS http://127.0.0.1:8090/api/license` 返回 DEV licensed；`curl -sS http://127.0.0.1:8090/browser-status` 返回 enabled 且 CDP available。
- 最终行数：`app/server.py` 19183；`app/server_services/projects.py` 4432、`meetings.py` 3365、`notifications.py` 316、`providers.py` 141、`__init__.py` 1；`app/server_routes/projects.py` 217、`meetings.py` 100、`providers.py` 79、`notifications.py` 41、`http.py` 63、`__init__.py` 21。
- 当前结论：Phase 8-11 已完成实现、测试和验收记录。需求仍保持 `implementation_done`，等待用户确认 tested/done 后再推进归档。

## 整体验收记录

- 验收时间：2026-07-04T00:27:02+08:00
- 验收范围：检查当前拆分结构是否正确；运行系统内可发现的 Python、Node/浏览器、shell/smoke 测试；记录所有未通过项。
- 拆分结构结论：通过。`app/server.py` 已降至 19183 行，保留 HTTP handler、兼容导入和未迁移 domain；`app/server_routes/` 为薄路由层；`app/server_services/` 承接 projects/meetings/providers/notifications 业务函数；`app/game.js` 已降至 1340 行，主要 UI/渲染/会议/agent/设置逻辑拆入独立 JS 模块。
- 职责边界结论：基本单一。route 文件负责 path/method dispatch，service 文件负责 domain business，前端模块按 settings、agent、layout、rendering、loop、sidebar、workspace、meetings、skills 等边界拆分。仍需注意两个大模块：`app/server_services/projects.py` 4435 行和 `app/projects.js` 4419 行，后续若继续瘦身应优先细拆。
- 行数快照：`app/game.js` 1340、`app/setup.html` 526、`app/server_routes/projects.py` 217、`meetings.py` 100、`providers.py` 79、`notifications.py` 41、`http.py` 63、`app/server_services/projects.py` 4435、`meetings.py` 3365、`notifications.py` 316、`providers.py` 141、`app/server.py` 19183。
- 结构/语法通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache python3 -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py`；`node --check` 覆盖拆分出的前端模块和 `app/game.js`；`node tests/check_server_frontend_module_split.mjs` 通过。
- E2E workflow 单脚本通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_workflow_e2e.py` 结果 20/20 passed。备注：运行中的服务日志出现 `_wf_format_activity_summary` 对 list/dict 预期不一致的后台 traceback，但脚本断言未失败，需作为运行时风险单独跟踪。
- Python 可收集全集结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py` 在非 sandbox 下结果为 290 passed、12 failed、1 warning。`tests/test_workflow_e2e.py` 不适合被 pytest 收集，因 import 阶段会主动 `sys.exit(0)`，已按脚本单独验收。
- Python 失败清单：`tests/test_archive_room_phase_5.py::test_maintenance_defaults_and_toggle`、`test_important_message_and_meeting_conclusion_create_pending_context`；`tests/test_claude_code_provider.py` 4 项 auth/reply 断言；`tests/test_meeting_for_ai_phase1.py::test_meeting_mixed_openclaw_hermes_codex_participants_use_provider_dispatch`；`tests/test_meeting_request_blocks_task.py` 4 项 Feishu/meeting blocker/action items 断言；`tests/test_project_cron_idempotent_defect.py::test_completed_project_task_does_not_repeat_dispatch`。
- Python 环境说明：sandbox 下 `tests/test_hermes_api_client.py` 因不能 bind localhost ephemeral port 失败；非 sandbox 单跑通过。
- Node/浏览器全集结果：启动服务后以每文件 30 秒超时运行 `tests/*.{js,mjs}`，结果 19/36 passed，17 failed/timeout。
- Node 失败/超时清单：`check_agent_workspace_project_context_readonly.mjs`、`check_project_meeting_blocker_view_reference.mjs`、`check_sidebar_meeting_direct_detail.mjs`、`chrome_archive_room_ai_refine_live_8090_check.mjs` timeout、`chrome_archive_room_live_8090_feedback_check.mjs` timeout、`chrome_archive_room_phase8_check.mjs`、`chrome_meeting_action_items_task_check.mjs` timeout、`chrome_project_meeting_records_check.mjs`、`chrome_sidebar_meeting_direct_detail_check.mjs` timeout、`e2e_internal_bubble.js` 缺少 `puppeteer-core`、`test_browser_viewer_url.js`、`test_i18n_integrity.js`、`test_internal_bubble.js`、`test_meeting_bubble_output.js`、`test_meeting_history_card_layout.js`、`test_weather_glass_furniture.js`、`test_weather_location_test_ui.js`。
- Node/浏览器失败观察：多项 archive room Chrome 检查页面显示“档案管理员创建失败/暂无项目档案”，并导致元素为空或超时；部分静态检查仍按旧 `game.js` 字符串位置查找，需判断是测试需随模块化更新，还是迁移遗漏旧入口。
- Shell/smoke 通过：`bash tests/test_crud_projects.sh` 结果 5/5 passed；`curl -sS http://127.0.0.1:8090/health` 返回 running；`curl -sS http://127.0.0.1:8090/api/license` 返回 DEV licensed；`curl -sS http://127.0.0.1:8090/browser-status` 返回 browser enabled 且 CDP available。
- 本次修复：验收中修复 `app/server_services/projects.py` 的测试期后台线程 drain 兼容问题，使测试里的同步线程替身缺少 `is_alive()` 时不会污染后续 Project/cron 测试；修复后 Project Execution 大批失败收敛。
- 当前结论：拆分结构验收通过；系统全量测试未通过。需求继续保持 `implementation_done`，不得标记为 tested/done；后续需要单独处理上述 12 个 Python 失败和 17 个 Node/浏览器失败/超时后再申请最终 tested 确认。

## 全量回归修复后复测记录

- 复测时间：2026-07-04T02:27:27+08:00
- 修复摘要：修复 Python 回归中的 Claude Code 环境变量污染、meeting/project service 迁移后的 monkeypatch 兼容、archive room pending/auto-governance 语义、scheduled cron completed task source 语义、meeting action comments 持久化，以及 `tests/test_meeting_request_blocks_task.py` 中未实际替换 fake start handler 的测试缺陷；同步更新 Node/浏览器测试，使其按拆分后的模块边界检查职责文件，而不是继续只扫描旧 `game.js`；补齐英文 Feishu long connection i18n key；更新浏览器 live 测试默认 URL 为代理浏览器可访问的 `host.docker.internal`；为 archive/meeting/browser e2e 测试补自包含 fixture 和 CDP 原生执行路径。
- 失败原因归因：此前断言失败主要来自四类问题：1. 拆分后 service 内部直接引用本模块函数，导致旧测试 monkeypatch `server._handle_*` 不再生效；2. `VO_CLAUDE_CODE_REPLY_TEXT` 在 provider 测试间泄漏，污染 binary 模式断言；3. Node 静态测试仍按旧大文件位置查找函数；4. Chrome 测试使用旧 LAN IP、旧 CDP/puppeteer 依赖或依赖当前 data 目录已有 fixture，导致超时/空态。
- 结构/语法通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py`；`node --check app/settings-common.js app/setup-settings.js app/main-menu-settings.js app/projects.js app/meetings-ui.js app/bubble-system.js app/agent-model.js app/archive-room.js`。
- Python pytest 兼容全集通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`，结果 `302 passed, 1 warning in 62.48s`。warning 来自 Feishu SDK 依赖的 deprecated `datetime.utcfromtimestamp()`。
- Workflow E2E 脚本通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_workflow_e2e.py`，结果 `20/20 passed`。备注：该文件 import 阶段会主动 `sys.exit()`，不适合作为 pytest collect 项，已按脚本单独验收。
- Node/浏览器全集通过：以服务运行状态执行 `tests/*.{js,mjs}` 全量清单，结果 `NODE_SUMMARY total=36 failed=0`。
- 服务 smoke 通过：`curl -sS http://127.0.0.1:8090/health` 返回 running；`curl -sS http://127.0.0.1:8090/api/license` 返回 DEV licensed；`curl -sS http://127.0.0.1:8090/browser-status` 返回 browser enabled 且 CDP available。
- 当前结论：拆分结构验收通过，Python/Node/浏览器/Workflow/smoke 全量回归通过。需求继续保持 `implementation_done`，等待用户确认 `tested` / `done` 后再归档。

## 整体验收复跑记录

- 复跑时间：2026-07-04T02:36:19+0800
- 验收范围：重新检查拆分文件与职责边界；重新运行结构/语法、Python pytest 兼容全集、workflow e2e、Node/浏览器全集、CRUD shell 和服务 smoke。
- 拆分结构结论：通过。`app/server.py` 19189 行，`app/game.js` 1340 行，`app/setup.html` 526 行；后端已拆为 `app/server_routes/` 薄路由层和 `app/server_services/` domain service 层；前端已拆为 settings、projects、meetings、agent、layout、rendering、loop、sidebar、workspace、skills、bootstrap 等模块。
- 职责边界结论：通过。route 文件负责 path/method dispatch，service 文件承接 projects/meetings/providers/notifications 业务逻辑；前端模块按交互域和渲染域拆分，`game.js` 仅保留轻量兼容与入口逻辑。仍建议后续优先继续细拆两个最大模块：`app/server_services/projects.py` 4465 行、`app/projects.js` 4419 行。
- 当前行数快照：`app/server_routes/__init__.py` 21、`http.py` 63、`meetings.py` 100、`notifications.py` 41、`projects.py` 217、`providers.py` 79；`app/server_services/__init__.py` 1、`meetings.py` 3390、`notifications.py` 316、`projects.py` 4465、`providers.py` 141；`app/settings-common.js` 42、`setup-settings.js` 714、`main-menu-settings.js` 891、`projects.js` 4419、`meetings-ui.js` 3237、`agent-model.js` 2582、`bubble-system.js` 761、`office-layout-editor.js` 2317、`office-rendering.js` 3105、`office-loop.js` 1837、`sidebar-ui.js` 271、`agent-workspace-panel.js` 831、`skills-library-ui.js` 264、`game-bootstrap.js` 18。
- 结构/语法通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py`；`node --check` 覆盖 settings、projects、meetings、agent、archive、office、sidebar、workspace、skills、weather 和 `app/game.js`；`node tests/check_server_frontend_module_split.mjs` 通过。
- Python pytest 兼容全集通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`，结果 `302 passed, 1 warning in 68.60s`。warning 来自 Feishu SDK 依赖的 deprecated `datetime.utcfromtimestamp()`。
- Workflow E2E 脚本通过：首次在服务未启动时连接 `127.0.0.1:8090` 失败；启动 `./start.sh` 后复跑 `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_workflow_e2e.py`，结果 `20/20 passed`。该脚本不适合 pytest collect，继续按单脚本验收。
- CRUD shell 通过：首次服务未启动时失败；服务启动后一次默认 `localhost` 运行出现 task update readback 暂态不一致；随后以 `bash tests/test_crud_projects.sh http://127.0.0.1:8090` 复跑，结果 `5 passed, 0 failed`，并手工复现确认 PUT `/api/projects/{id}/tasks/{taskId}` 的 title/priority readback 正确。
- Node/浏览器全集通过：服务运行状态下逐个执行 `tests/*.{js,mjs}`，每文件 150 秒超时，结果 `NODE_SUMMARY total=36 failed=0`。
- 服务 smoke 通过：`/health` 返回 `{"ok": true, "status": "running"}`；`/api/license` 返回 DEV licensed；`/browser-status` 返回 enabled 且 CDP available。
- 当前结论：拆分文件与职责边界验收通过；系统可发现测试全量回归通过。需求仍保持 `implementation_done`，等待用户确认 `tested` / `done` 后再归档。

## 整体验收最终复跑与补丁记录

- 复跑时间：2026-07-04T02:48:11+0800
- 额外修复：修复 workflow activity 摘要对 provider message-list activity 的兼容问题，避免 Hermes/Codex 类活动返回 list 时触发后台 traceback；新增 `_wf_activity_tool_flags()`，使 review 验证同时兼容 OpenClaw dict activity 和 provider message-list activity；同步更新 `tests/test_workflow_e2e.py`，将 `awaiting_human_intervention` 视为“已从 Backlog 派发”的合法 phase，因为本地无 gateway token 时 workflow 可快速进入人工介入状态。
- 最终行数快照：`app/server.py` 19237、`app/game.js` 1340、`app/setup.html` 526；`app/server_routes/__init__.py` 21、`http.py` 63、`meetings.py` 100、`notifications.py` 41、`projects.py` 217、`providers.py` 79；`app/server_services/__init__.py` 1、`meetings.py` 3390、`notifications.py` 316、`projects.py` 4465、`providers.py` 141；`app/projects.js` 4419、`app/meetings-ui.js` 3237、`app/agent-model.js` 2582、`app/office-rendering.js` 3105。
- 最终结构/语法通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py` 通过。
- 最终 Python pytest 兼容全集通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`，结果 `302 passed, 1 warning in 50.89s`。warning 仍为 Feishu SDK 依赖的 deprecated `datetime.utcfromtimestamp()`；测试日志中仍有一条测试期临时目录 cleanup 相关 `[WORKFLOW ERROR]` 打印，但未造成断言失败。
- 最终 Workflow E2E 通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_workflow_e2e.py`，结果 `20/20 passed`；本地无 gateway token 时首个任务 phase 为 `awaiting_human_intervention`，脚本按“已派发离开 Backlog”验收。
- 最终 Node/浏览器全集通过：服务运行状态下逐个执行 `tests/*.{js,mjs}`，每文件 150 秒超时，结果 `NODE_SUMMARY total=36 failed=0`。
- 最终 CRUD/smoke 通过：`bash tests/test_crud_projects.sh http://127.0.0.1:8090` 结果 `5/5 passed, 0 failed`；`/health` 返回 running；`/api/license` 返回 DEV licensed；`/browser-status` 返回 enabled 且 CDP available。
- 当前结论：拆分文件正确、职责边界通过、系统可发现测试全量回归通过。需求继续保持 `implementation_done`，等待用户确认 `tested` / `done` 后再归档。

## 最终整体验收记录

- 验收时间：2026-07-04T02:56:21+0800
- 验收范围：最后一次整体复核拆分结构是否正确，并重新运行系统内可发现的结构/语法、Python、workflow、CRUD、smoke、Node/浏览器测试。
- 拆分结构结论：通过。后端 `OfficeHandler` 已通过 `server_routes.dispatch()` 分发，`app/server_routes/` 保持薄路由层，`app/server_services/` 承接 projects/meetings/providers/notifications domain 业务；前端 `app/game.js` 保持轻量入口/兼容，主要设置、项目、会议、agent、布局、渲染、循环、sidebar、workspace、skills 等逻辑已拆入独立模块。
- 职责边界结论：通过。route 文件负责 path/method dispatch，service 文件负责 domain business，前端模块按页面交互域和渲染域拆分。后续可继续优化但不阻塞本需求的是两个仍偏大的模块：`app/server_services/projects.py` 4465 行、`app/projects.js` 4419 行。
- 最终行数快照：`app/server.py` 19237、`app/game.js` 1340、`app/setup.html` 526；`app/server_routes/__init__.py` 21、`http.py` 63、`meetings.py` 100、`notifications.py` 41、`projects.py` 217、`providers.py` 79；`app/server_services/__init__.py` 1、`meetings.py` 3390、`notifications.py` 316、`projects.py` 4465、`providers.py` 141；`app/settings-common.js` 42、`setup-settings.js` 714、`main-menu-settings.js` 891、`projects.js` 4419、`meetings-ui.js` 3237、`agent-model.js` 2582、`bubble-system.js` 761、`office-layout-editor.js` 2317、`office-rendering.js` 3105、`office-loop.js` 1837、`sidebar-ui.js` 271、`agent-workspace-panel.js` 831、`skills-library-ui.js` 264、`game-bootstrap.js` 18。
- 结构/语法通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py` 通过；`node --check` 覆盖拆分后的核心前端模块和 `app/game.js` 通过；`node tests/check_server_frontend_module_split.mjs` 通过。
- Python pytest 兼容全集通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`，结果 `302 passed, 1 warning in 32.65s`。唯一 warning 来自 Feishu SDK 依赖的 deprecated `datetime.utcfromtimestamp()`。
- Workflow E2E 通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_workflow_e2e.py`，结果 `20/20 passed`。本地无 gateway token 时任务会进入 `awaiting_human_intervention`，按“已从 Backlog 派发”验收。
- CRUD/smoke 通过：`bash tests/test_crud_projects.sh http://127.0.0.1:8090`，结果 `5/5 passed, 0 failed`；`/health` 返回 running；`/api/license` 返回 DEV licensed；`/browser-status` 返回 enabled 且 CDP available。
- Node/浏览器全集通过：服务运行状态下逐个执行 `tests/*.{js,mjs}`，每文件 150 秒超时，结果 `NODE_SUMMARY total=36 failed=0`。
- 当前结论：拆分文件正确、职责边界通过、系统可发现测试全量回归通过，没有未通过测试。需求继续保持 `implementation_done`，等待用户确认 `tested` / `done` 后再归档。

## Phase 12-17 Python 主服务继续瘦身 Checklist

执行规则：继续沿用“一拆一测”。每个 phase 必须先完成迁移，再执行对应测试闸门；测试闸门未通过、未修复或未明确记录失败归因前，不进入下一 phase。所有迁移保持 API path、HTTP method、响应字段、CORS/origin、secret mask、运行时状态语义不变；`server.py` 允许保留兼容导出，但不保留已迁移函数体的重复实现。

| 编号 | 关联需求点 | 验证方法 | 预期结果 |
| --- | --- | --- | --- |
| CHK-044 | Phase 12 Workflow Service 迁移 | 检查 `app/server_services/workflow.py`、`app/server_routes/workflow.py`、`app/server.py`、`app/server_routes/projects.py`；结构测试确认 workflow routes 调用 workflow service | `_wf_*` workflow execution pipeline 从 `server.py` 迁出；project workflow API 路由变薄；旧 `server._wf_*` 兼容入口仍可用 |
| CHK-045 | Phase 12 Workflow 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_workflow_e2e.py`、`tests/test_project_execution.py`、`tests/test_project_scheduled_cron_phase1.py` 到 `phase5.py`、`tests/test_project_cron_idempotent_defect.py`、`node tests/check_project_execution_start_payload.mjs` | workflow start/stop/auto/review/session cleanup/cron 行为不回退；通过后才能进入 Phase 13 |
| CHK-046 | Phase 13 Archive Room Service 迁移 | 检查 `app/server_services/archive_room.py`、`app/server_routes/archive_room.py`、`app/server.py`；结构测试确认 archive route 调用 archive service | archive manager、archive project、inspection、AI refine、maintenance、context package、pending governance 逻辑从 `server.py` 迁出 |
| CHK-047 | Phase 13 Archive Room 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_archive_room_phase_1_3.py` 到 `phase_8.py`、`tests/test_archive_room_ai_refine.py`、archive room Chrome/Node checks | 档案室列表、项目档案、维护、AI 精整、pending/context/governance、浏览器验收不回退；通过后才能进入 Phase 14 |
| CHK-048 | Phase 14 Agent Provider Bridge Service 迁移 | 检查 `app/server_services/agent_bridges.py`、`app/server_routes/agent_bridges.py`、`app/server.py`；结构测试确认 Hermes/Codex/Claude chat/run/activity/approval 路径调用 service | Hermes/Codex/Claude Code chat、run SSE、activity、approval、interrupt/cancel/reset/compact/history clear 等通信桥逻辑从 `server.py` 迁出 |
| CHK-049 | Phase 14 Agent Provider Bridge 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_hermes_server_native_api.py`、`tests/test_codex_server.py`、`tests/test_codex_runs_sse.py`、`tests/test_codex_bridge.py`、`tests/test_claude_code_server.py`、`tests/test_claude_code_runs_sse.py`、相关 Node bridge/i18n checks | 三类 provider 通信、SSE、activity、approval、cancel/reset 行为不回退；通过后才能进入 Phase 15 |
| CHK-050 | Phase 15 Agent Workspace / Skills Service 迁移 | 检查 `app/server_services/agents.py`、`app/server_services/skills.py`、`app/server_routes/agents.py`、`app/server_routes/skills.py`、`app/server.py` | agents list/create/delete、agent platform comm、agent workspace context/update、skills library list/get/create/save/delete/apply/upload 从 `server.py` 迁出 |
| CHK-051 | Phase 15 Agent Workspace / Skills 测试闸门 | 运行 `py_compile`、结构性测试、`tests/test_agent_workspace_project_context.py`、`node tests/check_agent_workspace_project_context_readonly.mjs`、skills library 相关静态/浏览器 smoke、相关 Node full checks | agent workspace、project context readonly、skills library UI/API、agent create/delete/comm 代表路径不回退；通过后才能进入 Phase 16 |
| CHK-052 | Phase 16 Browser / Config / Status Runtime 迁移 | 检查 `app/server_services/browser_runtime.py`、`app/server_services/config_runtime.py`、`app/server_routes/browser.py`、`app/server_routes/config.py`、`app/server.py` | browser-status/tabs/controller/viewer probe、setup/save、vo-config、license、status/health、office config 等低层 runtime/config 路径从 `server.py` 迁出 |
| CHK-053 | Phase 16 Browser / Config / Status 测试闸门 | 运行 `py_compile`、结构性测试、`node tests/test_browser_viewer_url.js`、`node tests/test_weather_location_test_ui.js`、`node tests/test_i18n_integrity.js`、`curl /health`、`curl /api/license`、`curl /browser-status`、设置页 smoke | 浏览器运行态、配置保存、license/status、weather/settings 代表路径不回退；通过后才能进入 Phase 17 |
| CHK-054 | Phase 17 Server.py 收口与兼容层验收 | 检查 `app/server.py`、`app/server_routes/__init__.py`、`app/server_services/*.py`；统计行数和顶层函数数量；确认 `server.py` 仅保留 startup、OfficeHandler、dispatch glue、兼容导出和少量无法独立的共享常量 | `server.py` 行数和函数数量明显下降，目标降至约 8k-12k 行或记录剩余原因；所有已迁移 domain 不在 `server.py` 重复保留函数体 |
| CHK-055 | Phase 17 全量回归与最终验收 | 运行 `py_compile`、结构性测试、`python -m pytest tests --ignore=tests/test_workflow_e2e.py`、`tests/test_workflow_e2e.py`、`tests/*.{js,mjs}`、CRUD shell、服务 smoke；记录最终行数 | Python/Node/浏览器/Workflow/CRUD/smoke 全量通过；失败项必须先修复或明确记录并等待用户确认；通过后仍等待用户确认 tested/done 再归档 |

## Phase 12-17 规划记录

- 记录时间：2026-07-04T09:12:48+0800
- 记录摘要：根据用户要求继续规划 Python 主服务瘦身。新增 Phase 12-17，按 Workflow、Archive Room、Agent Provider Bridge、Agent Workspace/Skills、Browser/Config/Status、最终收口验收逐步迁出 `app/server.py` 残留 domain logic。
- 执行约束：严格一拆一测。每个 phase 先迁移，再测试；测试闸门未通过、未修复或未明确记录失败归因前，不进入下一个 phase。
- 当前状态：仅补充需求、todolist 和 checklist；尚未开始 Phase 12-17 实现。

## Phase 12 Workflow Service 执行记录

- 执行时间：2026-07-04T09:28:30+0800
- CHK-044：通过。新增 `app/server_services/workflow.py` 和 `app/server_routes/workflow.py`；`app/server.py` 删除 `_wf_*` workflow engine 与 `_wf_auto_resume_on_startup` 函数体，通过 `from server_services.workflow import *` 保留旧兼容入口；`app/server_routes/projects.py` 移除 `/workflow/*` 分支，`server_routes.__init__` 将 workflow route 放在 projects route 前。
- CHK-045：通过。测试结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py` 通过；`node tests/check_server_frontend_module_split.mjs` 通过；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py` 结果 6 passed；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_project_execution.py tests/test_project_scheduled_cron_phase1.py tests/test_project_scheduled_cron_phase2_3.py tests/test_project_scheduled_cron_phase4.py tests/test_project_scheduled_cron_phase5.py tests/test_project_cron_idempotent_defect.py` 结果 98 passed；`node tests/check_project_execution_start_payload.mjs` 通过；启动 `VO_STATUS_DIR=/tmp/cosh-phase12-status ./start.sh` 后运行 `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_workflow_e2e.py` 结果 20/20 passed。
- 修复记录：修复 workflow service hydrate 把 projects wrapper 复制回 workflow 导致递归的问题；补齐 `_project_execution_launch_thread` 到 projects service 的桥接；更新 `tests/test_workflow_e2e.py`，源码检查改为读取 `app/server_services/workflow.py`。
- 行数快照：`app/server.py` 17084、`app/server_services/workflow.py` 2511、`app/server_services/projects.py` 4251、`app/server_routes/workflow.py` 52、`app/server_routes/projects.py` 204、`app/game.js` 1340。
- 当前结论：Phase 12 迁移与测试闸门通过，可以进入 Phase 13；需求仍保持 `implementation_done`，等待最终 tested/done 人工确认。

## Phase 13 Archive Room Service 执行记录

- 执行时间：2026-07-04T09:38:30+0800
- CHK-046：通过。新增 `app/server_services/archive_room.py` 和 `app/server_routes/archive_room.py`；`app/server.py` 删除 archive room/manager/governance/maintenance 函数体和 `/api/archive-room*` 重复路由分支，通过 `from server_services.archive_room import *` 保留 `_archive_*`、`_handle_archive_*` 兼容入口；`server_routes.__init__` 将 archive route 纳入 dispatch。
- CHK-047：通过。测试结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py tests/seed_archive_room_phase7_fixture.py tests/seed_archive_room_phase8_fixture.py` 通过；`node tests/check_server_frontend_module_split.mjs` 通过；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py` 结果 7 passed；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_archive_room_phase_1_3.py tests/test_archive_room_phase_4.py tests/test_archive_room_phase_5.py tests/test_archive_room_phase_6.py tests/test_archive_room_phase_7.py tests/test_archive_room_phase_8.py tests/test_archive_room_ai_refine.py` 结果 28 passed。
- Browser/Node archive 验收：启动 `VO_STATUS_DIR=/tmp/cosh-phase13-status ./start.sh` 后，以同一 `VO_STATUS_DIR` 运行 `tests/chrome_archive_room_ai_refine_live_8090_check.mjs`、`chrome_archive_room_manual_refresh_feedback_check.mjs`、`chrome_archive_room_ai_refine_feedback_check.mjs`、`chrome_archive_room_header_style_check.mjs`、`chrome_archive_room_live_8090_feedback_check.mjs`、`chrome_archive_room_phase8_check.mjs`、`chrome_archive_room_switch_rebuild_check.mjs`，全部完成且未抛异常。
- 修复记录：修复 archive service 创建 archive-manager 后只失效 service 本地 discovery cache、未失效 server discovery cache 的问题；为 phase7/phase8 archive browser fixture seed 增加进程内 fake gateway，避免验收依赖本机真实 OpenClaw token；运行 live checks 时显式使用与服务一致的 `VO_STATUS_DIR`。
- 行数快照：`app/server.py` 14484、`app/server_services/archive_room.py` 2650、`app/server_routes/archive_room.py` 78、`app/server_services/workflow.py` 2515。
- 当前结论：Phase 13 迁移与测试闸门通过，可以进入 Phase 14；需求仍保持 `implementation_done`，等待最终 tested/done 人工确认。

## Phase 14 Agent Provider Bridge Service 执行记录

- 执行时间：2026-07-04T09:55:30+0800
- CHK-048：通过。新增 `app/server_services/agent_bridges.py` 和 `app/server_routes/agent_bridges.py`；`app/server.py` 删除 Hermes/Codex/Claude Code chat/run/activity/approval/cancel/reset/compact/history clear 等 provider bridge 函数体和重复 `/api/hermes*`、`/api/codex*`、`/api/claude-code*` route 分支，通过 `from server_services.agent_bridges import *` 保留旧兼容入口；`server_routes.__init__` 将 agent bridge route 纳入 dispatch。
- CHK-049：通过。测试结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py` 通过；`node tests/check_server_frontend_module_split.mjs` 通过；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py` 结果 8 passed；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_hermes_server_native_api.py tests/test_codex_server.py tests/test_codex_runs_sse.py tests/test_codex_bridge.py tests/test_claude_code_server.py tests/test_claude_code_runs_sse.py` 结果 52 passed；`node tests/check_codex_runs_bridge.mjs`、`node tests/check_claude_code_runs_sse.mjs`、`node tests/check_codex_approval_ui.mjs`、`node tests/check_claude_code_chat_i18n.mjs` 全部通过。
- 修复记录：修复 provider run worker 先标记 `done=True` 后发送 terminal event 导致 SSE 测试偶发读不到 `run.completed` 的竞态，调整为先入队终态事件再标记 done；修复 `tests/test_claude_code_server.py` 对 import 顺序的隐式依赖，显式设置测试期 Claude Code `VO_CONFIG`，避免全量顺序中 provider 被误判 disabled。
- 行数快照：`app/server.py` 10502、`app/server_services/agent_bridges.py` 3873、`app/server_routes/agent_bridges.py` 169、`app/server_services/archive_room.py` 2650、`app/server_services/workflow.py` 2515。
- 当前结论：Phase 14 迁移与测试闸门通过，可以进入 Phase 15；需求仍保持 `implementation_done`，等待最终 tested/done 人工确认。

## Phase 15 Agent Workspace / Skills Service 执行记录

- 执行时间：2026-07-04T09:57:30+0800
- CHK-050：通过。新增 `app/server_services/agents.py`、`app/server_services/skills.py`、`app/server_routes/agents.py`、`app/server_routes/skills.py`；`app/server.py` 删除 agent workspace、agent platform communication、agent create/delete、agent skills、skills library、skills workshop 函数体和重复 route 分支，通过 `from server_services.agents import *`、`from server_services.skills import *` 保留旧兼容入口；`server_routes.__init__` 将 skills/agents route 纳入 dispatch，并放在 provider bridge 前，保证 communication log helper 已可用。
- CHK-051：通过。测试结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py` 通过；`node tests/check_server_frontend_module_split.mjs` 通过；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py` 结果 10 passed；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_agent_workspace_project_context.py tests/test_codex_server.py tests/test_claude_code_server.py tests/test_archive_room_phase_4.py` 结果 27 passed；`node tests/check_agent_workspace_project_context_readonly.mjs` 通过；`node --check app/agent-workspace-panel.js app/agent-skills-management.js app/skills-library-ui.js app/agent-creator-panel.js` 通过。
- Live smoke：启动 `VO_STATUS_DIR=/tmp/cosh-phase15-status ./start.sh` 后，`/health` 返回 running；`/api/agents` 返回 agents 数组（4）；`/api/skills-library` 返回 skills 数组（5）；`/api/agent-platform-communications/skill` 返回 markdown skill frontmatter；`/api/agent-platform-communications/history?limit=5` 返回 `{ok:true, events:[]}`。测试后已停止临时服务。
- 行数快照：`app/server.py` 7846、`app/server_services/agents.py` 1745、`app/server_services/skills.py` 834、`app/server_routes/agents.py` 75、`app/server_routes/skills.py` 78。
- 当前结论：Phase 15 迁移与测试闸门通过，可以进入 Phase 16；需求仍保持 `implementation_done`，等待最终 tested/done 人工确认。

## Phase 16 Browser / Config / Status Runtime 执行记录

- 执行时间：2026-07-04T10:04:30+0800
- CHK-052：通过。新增 `app/server_services/browser_runtime.py`、`app/server_services/config_runtime.py`、`app/server_routes/browser.py`、`app/server_routes/config.py`；迁出 browser status/tabs/controller/viewer probe、setup save、safe vo-config、office-config get/save、license status/activate/deactivate、health/status、weather proxy/test 等低层 runtime/config 逻辑；`server.py` 保留 `/setup` 页面、browser viewer 静态代理、SMS/model/media 等非本 phase 路径。
- CHK-053：通过。测试结果：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py` 通过；`node tests/check_server_frontend_module_split.mjs` 通过；`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_server_routes_module_split.py` 结果 12 passed；`node tests/test_browser_viewer_url.js`、`node tests/test_weather_location_test_ui.js`、`node tests/test_i18n_integrity.js`、`node tests/check_provider_runtime_settings_ui.mjs` 全部通过。
- Live smoke：启动 `VO_STATUS_DIR=/tmp/cosh-phase16-status ./start.sh` 后，`/health` 返回 running；`/api/license` 返回 DEV；`/browser-status` 返回 enabled/cdpAvailable；`/browser-tabs` 返回 list；`/vo-config` 返回 office/browser 配置。测试后已停止临时服务。
- 修复记录：迁移 `/api/office-config` 旧分支时相邻的 `/api/gateway/test` fallback 被一并移除，导致 startup health 报 gateway test 404；已在 `app/server_routes/config.py` 补回 `/api/gateway/test`，继续调用原 `OfficeHandler._test_gateway_connection()`。
- 行数快照：`app/server.py` 7341、`app/server_services/config_runtime.py` 333、`app/server_services/browser_runtime.py` 158、`app/server_routes/config.py` 65、`app/server_routes/browser.py` 33。
- 当前结论：Phase 16 迁移与测试闸门通过，可以进入 Phase 17；需求仍保持 `implementation_done`，等待最终 tested/done 人工确认。

## Phase 17 Server.py 收口与全量验收记录

- 执行时间：2026-07-04T10:28:30+0800
- CHK-054：通过。`app/server.py` 已收口到 startup、`OfficeHandler`、dispatch glue、兼容导出和仍未进入本轮范围的少量共享/独立功能；Phase 12-16 迁出的 workflow、archive room、provider bridge、agents/skills、browser/config/status domain 不再在 `server.py` 保留重复函数体。`server.py` AST 快照：top defs 124、functions total 227、classes total 2。
- CHK-055：通过。最终从拆分前 `app/server.py` 27468 行、`app/game.js` 20755 行，收敛到 `app/server.py` 7341 行、`app/game.js` 1340 行、`app/setup.html` 526 行。当前最大后端 service 为 `app/server_services/projects.py` 4260 行、`agent_bridges.py` 3879 行、`meetings.py` 3390 行、`archive_room.py` 2650 行、`workflow.py` 2515 行；route 层均保持薄分发，最大 `projects.py` 204 行。
- 修复记录：修复 `config_runtime._persist_setup_payload()` 拆出后只更新 service 本地 `VO_CONFIG`、未同步 `server.py` 与已加载 service 模块的问题，恢复 Feishu app config 保存后的即时配置可见性；修复 `agent_bridges._hydrate()` 在测试 monkeypatch 恢复到 wrapper 后未恢复 service 原始导出函数的问题，解决 Claude Code run idempotency 在全量顺序下读不到历史消息的污染。
- 结构/语法通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/server_services/config_runtime.py app/server_services/notifications.py app/server_services/agent_bridges.py` 通过；此前 Phase 16 全量 `py_compile app/server.py app/server_routes/*.py app/server_services/*.py app/providers/*.py` 已通过；`node tests/check_server_frontend_module_split.mjs` 在全量 Node/browser 中通过。
- Python pytest 兼容全集通过：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`，结果 `309 passed, 1 warning in 38.68s`。唯一 warning 来自 Feishu SDK 依赖的 deprecated `datetime.utcfromtimestamp()`。
- Workflow E2E 通过：服务运行状态下执行 `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache VO_TEST_URL=http://127.0.0.1:8090 .venv/bin/python tests/test_workflow_e2e.py`，结果 `20/20 passed`。备注：该文件是脚本式测试，使用 pytest collect 会因文件底部 `sys.exit(0)` 触发 pytest internal error，因此按脚本直接验收。
- CRUD/smoke 通过：`bash tests/test_crud_projects.sh http://127.0.0.1:8090` 结果 `5/5 passed, 0 failed`；`/health` 返回 running；`/api/license` 返回 demo license payload；`/browser-status` 返回 browser status；`/api/gateway/test` 返回 gateway unreachable 但 endpoint 正常响应。
- Node/浏览器全集通过：服务运行状态下逐个执行 `tests/*.js` 与 `tests/*.mjs`，每文件 240 秒超时，最终结果 `All Node tests passed`。过程中 `chrome_archive_room_ai_refine_live_8090_check.mjs` 曾出现一次 CDP `Uncaught` 顺序抖动，单项立即复测通过，随后完整 Node/browser 第二轮通过。
- 当前结论：Phase 12-17 Python 主服务继续瘦身闭环完成；拆分文件正确、职责边界通过、系统可发现测试全量回归通过，没有未修复失败项。需求继续保持 `implementation_done`，等待用户确认 `tested` / `done` 后再归档。
