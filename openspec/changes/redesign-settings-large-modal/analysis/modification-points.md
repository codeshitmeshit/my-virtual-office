# 变量级修改点分析

## 分析基线

- 仓库：`/Users/bytedance/cosh/my-virtual-office`
- Git 基线：`416686c826d4be94bee858b4a52897565c7d366e`
- CodeGraph：`.codegraph/` 存在；同步 18 个变更文件后，索引包含 840 个文件。已查询 `toggleMainMenu`、`_mmLoadCurrentSettings`、`mmSaveSettings`、`main-menu-panel`、OSS 动态设置插入点和相关测试影响面。
- OpenSpec：`openspec validate redesign-settings-large-modal --json` 通过，1 项通过、0 项失败。
- 工作树保护：`app/index.html`、两个 locale 文件及 OSS/Personal Assets 等文件已有用户未提交修改。本 change 只能做独立的新文件和最小 wiring，不得恢复、覆盖或格式化这些用户变更。
- 基线测试：
  - `node tests/test_oss_settings_ui.js`：通过，输出 `OSS settings UI contract ok`。
  - `node tests/check_server_frontend_module_split.mjs`：通过。
  - `node tests/check_provider_runtime_settings_ui.mjs`：修改前已失败，原因是 `app/main-menu-settings.js` 缺少测试要求的 `codexCfg.routeApprovalsThroughVo`；运行时 `app/game.js` 已包含该读取。此既有失败不属于本 change，不得顺手修复或把它宣称为本次回归。

## 已证实的当前调用链

1. `app/index.html:364` 的 `#btn-main-menu` 通过内联 `onclick="toggleMainMenu()"` 进入运行时。
2. `app/game.js:14041` 定义 `_mainMenuOpen: boolean`；`toggleMainMenu`（14090-14103）翻转该变量并仅通过 `#main-menu-panel.classList.toggle('open', _mainMenuOpen)` 控制可见性，同时保持设置加载和飞书 Chat polling 的启停。
3. `_mmLoadCurrentSettings`（`app/game.js:14105` 起）与 `mmSaveSettings`（15137-15336）按稳定 DOM ID 读写字段；它们不依赖字段在 `.main-menu-body` 中的直接父节点或顺序。
4. 当前视觉由 `app/style.css:4-18` 的 `.main-menu-panel` 绝对定位、`left: -280px -> 0` 和 `width: 270px` 构成；`.main-menu-body`（31-38）是单列滚动容器，`.mm-section`（39-45）是现有卡片边界。
5. `app/index.html:49-360` 包含现有 header、body、全部静态 `.mm-section` 和 `.mm-save-all`；所有业务按钮保留自己的内联 handler。
6. `app/oss-settings.js:31-63` 在脚本执行时把 `#oss-settings-section` 插到 `.mm-save-all` 前；`observeSettingsPanel`（157-169）只观察 `#main-menu-panel` 的 `open` class。`app/index.html:1255-1256` 先加载 `game.js`，再加载 `oss-settings.js`，因此新的布局模块可在 OSS 之后安全重排已有节点，同时继续保留 `open` class 作为 OSS 加载信号。

## 修改点卡片

### 修改点 ID：MP-SET-01

修改点 ID：MP-SET-01
对应 scenario：打开大弹窗；关闭不引入新语义；分类导航；分类切换保留字段值；全部设置控制 parity；条件字段保持条件化；现有 action 行为兼容。
文件：`app/settings-modal-ui.js`
符号：`CATEGORY_DEFINITIONS`、`settingsModalState`、`classifySection(section)`、`activateCategory(categoryId)`、`mountSettingsModal()`
变量：`CATEGORY_DEFINITIONS`、`settingsModalState`、`panel`、`body`、`sections`、`saveButton`
类型：展示状态与现有 DOM 节点重排
目标变化：把现有设置节点按七个分类重排进大弹窗，同时保持原节点、ID、handler 和业务副作用。
未决假设：无。

对应 scenarios：打开大弹窗；关闭不引入新语义；分类导航；分类切换保留字段值；全部设置控制 parity；条件字段保持条件化；现有 action 行为兼容。

- 仓库/基线：本仓库 / `416686c826d4be94bee858b4a52897565c7d366e`
- 新文件：`app/settings-modal-ui.js`
- 计划符号：`CATEGORY_DEFINITIONS`、`settingsModalState`、`classifySection(section)`、`activateCategory(categoryId)`、`mountSettingsModal()`。
- 变量与类型：
  - `CATEGORY_DEFINITIONS: Array<{id: string, labelKey: string, selectors: string[]}>`：定义七个产品分类及现有 section 的稳定 selector 锚点。
  - `settingsModalState: {mounted: boolean, activeCategory: string}`：只保存当前页面会话的展示状态，不进入 localStorage 或服务端。
  - `panel: HTMLElement | null`：来源为 `document.getElementById('main-menu-panel')`。
  - `body: HTMLElement | null`：来源为 `panel.querySelector('.main-menu-body')`。
  - `sections: HTMLElement[]`：来源为 `body.querySelectorAll('.mm-section')`，包括 OSS 已动态插入的 section。
  - `saveButton: HTMLButtonElement | null`：来源为 `body.querySelector('.mm-save-all')`。
