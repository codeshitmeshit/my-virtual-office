# Server And Frontend Module Split

## 背景

当前 `app/server.py` 约 27,500 行，`app/game.js` 约 20,700 行，已经成为主要维护风险。后端 HTTP 路由、业务处理、JSON 响应、CORS header、请求体解析大量集中在 `OfficeHandler` 和同一文件的全局函数中；前端设置面板逻辑则分散在 `app/setup.html` 的内联脚本和 `app/game.js` 的主菜单区域中。

用户提出的方向是做结构性改进，但避免大重构。最划算的拆法是沿稳定边界抽模块：

- `server_routes/projects.py`
- `server_routes/providers.py`
- `server_routes/meetings.py`
- `server_routes/notifications.py`
- 公共 `send_json()`、`read_json()`、`require_origin()`，减少每个分支重复 header 和 JSON 解析。
- 前端把 `setup.html`、`game.js` 里的设置面板逻辑拆成独立 JS 模块。

## 目标用户

- 维护 Virtual Office 后端 API 的开发者和 agent。
- 维护设置向导、主菜单设置面板、provider 配置和通知配置的开发者和 agent。
- 执行后续需求时需要快速定位项目、provider、会议、通知相关接口的开发者。

## 目标

- 降低 `app/server.py` 和 `app/game.js` 的单文件维护风险。
- 以路由边界和设置面板边界为主做渐进式拆分，保持现有 API、页面和测试行为兼容。
- 提供统一请求/响应 helper，减少重复 JSON 解析、CORS header、错误响应样板。
- 让后续变更可以优先落在小模块中，而不是继续扩大两个巨型文件。

## 范围

- 后端新增 `app/server_routes/` 包，首批覆盖 projects、providers、meetings、notifications 四类路由。
- 后端新增或抽出公共 HTTP helper，包括 JSON 响应、JSON 请求读取、origin 校验或 CORS 处理。
- 修改 `OfficeHandler` 的 `do_GET`、`do_POST`、`do_PUT`、`do_DELETE`，让其优先委派给对应 route 模块；未迁移路由仍保留原分支。
- 前端新增设置相关 JS 模块，拆出 `setup.html` 内联设置脚本和 `game.js` 主菜单设置逻辑中的可独立部分。
- 更新 HTML script 引用，确保加载顺序清楚，现有全局函数入口仍可被 inline `onclick` 使用。
- 增加聚焦测试，证明路由委派、helper、设置模块入口和关键交互未回退。

## 非目标

- 不重写 HTTP server 框架，不迁移到 Flask/FastAPI/Express。
- 不一次性拆完 `server.py` 或 `game.js` 的所有逻辑。
- 不改变现有 API 路径、请求/响应字段、鉴权语义或页面 DOM 结构。
- 不重做设置面板 UI，不做视觉 redesign。
- 不在本阶段清理所有全局变量，只在模块边界处建立兼容入口。

## 关键约束

- 现有测试和浏览器检查脚本仍应能运行。
- 路由拆分需要兼容当前大量 `_handle_*` 全局函数，以及 `OfficeHandler` 内部方法如 provider config watcher、gateway origin、SMS proxy 等。
- 前端模块拆分必须兼容当前非 bundler 的静态 script 加载方式。
- 当前 HTML 中存在大量 inline `onclick`，拆分后需要保留 `window.mmSaveSettings`、`window.testCodexConnection` 等入口或对应兼容代理。
- 敏感配置如 Feishu secret、provider API key、gateway token 不应因 helper 或模块拆分被日志泄露。

## 当前已知结论

- 这是维护性和可测试性改进，产品目标清楚，不需要进一步产品澄清。
- 技术上应采用分阶段搬迁和 shim/adapter 模式，参照已有 `app/providers/codex_app_server.py` 与 `app/providers/codex_bridge.py` 的拆分测试方式。
- 首批不应追求完全移除 `server.py` 和 `game.js` 中的相关代码，而应先建立路由委派、公共 helper 和前端设置模块边界。

## Phase 2 增量范围

Phase 1 已完成路由包、HTTP helper、dispatch 接入和前端设置模块占位，但实际大文件瘦身仍有限。Phase 2 的目标是在保持低风险的前提下开始真实迁移代码块：

