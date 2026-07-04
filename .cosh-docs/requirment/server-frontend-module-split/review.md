# Server And Frontend Module Split Review

## 产品澄清检查

需求目标明确：降低两个巨型文件的维护风险，并按已有业务边界拆模块。该需求不改变用户可见能力，也不需要新增交互范式。暂无阻塞性产品歧义。

## 技术评审结论

结论：可以进入 checklist 草案。建议以低风险、分阶段的结构性改进推进，不做一次性大搬迁。

## 现状观察

- `app/server.py` 当前约 27,500 行，`OfficeHandler` 从约 22,846 行开始，`do_GET`、`do_POST`、`do_PUT`、`do_DELETE` 中存在大量路径分支和重复响应代码。
- 项目相关函数集中在 `server.py` 中，例如 `_handle_projects_list`、`_handle_project_get`、`_handle_project_create`、`_handle_project_execution_*`、`_handle_project_scheduled_cron_*` 等。
- 会议相关函数集中在 `server.py` 中，例如 `_handle_meeting_request_create`、`_handle_meeting_request_confirm`、`_handle_meeting_create`、`_handle_meeting_end` 等。
- provider 相关函数横跨 `server.py` 全局 `_handle_codex_*`、`_handle_hermes_*`、`_handle_claude_code` 风格接口，以及 `OfficeHandler` 内部的模型配置 watcher 方法。
- 通知相关代码包含 Feishu card action、Feishu notification config/test 和相关 secret mask 逻辑。
- `app/setup.html` 约 1,220 行，设置向导脚本从页面内联脚本中直接处理 license、provider、browser、SMS、PC metrics、Feishu、weather、finish setup 等流程。
- `app/game.js` 约 20,700 行，主菜单设置逻辑集中在约 13,980 行到 14,800 行附近，包含 `_mmLoadCurrentSettings`、`mmTestHermes`、`mmTestCodex`、`mmTestClaudeCode`、`mmTestCdp`、`mmSaveSettings`、Feishu 设置等。
- `app/index.html` 仍使用普通 `<script src="game.js?...">` 加载方式，没有前端 bundler。

## 推荐方案

### 后端

- 新增 `app/server_routes/__init__.py` 和 `app/server_routes/http.py`。
- `http.py` 提供：
  - `send_json(handler, data, status=None, headers=None)`：统一 JSON 响应和 CORS header，支持 `_status` 字段兼容。
  - `read_json(handler, max_bytes=None)`：统一读取 request body，空 body 返回 `{}`，JSON 错误返回明确错误或抛出可转换异常。
  - `require_origin(handler, allowed=None)`：集中处理需要 origin 校验的接口，默认保持当前同源/CORS 行为，不扩大安全面。
  - 可选 `send_error_json(handler, status, error, code=None)`。
- 新增 route 模块，每个模块暴露统一入口，例如 `handle_get(handler, path, query) -> bool`、`handle_post(handler, path, query) -> bool`、`handle_put(...)`、`handle_delete(...)`。返回 `True` 表示已处理，`False` 表示交回 `server.py` 原逻辑。
- `OfficeHandler.do_*` 顶部先解析 `urllib.parse.urlparse(self.path)`，按顺序调用 route 模块；未覆盖路径保留原分支。
- 首批搬迁以薄委派为主：route 模块先调用 `server.py` 中既有 `_handle_*` 函数，后续再把业务函数整体迁出。这样能先缩小路由分支，同时避免循环依赖爆炸。
- 对 provider 路由需谨慎：`OfficeHandler` 内部有 `_send_watcher_request`、`_get_models`、`_set_agent_model` 等方法，首批 route 模块可以接收 `handler` 并调用其方法，暂不强行迁移这些方法。

### 前端

- 新增例如：
  - `app/settings-common.js`：共享 escape、weather location、masked secret 判断、fetch JSON helper、默认 browser URL。
  - `app/setup-settings.js`：承接 setup wizard 中的 provider/browser/Feishu/weather/test/save 流程。
  - `app/main-menu-settings.js`：承接 `game.js` 主菜单设置面板逻辑。
- 保持普通 script 加载方式，在 `setup.html` 和 `index.html` 中按依赖顺序引入。
- 对 HTML inline `onclick` 兼容：模块内部将需要的函数挂到 `window`，例如 `window.mmSaveSettings = mmSaveSettings`、`window.testCodexConnection = testCodexConnection`。
- 第一阶段可以先抽纯函数和独立流程，不立刻拆 DOM HTML；后续再考虑主菜单 markup 独立化。

## 风险与应对