- 当前值来源：`app/index.html:49-360` 的现有 DOM；OSS section 来源为 `app/oss-settings.js:31-63`。
- 计划读取：section 内现有稳定 ID（如 `#mm-oc-path`、`#mm-hermes-enable`、`#mm-codex-enable`、`#mm-office-name`、`#mm-show-bubbles`、`#mm-apiusage-enable`、`#mm-pcmetrics-enable`、`#mm-browser-enable`、`#mm-feishu-enable`、`#oss-settings-section`、`#mm-import-file`）。
- 计划写入：只创建 modal dialog、nav、category panel、content 和 footer 展示容器；给节点写展示 class、ARIA 属性和 `data-settings-category`；把原始 section 与原始 `.mm-save-all` 节点移动到新容器，不克隆、不替换、不修改其 ID 或 handler。
- 预期变化：当前 270px 单列侧栏变为七分类大弹窗；分类按钮只切换 active 展示状态。原始 input 值随原节点移动而保留。
- 明确保持不变：
  - 不读取或写入 `_mainMenuOpen`；仍由 `toggleMainMenu` 独占。
  - 不覆盖 `_mmLoadCurrentSettings`、`mmSaveSettings`、任何 `mmTest*`、飞书、OSS、导入、导出、重置或语言/字号函数。
  - 不新增 backdrop click、Escape、dirty tracking、自动保存或关闭确认。
- 上游：`app/index.html` 在 `game.js` 与 `oss-settings.js` 完成初始化后加载本模块。
- 下游：现有 `game.js` ID 查询、内联 handler、OSS `open` observer 与飞书 polling 继续消费同一节点和 class。
- 测试锚点：计划新增 `tests/test_settings_modal_ui.js`，验证 7 个分类、每个当前 section 恰好归属一次、节点身份不变、导航不调用业务 handler、字段值跨分类保留、重复 mount 幂等。
- 排除的替代点：
  - 不把布局逻辑追加到 19k 行的 `app/game.js`，避免扩大 legacy entry point。
  - 不复制 300 多行设置 markup 到第二套 modal，避免 DOM ID、handler 和密钥输入产生双权威。
  - 不重写 `toggleMainMenu`，避免破坏设置加载与飞书 polling 生命周期。
- 未决假设：无。脚本顺序、稳定 ID 和 OSS 插入时机均已由当前源码确认。

### 修改点 ID：MP-SET-02

修改点 ID：MP-SET-02
对应 scenario：大弹窗 shell；清晰 action/status；管理员信息密度；窄桌面可访问；Figma 视觉验收。
文件：`app/settings-modal.css`
符号：`.main-menu-panel.settings-modal-mounted`、`.settings-modal-dialog`、`.settings-modal-layout`、`.settings-modal-nav`、`.settings-modal-content`、`.settings-modal-category-panel`、`.settings-modal-footer`
变量：`--settings-modal-width`、`--settings-modal-height`、`--settings-modal-nav-width`、`--settings-modal-surface`、`--settings-modal-border`
类型：限定作用域的 CSS 几何与视觉 token
目标变化：仅在 UI 模块挂载成功后把旧侧栏呈现为带稳定区域的大弹窗，并提供窄桌面降级。
未决假设：最终像素值需在 design 阶段以已确认 Figma 大弹窗为准，不影响代码边界选择。

对应 scenarios：大弹窗 shell；清晰 action/status；管理员信息密度；窄桌面可访问；Figma 视觉验收。

- 仓库/基线：本仓库 / `416686c826d4be94bee858b4a52897565c7d366e`
- 新文件：`app/settings-modal.css`
- 计划选择器：`.main-menu-panel.settings-modal-mounted`、`.settings-modal-dialog`、`.settings-modal-layout`、`.settings-modal-nav`、`.settings-modal-content`、`.settings-modal-category-panel`、`.settings-modal-footer`，以及上述容器内对现有 `.mm-section`、`.mm-input`、`.mm-btn`、`.mm-status` 的限定覆盖。
- 变量与类型：计划新增 `--settings-modal-width: <length>`、`--settings-modal-height: <length>`、`--settings-modal-nav-width: <length>`、`--settings-modal-surface: <color>`、`--settings-modal-border: <color>` 等局部 CSS custom properties。
- 定义/写入：所有新视觉规则仅写入 `app/settings-modal.css`；只有根节点具备 `settings-modal-mounted` 时才覆盖旧侧栏，模块未挂载时继续使用 `app/style.css:4-135` 的现状作为降级。
- 当前值来源：`app/style.css:4-18` 的侧栏几何、19-35 的 header/body、39-135 的 section/control/status 基础样式；产品视觉基准来自 Figma `334:240`。
- 预期变化：根层成为带遮罩的大弹窗，dialog 保持稳定 header/nav/content/footer，content 独立滚动，卡片在可用宽度内采用高密度网格；窄桌面降级为单列内容且所有动作可滚动访问。
- 明确保持不变：不删除或改写 `app/style.css` 的现有规则，不改变 canvas、toolbar、其他 modal、meeting、personal assets 或 agent management 样式。
- 测试锚点：计划新增静态 wiring/layout contract 测试，并使用 1512×742 与窄桌面 viewport 的浏览器截图验证 dialog 边界、滚动、无遮挡和无文本裁切。
- 排除的替代点：不继续扩大 `app/style.css`；不使用全局 `.modal` 覆盖，避免影响其他产品弹窗。
- 未决假设：最终像素值需在 design 阶段以已确认 Figma 大弹窗为准，不影响代码边界选择。