- `app/setup.html`：将 setup wizard 的大段内联设置脚本迁移到 `app/setup-settings.js`，保留顶部 i18n/title 等轻量页面脚本。
- `app/game.js`：将主菜单设置块迁移到 `app/main-menu-settings.js`，包括 `toggleMainMenu`、`_mmLoadCurrentSettings`、`mmTest*`、`mmSaveSettings`、Feishu 设置保存/测试、导入导出/重置等设置相关入口。
- `app/server.py`：删除已由 `server_routes.dispatch()` 覆盖的重复路由分支，优先处理 projects、providers、meetings、notifications 四个域，不迁移尚未接管的路由。
- `app/server_routes/*`：继续保持薄路由层职责，必要时补齐路径解析和 helper 使用，不在 Phase 2 中搬迁大型业务函数。
- 测试和验收：补充结构性检查，验证迁移后的文件行数变化、旧全局入口存在、HTML script 加载顺序、dispatch 覆盖和未迁移路径回退。

## Phase 2 非目标

- 不把 `_handle_project*`、`_handle_meeting*` 等大型业务函数整体搬出 `server.py`。
- 不拆主菜单或 setup wizard 的 HTML 结构和 CSS。
- 不引入 bundler、ES module 或新的前端构建步骤。
- 不改变 API path、HTTP method、响应字段、`_status` 语义、CORS 默认行为或 secret mask 规则。

## Phase 3-7 Game.js 拆分路线图

Phase 2 后 `app/game.js` 仍约 19,900 行。后续不建议一次性拆完整文件，而是用 5 个 phase 逐步把 `game.js` 收敛为薄启动/编排层，目标是最后只保留 canvas/context 初始化、全局配置读取、主 loop 调度、模块加载顺序说明和必要 `window.*` 兼容导出。

### Phase 3：Agent Creator Panel

- 新增 `app/agent-creator-panel.js`。
- 迁移 Agent Creator Panel 相关逻辑，包括 `toggleAgentPanel`、`_buildAgentPanel`、agent 外观编辑、预览、保存、撤销、branch/provider/platform 选择弹窗和相关 DOM 事件。
- 保留旧入口，例如 `window.toggleAgentPanel`，确保 toolbar/onclick 不失效。
- 预期 `game.js` 再减少约 900-1500 行。

### Phase 4：Edit Mode / Layout Editor

- 新增 `app/office-layout-editor.js`，必要时新增 `app/office-color-picker.js`。
- 迁移 edit mode 状态、家具选择、拖拽、多选、撤销、保存、catalog 面板、color picker、desk/branch assign menu、canvas edit overlay 和 edit HUD。
- 只拆编辑控制层，不优先迁移底层 canvas 绘制函数，避免和渲染/碰撞同时大规模耦合变更。
- 预期 `game.js` 再减少约 2500-4000 行。

### Phase 5：Environment Rendering / Furniture

- 新增 `app/office-rendering.js`、`app/furniture-renderers.js`、`app/weather-rendering.js`，若边界清楚再新增 `app/collision-system.js`。
- 迁移 `drawEnvironment`、window/weather 绘制、walls/floor/lighting、furniture dispatcher、desk、meeting room、lounge、kitchen、bookshelf、plant、vending 等绘制函数。
- 验证 canvas 非空、家具显示、天气窗口、collision grid 和交互点不回退。
- 预期 `game.js` 再减少约 3500-5500 行。

### Phase 6：Agents / Bubbles / Idle Animations

- 新增 `app/agent-model.js`、`app/agent-rendering.js`、`app/bubble-system.js`、`app/office-ambient-animations.js`、`app/pet-system.js`。
- 迁移 Agent class、agent appearance drawing、bubbles/chat bubbles、paper airplane、RPS、social interactions、gatherings、dart games、pong、pets，以及 agent update/draw 相关循环函数。
- 放在 Phase 6 执行，等 editor/rendering 拆完后依赖关系更清楚。
- 预期 `game.js` 再减少约 5000-7000 行。

### Phase 7：Meetings / Sidebar / Workspace / Skills + Bootstrap 收口

- 新增 `app/meeting-ui.js`、`app/sidebar-ui.js`、`app/agent-workspace-panel.js`、`app/skills-library-ui.js`，必要时新增 `app/game-bootstrap.js`。
- 迁移 meeting modals、meeting request、action items、sidebar widgets、agent workspace panel、skills library 和 skill editor。
- 最后整理 `index.html` script 加载顺序、结构性测试和旧全局入口兼容导出。
- 完成后 `game.js` 目标控制在 1-3k 行以内，成为兼容旧入口的启动壳。

### Phase 3-7 通用验收策略

