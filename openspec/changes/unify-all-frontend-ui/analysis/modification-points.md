# 变量级修改点证据

## 取证基线

- 仓库：`/Users/bytedance/cosh/my-virtual-office`
- 基线 commit：`a99f80f75ca8ebe8b5c6ec4d0bf8d937386d2c8b`
- 当前源码：以 2026-08-09 工作区为准。CodeGraph 索引用于发现调用与影响面；所有行号、变量和值均已回到当前磁盘源码复核。
- 工作区状态：存在用户的已修改与未跟踪文件。本 change 只在这些现状上增量迁移 UI，不还原、不覆盖其他 change 的业务实现。
- 全局不变量：不修改后端路由、服务、存储、协议、请求/响应结构、业务状态机或持久化时序；现有 DOM id、公开 JS 入口与事件处理器默认保持兼容。

修改点 ID：MP-01
对应 scenario：A frontend surface resolves foundation values；A domain visual needs specialized presentation；In-progress frontend work is migrated
文件：`app/index.html:12`、`app/style.css:138`、`app/fonts.css:9`，新增 `app/ui-system.css`
符号：`<head>` stylesheet load order；CSS `:root`；`html[lang="zh"]`；`html[lang="zh"] body *`
变量：`--ui-bg`、`--ui-surface`、`--ui-border`、`--ui-text`、`--vo-pixel-ui-font`、新增 `--ui-canvas|surface|toolbar|panel|text-primary|text-muted|accent|success|info|warning|danger|space-*|radius-*|font-*`
类型：CSS custom property token（颜色、长度、font-family 字符串）与 HTML stylesheet `href: string`
定义位置：`app/style.css:138-147` 定义四个 `--ui-*`；`app/fonts.css:9-16` 定义并按语言覆盖像素字体；`app/index.html:12-28` 决定主应用级联顺序。
当前值来源：历史主样式硬编码；`--ui-surface` 当前为 `#1a1a2e`，实际对应规范 Panel 而非 Surface；`fonts.css:18-20` 对中文页面所有后代强制像素字体。
相关读取行：`app/style.css:159-160,695,736,852,876,887,906-907,919` 起的全局壳层与面板规则；各 feature CSS 通过硬编码旁路这些变量。
相关写入行：CSS 级联在文档解析时写入 computed style；语言切换通过 `html[lang="zh"]` 重写 `--vo-pixel-ui-font`。
目标变化：在新聚焦文件 `app/ui-system.css` 建立唯一 canonical token 层：Canvas `#0A0A0F`、Surface `#12121E`、Toolbar `#151520`、Panel `#1A1A2E`、主文字 `#E8E8F0`、弱文字 `#888888`、Accent `#FFD700`、Success `#4CAF50`、Info `#4FC3F7`、Warning `#FFB300`、Danger `#F44336`，并补齐 2/4/6/8/12/16/24/32 间距、4/6/8/12/pill 圆角和 8/9/10/12/14/18 字级。旧 `--ui-*` 作为兼容别名而非第二套系统；正文改为可读系统中文字体栈，像素字体只保留在办公室场景/品牌化 domain visual 的显式作用域。
上下游影响：上游是 Figma canonical page；下游是所有主应用 CSS module 与动态插入的 UI。办公室 canvas、avatar、pipeline canvas 等 domain visual 可保留，但外围 chrome 必须消费 canonical token。
测试锚点：新增 `tests/test_frontend_ui_system_contract.py` 校验 token 完整性、别名、加载顺序与未定义变量；扩展 `tests/test_font_assets.js`、`tests/test_font_scale.js` 验证技术字体和语言字体边界。
排除的替代点：不逐文件再创建 `:root`；不删除现有像素字体资产；不修改 canvas 绘制颜色、头像素材或业务状态颜色数据。
未决假设：无阻塞项；domain visual 例外仅限内容本体，不延伸到导航、表单、对话框和反馈。