### 修改点 ID：MP-SET-03

修改点 ID：MP-SET-03
对应 scenario：任务分类导航；完整设置 parity；批准设计与交互可追溯。
文件：`app/index.html`、`app/locales/en.json`、`app/locales/zh.json`
符号：stylesheet load list、runtime script list、settings modal locale keys
变量：`settings_modal_connections_agents`、`settings_modal_office`、`settings_modal_display`、`settings_modal_tools_browser`、`settings_modal_notifications`、`settings_modal_storage`、`settings_modal_advanced`、`settings_modal_subtitle`
类型：资源 wiring 与本地化字符串
目标变化：以最小 HTML/JSON patch 加载新模块和样式，并让七个分类随当前语言更新。
未决假设：无。

对应 scenarios：任务分类导航；完整设置 parity；批准设计与交互可追溯。

- 仓库/基线：本仓库 / `416686c826d4be94bee858b4a52897565c7d366e`
- 文件：`app/index.html`、`app/locales/en.json`、`app/locales/zh.json`
- 精确表达式与变量：
  - `app/index.html:12-27` 的 stylesheet load list：计划在 `style.css` 后增加 `settings-modal.css`，确保限定覆盖生效。
  - `app/index.html:1255-1257` 的 runtime script list：计划在 `oss-settings.js` 后增加 `settings-modal-ui.js`，确保 OSS section 已存在再 mount。
  - 新 locale keys（字符串）：`settings_modal_connections_agents`、`settings_modal_office`、`settings_modal_display`、`settings_modal_tools_browser`、`settings_modal_notifications`、`settings_modal_storage`、`settings_modal_advanced`、`settings_modal_subtitle`。
- 当前值来源：导航名称需通过现有 `window.i18n.t` 和 `i18n:changed` 生命周期读取；不能把中文或英文硬编码为唯一显示值。
- 计划读取：`settings-modal-ui.js` 读取上述 locale key；切换语言后重新渲染 nav 文案而不重建表单节点。
- 计划写入：仅增加两个资源引用和上述新翻译键，不改 `app/index.html:49-360` 的既有设置字段、按钮和 handler。
- 预期变化：新模块和样式进入运行时；中英文分类文案与当前语言同步。
- 用户变更保护：`index.html` 已新增 Personal Assets 与 OSS wiring，locale 文件已新增 Personal Assets/OSS 文案；实现必须用局部 patch 保留这些内容，禁止整体重排 JSON 或 HTML。
- 测试锚点：计划新增 `tests/check_settings_modal_wiring.mjs`，验证 CSS/JS 顺序、全部 locale key、设置 ID inventory 未减少，并验证新模块不包含 `/setup/save`、localStorage 或业务 endpoint。
- 排除的替代点：不把模块拼回 `game.js`；不复制已有设置 markup；不使用未本地化的固定导航文案。
- 未决假设：无。

## 设计证据边界（非代码修改点）

- Figma 文件：`o6Crht2KV89peGoPpCAJsX`
- 大弹窗：`334:240`
- 交互全景：`338:240`
- 存储与提交：`338:249`
- 在 design 阶段，交互板与存储板必须删除或改写“测试默认不落库”“服务端成功后才写本地偏好”“dirty-close 三选一”等超出本期范围的目标语义；保留对当前 side effect、独立保存边界和现有关闭行为的准确说明。
- Figma 更新映射到 MP-SET-01 的行为兼容边界与 MP-SET-02 的视觉验收，不建立平行产品规格。

## 跨修改点风险

1. `app/index.html` 与 locale 文件已有用户未提交变更；虽然 planned diff 很小，仍需要逐块检查，确保不覆盖 Personal Assets 和 OSS 内容。
2. `app/main-menu-settings.js` 是未直接加载的拆分源，而运行时仍由 `app/game.js` 提供设置函数。此 change 不修改两份业务实现，避免产生第三份行为权威。
3. OSS 测试依赖 `#main-menu-panel .main-menu-body` 和 `open` class。新模块必须保留两者；脚本顺序测试必须阻止 settings modal 在 OSS section 创建前 mount。
4. 现有 provider runtime 静态测试已有基线失败。最终验证必须把该既有失败与本 change 的聚焦测试结果分开报告。

## 建议确认结果

- 接受 MP-SET-01 至 MP-SET-03 作为后续 `design.md` 的唯一代码修改边界。
- 接受“新 UI 模块重排原节点、限定 CSS 覆盖、index/locale 最小 wiring”的方案方向。
- 明确不修改 `app/game.js`、`app/main-menu-settings.js`、后端 API、存储格式和现有 action side effects。