- Phase 3-7 必须按“实现 phase -> 测试闸门 -> 下一 phase”的顺序执行；前一测试闸门未通过或未记录失败原因时，不得进入下一 phase。
- 每个 phase 都运行 `node --check` 覆盖新增 JS 模块。
- 扩展结构性测试，确认新模块存在、HTML 已引用、旧 `window.*` 入口仍存在。
- 增加负向检查，确认已迁移函数不再留在 `game.js`。
- 记录 `wc -l app/game.js` 和新增模块行数变化。
- 启动服务做 smoke test：首页加载无 console error、canvas 非空、该 phase 代表入口可打开和操作。

## Phase 8-11 Python 服务拆分路线图

Phase 1/2 已经把 HTTP route dispatch 和公共 JSON helper 拆出，但 `app/server.py` 仍保留大量 `_handle_*` 业务函数。后续 Python 服务拆分的目标不是更换 Web 框架，而是把 domain business logic 从 `server.py` 迁入 `app/server_services/`，让 `server.py` 最终只保留 HTTP handler、静态资源、启动流程、兼容 wrapper 和少量跨域胶水。

执行顺序继续采用“一拆一测”：每个服务域完成迁移后必须先通过对应测试闸门并写入验收记录，才能进入下一个服务域。任一测试闸门未通过时，不进入下一 phase，除非失败被明确记录为既有问题并由用户确认继续。

### Phase 8：Projects Service

- 新增 `app/server_services/projects.py`，必要时新增 `app/server_services/__init__.py`。
- 迁移 project CRUD、task update/delete、project execution start/cancel/review/accept、checklist 状态计算、scheduled cron/project load repair 等 project 业务函数。
- `app/server_routes/projects.py` 改为调用 `server_services.projects`，不再直接依赖 `server.py` 中已迁移的 project 函数体。
- `server.py` 可暂留轻量兼容 wrapper，但 wrapper 只能委派到 service，不能保留第二份业务逻辑。

### Phase 9：Meetings Service

- 新增 `app/server_services/meetings.py`。
- 迁移 meeting request、confirm/reject、executable meeting lifecycle、active/history 查询、conflict/action item、quality gate 和 meeting for AI 相关业务函数。
- `app/server_routes/meetings.py` 改为调用 `server_services.meetings`，保持原 API path、method、响应字段和状态机语义不变。
- 保留通知发送、project 关联等跨域调用的现有行为；如果需要抽公共 helper，只做薄适配，不扩散重构范围。

### Phase 10：Providers Service

- 新增 `app/server_services/providers.py`。
- 迁移 provider runtime config、Hermes/Codex/Claude Code 测试、provider execution contract、gateway/origin/token 相关业务逻辑。
- `app/server_routes/providers.py` 改为调用 `server_services.providers`。
- 不改变 provider 配置文件格式、masked secret 规则、runtime watcher 语义或默认 provider 选择策略。

### Phase 11：Notifications Service

- 新增 `app/server_services/notifications.py`。
- 迁移 Feishu notification config、masked secret 保存、webhook/test/card action、通知状态读写和相关 helper。
- `app/server_routes/notifications.py` 改为调用 `server_services.notifications`。
- 不改变 Feishu secret mask、通知 payload 字段、失败降级和测试接口返回结构。

### Phase 8-11 通用验收策略

- 每个 phase 都运行 Python 编译检查：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache python3 -m py_compile app/server.py app/server_routes/*.py app/server_services/*.py`。
- 扩展结构性测试，确认 `app/server_services/*.py` 存在、route 模块调用 service、`server.py` 中已迁移函数体不再重复保留。
- 每个服务域运行对应 pytest/Node 子集，并记录行数变化：`wc -l app/server.py app/server_routes/*.py app/server_services/*.py`。
- Projects 闸门覆盖 project execution、scheduled cron 和 project UI payload 检查。
- Meetings 闸门覆盖 meeting for AI phase4/5/6 和 project meeting records UI 检查。
- Providers 闸门覆盖 provider runtime config、provider execution contract 和 provider runtime settings UI 检查。
- Notifications 闸门覆盖 Feishu notifications、masked secret 保存和通知 test/action 代表路径。
- Phase 11 结束后再跑一次相关完整 Python 子集和服务 smoke：`/health`、`/api/license`、`/browser-status`。
- 完整回归中的既有失败必须继续单独标注；若失败经过本次迁移路径，必须先修复再进入下一 phase。