修改点 ID：MP-02
对应 scenario：Equivalent controls appear on different surfaces；Close and destructive actions are presented；A form control changes state
文件：`app/window-controls.css:2`、`app/style.css:58`、`app/settings-modal.css:73`，新增 `app/ui-components.css`
符号：CSS `:root` close-control tokens；`.close-btn,.catalog-close-btn,.agent-management-close,...`；`.mm-input`；`.mm-btn`；`.settings-modal-nav-button`
变量：`--vo-close-bg-hover`、`--vo-close-border-hover`、`--vo-close-color`、`--vo-close-color-hover`、`--vo-close-focus`；共享 `.ui-button|input|select|textarea|toggle|card|badge` declaration blocks
类型：CSS custom property token 与 `CSSStyleRule` declaration block；CSS 源码无运行时变量，因此以最小规则块作为变量级表达式
定义位置：`app/window-controls.css:2-12` 定义关闭控件颜色；`:14-96` 写尺寸/状态；`app/style.css:58-102` 定义旧设置输入与按钮；`app/settings-modal.css:73-88,116-148` 再次覆盖 close/nav 状态。
当前值来源：关闭动作使用 Danger 红 `#f44336` 与红色 hover；同语义按钮、输入、导航在 feature CSS 中使用不同高度、颜色、字体和 focus 规则。
相关读取行：`app/index.html` 中 `.close-btn`、`.catalog-close-btn` 及各 feature renderer 输出的现有 class；浏览器 CSS selector matching 读取这些规则。
相关写入行：hover/focus/disabled/active 时伪类重算 computed style；feature CSS 后加载时会覆盖共享规则。
目标变化：新增 `ui-components.css` 作为共享 primitive 层并由旧 class 兼容映射消费；关闭为中性 secondary/ghost，删除仍为 danger；按钮、导航、表单、toggle、card、badge 统一尺寸、字体、语义 tone 和 hover/active/focus-visible/loading/error/disabled 状态。feature CSS 只保留布局和领域差异。
上下游影响：不改变按钮 `onclick`、listener、`disabled`/`aria-busy` 写入或 DOM id；会影响所有 modal header、settings、chat/SMS/browser、管理与工作流 surface 的 computed style。
测试锚点：新增 `tests/test_frontend_ui_component_contract.py`；扩展 `tests/test_agent_management_ui.py`、`tests/test_hr_accessibility_ui.mjs`、`tests/test_settings_modal_ui.js` 校验 close 与 focus/disabled 语义。
排除的替代点：不把 close、clear、remove、delete 合并为同一 danger class；不批量更名所有现有 class；不改变按钮触发器和确认流程。
未决假设：无阻塞项；优先用兼容 selector 降低 DOM/测试契约变更。

修改点 ID：MP-03
对应 scenario：Close and destructive actions are presented；A keyboard user operates a migrated workflow；A migrated action is invoked
文件：`app/vo-dialogs.js:5`、`app/vo-dialogs.js:20`、`app/vo-dialogs.js:48`，新增 `app/ui-dialogs.css`
符号：`activeDialog`；`ensureStyles()`；`removeActive(result)`；`show(options)`；`VODialogs.showAlert|showConfirm|showPrompt`
变量：`activeDialog: null | {kind:string,overlay:HTMLElement,resolve:Function,keydown:Function}`、`options: DialogOptions`、`style.textContent: string`
类型：闭包可变状态对象、对话框 option 对象、动态 CSS 字符串
定义位置：`app/vo-dialogs.js:5` 定义活动对话框；`:20-37` 动态注入样式；`:48-131` 创建 DOM、绑定按钮/Enter/Escape、写入活动状态并聚焦。
当前值来源：调用方通过 `voAlert/voConfirm/voPrompt` 传入 kind/tone/text；`ensureStyles()` 自带一套 `--gold/--surface2` fallback 和 hard-coded danger 样式。
相关读取行：`:39-45` 清理并 resolve；`:53` 处理并发替换；`:117-125` 键盘读取 kind；`:135-150` 公共适配器读取 options。
相关写入行：`:113-126` 写 `activeDialog`；`:127-130` 注册 keydown、挂载 overlay、写入焦点；`:39-45` 清空状态并移除 DOM。
目标变化：保持 `activeDialog` 生命周期、Promise 结果、Enter/Escape 与 focus entry 完全不变；移除 JS 内的 competing CSS 字符串，改由 `ui-dialogs.css` 消费 canonical tokens，补齐 label 关联、focus-visible 与 neutral/danger action presentation。只有已有 backdrop-close 行为的 feature dialog 才保留 backdrop close，不在通用确认框新增业务行为。
上下游影响：所有调用 `voAlert/voConfirm/voPrompt` 的设置、项目、cron、models、Agent 等流程继续得到相同返回值；仅 DOM 属性和视觉规则增量变化。
测试锚点：新增 `tests/test_vo_dialogs_ui.js` 覆盖 Promise 结果、Escape/Enter、focus 与 tone；项目删除/重置现有测试继续证明确认边界不变。
排除的替代点：不改用原生 `alert/confirm/prompt`；不把所有 feature-specific complex dialogs 强制改写为 `VODialogs`；不新增后端确认接口。
未决假设：无阻塞项；现有通用 dialog 没有 backdrop click 关闭合同，迁移时保持不新增。