- 循环导入风险：route 模块从 `server.py` 导入大量 `_handle_*` 可能触发循环。建议 route 模块不要 import `server.py`，而由 `OfficeHandler` 或 route context 注入 handler 函数映射；或在 `server.py` 完成函数定义后注册 routes。
- 行为漂移风险：大量接口依赖 `_status` 字段、path split 细节、query string 细节。迁移时每组路由都要保留请求路径解析测试。
- CORS/security 风险：统一 `send_json` 不应无脑改变所有接口 origin 策略。`require_origin` 应只用于当前已有 origin 限制或明确需要限制的接口。
- 前端全局入口风险：inline `onclick` 和其他模块可能直接调用 `mm*` 函数。拆出后必须保留 window 兼容入口。
- 缓存风险：HTML script query 需要更新版本参数，避免浏览器加载旧 `game.js` 或新模块缺失。
- 测试体量风险：一次迁移四个完整域可能过大。建议按域逐步迁移，先 projects 或 notifications，验证模式后再继续。

## 非阻塞建议

- 给 `server.py` 增加一个临时结构性检查测试，验证 `server_routes/projects.py` 等文件存在、`OfficeHandler` 有 route 委派、重复 `send_header("Access-Control-Allow-Origin", "*")` 数量逐步下降。
- 每迁移一个 route 模块都运行对应 Python 单测和关键 JS browser check。
- 在 route 模块开头记录本模块承接的路径前缀，降低后续定位成本。

## Phase 2 评审

### Phase 2 目标

Phase 2 应从“建立边界”推进到“真实瘦身”。首要价值不是继续新增抽象，而是把已经识别清楚、依赖边界稳定的代码块从巨型文件迁出，并删除已被 route dispatch 接管的重复分支。

### 推荐拆分顺序

1. 前端先迁移 `setup.html` 的 setup wizard 内联脚本。
   - 该脚本当前集中处理步骤跳转、license/provider/browser/SMS/PC metrics/Feishu/weather 测试与保存。
   - 迁移到 `setup-settings.js` 后，应保留 `window.nextStep`、`window.finishSetup`、`window.testCodexConnection`、`window.testClaudeCodeConnection`、`window.testBrowserConnection` 等 inline `onclick` 入口。
   - 顶部 `_t`、`updateSetupPageTitle` 等轻量 i18n/title 辅助可以暂留 `setup.html`，避免扩大变更面。

2. 再迁移 `game.js` 主菜单设置块。
   - 迁移范围以 `MAIN MENU` 设置区域为边界，包含打开/关闭菜单、加载当前设置、provider/browser/weather/PC metrics/Feishu 测试与保存、导入导出、重置等设置函数。
   - `main-menu-settings.js` 继续作为普通 script 加载在 `game.js` 后面，因此可以复用 `game.js` 已初始化的全局状态。
   - 必须显式保留 `window.mmSaveSettings`、`window.mmTestHermes`、`window.mmTestCodex`、`window.mmTestClaudeCode`、`window.mmTestWeather`、`window.toggleMainMenu` 等入口。

3. 最后删除 `server.py` 中重复路由分支。
   - 只删除已经由 `server_routes.dispatch()` 明确接管的 projects/providers/meetings/notifications 分支。
   - 对 `/setup/save`、`/vo-config`、`/browser-status`、静态文件、archive-room、agent 删除、skills-library 等未接管路径继续保留原逻辑。
   - 文件下载或二进制响应类接口即使在 route 中处理，也应继续显式写 header/body，不强行套 `send_json()`。

### 关键风险

- 前端加载顺序风险：`main-menu-settings.js` 依赖 `game.js` 中已有全局变量，必须在 `game.js` 之后加载；`settings-common.js` 必须在 setup/main-menu 模块之前加载。
- 全局函数丢失风险：HTML inline `onclick` 和其他脚本直接调用旧函数名，迁移后必须在 `window` 上保留兼容入口。
- 后端双处理风险：如果 route 已处理但旧分支未删除，后续维护者可能在两个位置改同一路径。Phase 2 应删除重复分支来消除歧义。
- 后端误删风险：`server.py` 中相邻路由密集，删除分支必须以精确 path/method 为依据，不能按大段注释粗暴删除未迁移接口。
- 回归测试解释风险：当前完整 Python 回归已有 project execution/cron 业务断言失败。Phase 2 验收需区分“迁移路径测试”与“既有业务失败”，并继续记录无法归因于迁移的失败。

### Phase 2 验收结论

可以执行，但需要重新确认 checklist。Phase 2 改变了原 checklist 中“首批不追求完全移除相关代码”的假设，新增验收项应覆盖真实迁移、旧入口兼容、重复分支删除和文件行数下降。