修改点 ID：MP-04
对应 scenario：Multiple transient results occur；An error requires continued user attention；A migrated action is invoked
文件：`app/projects.js:733`、`app/agent-creator-panel.js:659`、`app/game.js:8219`、`app/game.js:15432`、`app/skills-library-ui.js:10`、`app/settings-save-feedback.js:10`，新增 `app/ui-feedback.js` 与 `app/ui-feedback.css`
符号：`ProjMgr::toast(msg,type)`；`_acpShowToast(msg)`；`_archiveToast(message,type)`；`_showOfficeToast(msg)`；`_sklToast(message)`；`VOSettingsSaveFeedback::{start,success,failure}`
变量：`el: HTMLElement`/`toast: Function`；`type: 'info'|'success'|'warning'|'error'`；`currentState: {kind:'idle'|'saving'|'success'|'error',detail:string}`；新增 `feedbackQueue: FeedbackItem[]`
类型：DOM element reference、tone 字符串、反馈状态对象、队列数组
定义位置：项目 toast `app/projects.js:733-746`；Agent toast `app/agent-creator-panel.js:659-665`；archive/office toast `app/game.js:8219-8230,15432-15441`；skills adapter `app/skills-library-ui.js:10-15`；settings state `app/settings-save-feedback.js:10,52-75`。
当前值来源：各业务调用方传文本或 type；部分通过 emoji 推断语义；单 DOM 节点和 timer 会覆盖上一条结果；settings footer 另有可访问的 persistent status。
相关读取行：`app/skills-library-organization-ui.js:712,747,780` 选择全局 toast；`app/game.js:15316-15427` 保存/导入/重置；`app/projects.js` 的 49 个调用点；settings `messageForState()` 读取 `currentState`。
相关写入行：各函数创建/覆写节点、class、text 和 timeout；settings `setState()` 写 `currentState` 后 render。
目标变化：新增 `VOFeedback` 队列边界，接受明确 `message/tone/persistent/action/duration`，支持堆叠和 `role=status|alert`；保留所有旧函数名作为薄适配器，业务调用与时序不变。错误需纠正/重试时持久显示；settings 原有 inline 状态继续作为表单内反馈并复用 canonical tone，不泄露敏感值。
上下游影响：上游为现有 handler 的成功/失败分支；下游仅替换反馈 DOM/样式。API 调用、catch 分支、reload、导入导出和保存流程不改。
测试锚点：新增 `tests/test_ui_feedback.js` 覆盖 stacking、tone、timer、ARIA、persistent；扩展 `tests/test_settings_save_feedback.js`、skills UI 静态测试、项目 UI 合同测试。
排除的替代点：不从 message emoji 猜测业务成功与否作为长期合同；不删除 settings inline feedback；不把需要用户决策的错误降级为短 toast。
未决假设：无阻塞项；旧单参数适配器只做兼容，迁移触达的调用点逐步传显式 tone。

修改点 ID：MP-05
对应 scenario：The main Virtual Office application is audited；A domain visual needs specialized presentation；A keyboard user operates a migrated workflow
文件：`app/style.css:159`、`app/index.html:1208`，新增 `app/ui-main-shell.css`
符号：`body`；`.toolbar`；`.sidebar`；`.modal-content`；`.chat-panel`；`.sms-panel`；`.browser-panel`；办公室 canvas 周边 chrome rules
变量：上述 selector 对应的 `CSSStyleRule[]`（background/color/border/font/spacing/radius/focus/overflow declarations）
类型：CSS rule collection；这些样式没有 JS 静态变量，最小可定位表达式是 selector declaration block
定义位置：`app/style.css:159` 起定义 body/canvas 主壳；`:887` 起 sidebar；`:1067` 起 modal；`:1635` 起 SMS；`:2195` 起 chat；browser 与 toolbar 同文件后续 section；`app/index.html:1208` 起的内联 bootstrap 负责入口状态，不改。
当前值来源：`style.css` 混合 `--ui-*`、历史硬编码色值与像素字体；多个 panel 各自定义 toolbar/button/form/scrollbar。
相关读取行：`app/game.js`、`app/chat.js`、`app/sms-panel.js`、`app/browser-panel.js`、`app/sidebar-ui.js` 用既有 id/class 开关 `hidden/open/minimized/active` 并写尺寸/位置。
相关写入行：JS 仅写 class、inline geometry 和 CSS vars（如 `--sms-toolbar-clearance`）；CSS cascade 写视觉。迁移不改这些 JS 状态写入。
目标变化：新 `ui-main-shell.css` 统一 office chrome、toolbar、sidebar、chat/SMS/browser/monitor/modal 外壳的 token、层级、文字、间距、滚动条、focus 和窄屏可达性；保留办公室 pixel canvas、家具、天气和 avatar 的 domain visual。
上下游影响：影响主入口所有常驻 chrome；不改变 canvas 坐标、panel 拖拽/缩放、轮询、聊天、通知或窗口状态。
测试锚点：现有 `tests/test_meeting_history_card_layout.js`、browser/SMS/chat 静态与交互测试；新增主壳 desktop/narrow Playwright 截图及 focus smoke。
排除的替代点：不重写 `app/game.js`；不调整办公室布局数据、canvas 绘制、panel 拖拽算法或 localStorage key。
未决假设：无阻塞项；inline geometry 属于运行时布局状态，不作为“禁止 inline presentation”的违规。

修改点 ID：MP-06
对应 scenario：The main Virtual Office application is audited；In-progress frontend work is migrated；A form control changes state
文件：`app/settings-modal.css:27`、`app/agent-management.css:1`、`app/human-resources.css:1`、`app/human-resources-figma.css:6`、`app/personal-assets.css:1`、`app/agent-configuration.css:1`
符号：`.settings-modal-dialog`；`.agent-management-modal|dialog|tabs`；`.hr-shell|hr-*`；`.personal-assets-*`；`.agent-configuration|ac-*`
变量：feature root `CSSStyleRule[]`；`AgentManagement.state: object`；`HumanResources.state: object`；`PersonalAssets.state: object`
类型：CSS rule collection 与模块闭包状态对象
定义位置：CSS 根 selector 位于各文件首部；`app/agent-management.js:4-22`、`app/human-resources.js:4-30`、`app/personal-assets.js:4-35` 定义 open/loading/error/draft/focus 等状态。
当前值来源：renderer 根据 state 输出固定 class；CSS 使用 teal/blue/green/feature-local hard-coded palette，settings 虽最接近规范仍重复硬编码 token 和像素小字。
相关读取行：`AgentManagement.render/open/close` `app/agent-management.js:285-322`；`HumanResources.render/open/close` `app/human-resources.js:951,1159-1180`；`PersonalAssets.render` `app/personal-assets.js:151-245`；settings `mountSettingsModal()` `app/settings-modal-ui.js:168`。
相关写入行：现有 handler 写 state.open/loading/error/editorDraft/returnFocus、DOM hidden/class/aria；CSS 读取这些 class/attributes 呈现状态。
目标变化：保留 renderer、state shape、draft、loading/error、focus-return 和所有 API adapter；仅将管理/设置/HR/个人资产/Agent 配置的 shell、tabs、card、form、badge、notice、dialog 与 action CSS 映射到 MP-01/02 tokens/components，删除相互竞争的 feature palette。`human-resources-figma.css` 只保留已批准的结构布局差异。
上下游影响：已修改/未跟踪的 settings 与 personal-assets 前端工作被保留并纳入统一；后端管理 API、个人资产 revision/sync、HR command 轮询均不改。
测试锚点：`tests/test_settings_modal_ui.js`、`tests/test_settings_save_feedback.js`、`tests/test_agent_management_ui.py`、`tests/test_hr_*ui*`、`tests/test_personal_assets_*.mjs`、`tests/test_agent_configuration_figma_layout.py`。
排除的替代点：不合并设置与 Agent Management 的业务模块；不修改 `state` 字段、API URL、revision、sync 或保存 transport；不覆盖另一 active change 的 settings 行为。
未决假设：无阻塞项；feature-specific Figma 构图只在不冲突于 canonical system semantics 时保留。

修改点 ID：MP-07
对应 scenario：The main Virtual Office application is audited；Orchestration modal is rendered；Visual acceptance is performed；Modal footer is rendered
文件：`app/projects.css:23`、`app/project-orchestration.css:22`、`app/meeting-center.css:18`、`app/archive-room.css:1`、`app/human-decision-center.css:1`
符号：`#projectsModal .proj-*`；`.project-orchestration-*|.proj-orchestration-*`；`.meeting-center-*`；`.archive-*`；`.human-decision-center*`
变量：feature root `CSSStyleRule[]`；`ProjMgr.state: object`；`MeetingCenter.selected: {active,completed,requests}`；`ArchiveRoom.state: object`；Human Decision draft/selection closure state
类型：CSS rule collection、模块状态对象与 tone/state strings
定义位置：CSS roots 位于上述文件；项目 `app/projects.js:18-37`；meeting `app/meeting-center.js:4-5`；archive `app/archive-room.js:4-23`；human decision state 由 factory/render closure 在 `app/human-decision-center.js:182-505` 维护。
当前值来源：API 响应与现有 handler 写业务状态；renderer 输出 `.active/.error/.danger/.status-*` 等 class；CSS 当前分别采用绿色 primary、紫色 meeting、archive/decision 自有 palette。
相关读取行：项目 `renderListView/renderBoardView/renderDetailPanel/show*Dialog`；meeting `renderList/renderControls/render`；archive `render/renderGovernanceDialog/renderArtifactBrowser`；human decision `renderList/renderDetail/open/close`。
相关写入行：这些 JS 函数写 DOM innerHTML、class、aria、loading/disabled，并调用原 API；CSS 读取 class 和 data/aria state。
目标变化：不改变项目、编排、会议、归档和人工决策的 state/renderer 数据流；统一其 page/modal chrome、controls、forms、status、dialogs、feedback 和 focus。编排保留 frame `147:2`/`148:3` 的 workflow geometry、pipeline canvas、task grouping/directional relationships，且继续不显示“保存编排”；canonical token/component 在冲突时优先。
上下游影响：覆盖项目与会议的大量调用链，但视觉修改不得触及 API object、workflow poll/SSE、drag/drop、task ordering、acceptance、meeting lifecycle、archive governance。
测试锚点：`tests/test_project_orchestration_css.py`、项目 orchestration JS/Python tests、`tests/test_meeting_center_ui.py`、`tests/test_meeting_center_mobile_layout.js`、archive room phase tests、human decision UI/continuation tests；新增代表态截图。
排除的替代点：不改 workflow geometry 来迎合通用卡片；不新增“保存编排”或隐式启动；不改状态 machine、请求顺序、拖拽和确认语义。
未决假设：无阻塞项；pipeline canvas 被记录为 domain-layout exception，外围 UI 不例外。

修改点 ID：MP-08
对应 scenario：The main Virtual Office application is audited；Equivalent controls appear on different surfaces；Multiple transient results occur
文件：`app/skills-library-organization.css:1`、`app/mcp-registry.css:1`、`app/branch-agent-selector.css:1`、`app/style.css:5132`
符号：`.skills-library-modal|.skl-*`；`.mcp-registry-modal|.mcp-*`；`.branch-agent-selector*`
变量：`_sklSkills: Array`、`_sklLibraryData: object`、`_sklEditingName: null|string`、`_mcpServers: Array`、`_mcpAgentsById: object`、catalog CSS rule collections
类型：前端模块状态数组/对象与 CSS rule collection
定义位置：skills `app/skills-library-ui.js:6-8`；MCP `app/mcp-registry-ui.js:3-4`；CSS roots 在上述文件与旧 `app/style.css:5132` legacy section。
当前值来源：skills/MCP API 响应写数组/对象，render 函数输出 cards/forms/status；organization 与 registry CSS 各自定义 modal/card/action/marker；feedback 回退到 `_showOfficeToast/_acpShowToast`。
相关读取行：skills `openSkillsLibrary/renderSkillCards/openSkillEditor` `app/skills-library-ui.js:24-214`；MCP `openMcpRegistry/refreshMcpRegistry/renderMcpRegistry` `app/mcp-registry-ui.js:36-166`。
相关写入行：refresh 函数写数组和 innerHTML；open/close 写 `hidden`；CSS 读取 class；不改 mutation fetch。
目标变化：catalog/registry/selector 保留数据状态与 render path，视觉统一到共享 modal/card/form/button/badge/feedback；旧 `style.css` 中重复 catalog declarations 收敛为兼容布局或删除，避免与专属 CSS 双重定义。
上下游影响：skills organization marker/runs、agent usage、MCP guide/registration 交互不变；MP-04 提供反馈适配。
测试锚点：`tests/test_skill_library_organization_ui_states.js`、`tests/test_skill_library_organization_ui_static.mjs`、`tests/test_mcp_registry_ui_contract.py`、`tests/test_branch_agent_selector_ui.py`。
排除的替代点：不合并 skills 与 MCP 数据模型；不改 API、feature flag、organization polling 或 agent assignment。
未决假设：无阻塞项；legacy `style.css` 规则必须先由 computed-style/selector 测试证明可安全收敛。

修改点 ID：MP-09
对应 scenario：Standalone and public frontends are audited；A migrated action is invoked；A migrated surface is rendered at a narrow viewport
文件：`app/setup.html:7`、`app/models.html:34`、`app/cron.html:20`、`app/setup-settings.js:9`，新增 `app/ui-standalone.css`
符号：各页面 `<head>` stylesheet order 与 inline `<style>`；`nextStep(n)`；`testCodexConnection()`；`testClaudeCodeConnection()`；models/cron 页面现有 inline handlers
变量：standalone `:root` custom properties；HTML `style` declaration blocks；`currentStep: number`；`statusEl: HTMLElement`
类型：CSS token/规则、数字状态与 DOM reference
定义位置：setup inline CSS `app/setup.html:9-68`；models `app/models.html:34-120`；cron `app/cron.html:20-129`；setup state/handlers `app/setup-settings.js:1,9-20,378-435`。
当前值来源：三个页面分别硬编码背景/表面/边框/文字/semantic colors、Press Start 字体、按钮/表单/modal/status；setup test 明确先 `/setup/save` 再调用 test endpoint。
相关读取行：页面 DOM 解析读取 inline CSS；setup handlers 读取 `currentStep`、input 值和 `statusEl`；models/cron inline scripts读取各自表单状态。
相关写入行：`nextStep` 写 active class；test handlers 写 `statusEl.innerHTML` 并发请求；models/cron 写列表、modal、status。视觉迁移不改写入顺序。
目标变化：新增 `ui-standalone.css` 复用 MP-01/02/03/04 的 token/component/dialog/feedback semantics，并在三个入口按统一顺序加载；将 inline presentation 迁出 HTML，保留必要动态 style/handler 与全部 id/onclick/API。setup 的“保存并测试”既有副作用不得被重命名成无副作用 Test。
上下游影响：不改 setup/model/cron 请求、表单字段、i18n、本地状态或导航；窄屏卡片、表单、toolbar、modal 可达性统一。
测试锚点：新增 `tests/test_standalone_ui_contract.py` 与 desktop/narrow smoke；保留 setup/模型/cron 后端合同测试，仅验证相同请求边界。
排除的替代点：不拆分或重写 standalone 业务脚本；不修改 `/setup/save`、provider test、cron API；不把当前“保存并测试”静默改成纯 Test。
未决假设：无阻塞项；动态 `display:none` 等状态 style 可保留，静态装饰 style 迁出。

修改点 ID：MP-10
对应 scenario：Standalone and public frontends are audited；A frontend surface resolves foundation values；A migrated surface is rendered at a narrow viewport
文件：`website/index.html:11`、`website/styles.css:2`、`website/script.js:1`
符号：public site `<head>` stylesheet order；CSS `:root`；`.nav|.btn|.hero|.feature-card|.demo-card|.pricing-card|.setup-*|.faq-*|footer`；website navigation/menu handlers
变量：`--bg`、`--bg-2`、`--bg-3`、`--surface`、`--text`、`--text-dim`、`--accent` 等 marketing aliases；对应 `CSSStyleRule[]`
类型：CSS custom properties、CSS rule collection 与 DOM event handler locals
定义位置：`website/styles.css:2-24` 定义独立 token；`:28` 起定义页面排版和组件；`website/index.html:11-15` 加载 CSS/fonts/i18n；`website/script.js` 绑定公共站交互。
当前值来源：独立 marketing palette 基本接近 Canvas/Accent，但 Surface/Text/字体/spacing/radius 与产品 UI 不同，按钮/card/nav 自建组件语义。
相关读取行：website 所有 style rules 消费 `--bg/--surface/--text/--accent`；HTML class 和 script 交互读取 DOM，不依赖 app backend。
相关写入行：CSS cascade 写视觉；script 仅写 menu/scroll/interaction class，保持不变。
目标变化：让官网 token aliases 指向 canonical foundation，并统一 nav/button/card/badge/form/focus/responsive semantics；保留 hero artwork、demo illustration、marketing composition 作为 domain/public content presentation。
上下游影响：仅 public static frontend；不改文案、链接、下载/CTA 目标、i18n 或脚本行为。
测试锚点：新增 `tests/test_website_ui_contract.py` 与 desktop/mobile screenshots，检查 CTA/focus/menu、无 overflow 和 canonical aliases。
排除的替代点：不把官网重做成应用内页面；不删除营销视觉层级；不修改链接或引入后端依赖。
未决假设：无阻塞项；公共站可保留更大的营销标题字号，但控件与 semantic tokens 必须统一。

修改点 ID：MP-11
对应 scenario：Static UI-system validation runs；Visual acceptance is performed
文件：新增 `tests/test_frontend_ui_system_contract.py`、`tests/test_frontend_ui_component_contract.py`、`tests/test_standalone_ui_contract.py`、`tests/test_website_ui_contract.py` 与视觉验收证据目录
符号：UI source inventory；CSS custom-property definition/reference scanner；entry stylesheet-order assertions；inline-style exception matcher；representative viewport screenshot matrix
变量：`ENTRY_POINTS: tuple[Path,...]`、`SYSTEM_TOKENS: dict[str,str]`、`DOMAIN_VISUAL_EXCEPTIONS: dict[Path,set[str]]`、`PROHIBITED_GLOBAL_ROOTS: set[Path]`
类型：Python immutable test fixtures/collections 与 screenshot manifest
定义位置：当前不存在；已有静态测试采用 `Path.read_text()`，例如 `tests/test_mcp_registry_ui_contract.py:5-7`、`tests/test_agent_management_ui.py:5-8`、`tests/test_project_orchestration_css.py:5-10`。
当前值来源：现有测试分散验证 feature DOM/CSS，缺少跨入口 token 完整性、undefined var、竞争 `:root`、inline presentation、focus state 和 screenshot inventory 的统一门禁。
相关读取行：新 scanner 将读取 `app/index.html`、三个 standalone HTML、`website/index.html` 及其加载的 CSS；现有 feature tests 继续读取原文件。
相关写入行：测试只写临时结果/截图 evidence，不修改生产状态；截图 manifest 记录 viewport、surface、state 与 canonical reference。
目标变化：建立可重复静态门禁与代表性 desktop/narrow visual matrix；识别未定义变量、禁止的 competing global tokens、缺失 focus/disabled/loading/error state、未授权 inline decoration，并允许显式 domain visual exception。运行现有定点交互测试证明业务兼容。
上下游影响：为 MP-01 至 MP-10 提供回归证据；不要求后端改动或真实生产数据写入。
测试锚点：`pytest -q tests/test_frontend_ui_system_contract.py tests/test_frontend_ui_component_contract.py tests/test_standalone_ui_contract.py tests/test_website_ui_contract.py`，相关 Node tests，OpenSpec strict validate，代表态截图人工审阅。
排除的替代点：不只依赖人工截图；不以像素级全页 snapshot 取代语义/交互测试；不把运行时 geometry inline style误报为静态装饰违规。
未决假设：无阻塞项；具体截图启动命令和浏览器基准在 design/tasks 中基于当前可用本地服务固化。

## 依赖顺序与不得修改项

1. `MP-01 -> MP-02/03/04`：先建立 token，再建立组件、dialog、feedback。
2. `MP-02/03/04 -> MP-05..MP-10`：各 surface 只迁移到共享语义，不创建新系统。
3. `MP-11` 从第一项实现起同步落地，并在所有 surface 完成后汇总视觉验收。
4. 全程不得修改 `app/server.py`、`app/services/**`、provider、repository、协议、数据文件、API 路径和 payload；若 UI 目标需要这些变化，按规格直接排除并保留当前行为。
5. 现有 dirty frontend 文件视为当前基线内容，不回退；实现前若变量、类型或读写行发生变化，必须重新运行 CodeGraph 与源码核验并重新确认相应修改点。
