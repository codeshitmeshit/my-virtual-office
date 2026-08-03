## Why

VO 在任务、会议或聊天执行中会产生需要人工裁决的事项。用户需要在 VO 控制面板中拥有一个低干扰、可追溯的人工决策中枢，集中查看待决策队列、处理单个决策并回看历史，而不是依赖零散弹窗或进入其他页面。

## What Changes

- 新增一个面向 VO 控制面板的人工决策中枢组件：固定入口、待决策徽标、待处理列表、选中事项完整决策卡和已处理历史。
- 普通新决策只更新入口徽标；高风险或即将超时的决策自动打开中枢并聚焦对应事项。
- 中枢消费带版本号的完整决策快照；当用户已在飞书处理某事项时，下一份快照立即更新徽标，并将该事项从待决策迁移到只读历史。
- 决策详情覆盖情景、风险、超时后果、ABCD、VO 推荐、自定义输入、提交、任务详情、提醒、超时和修改边界。
- UI 评审阶段使用临时本地 HTML 展览页；确认设计并完成正式集成后删除该展览页。
- 将已确认的中枢组件嵌入 VO 正式控制面板，并复用现有 Dashboard SSE 的 `decisions` 分区实现实时同步。
- 新增统一决策状态权威、REST API、飞书卡片投递/回调/终态更新，以及可由任务、会议和聊天共同调用的 VO Skill。
- 聊天来源的决策完成后，由后端在页面关闭时仍可自动唤醒原 Agent，并在原 conversation 中继续暂停分支；会议和项目本期不接入此续跑器。

## Capabilities

### New Capabilities

- `human-decision-center-ui`: 定义 VO 控制面板人工决策中枢的入口提醒、队列与历史、决策详情、生命周期、响应式行为和可删除展览宿主。

### Modified Capabilities

无。

## Non-goals

- 不把临时展览页作为生产页面或正式入口；它在最终验收后可以删除。
- 不新建第二条 SSE、WebSocket 或轮询通道。
- 不复制飞书鉴权、投递和卡片更新轮子；复用现有通知基础设施。
- 本次不自动改变会议或项目执行器的业务状态；聊天仅恢复原 conversation 中明确暂停的分支。
- 不提供搜索、统计、批量决策或复杂管理后台能力。

## Impact

- 新增独立人工决策中枢组件、作用域样式、正式控制面板适配器、统一状态服务、API、飞书交付工作流、SSE 分区和通用 Skill。
- 已按 UI 评审约定删除临时展览页和示例控制器；正式入口仅加载复用组件和生产适配器。
- 复用现有 Dashboard SSE 与飞书通知基础设施，遗留入口只增加薄接线。

## Repository Evidence

- 基线仓库：`/Users/bytedance/cosh/my-virtual-office`，commit `fbfc259c6205ba12d8e12035ce9cc08e7d17bc6a`。
- CodeGraph 1.5.0 当前索引：761 files、18,689 nodes、63,896 edges；解析失败项均为已不存在的历史 OpenSpec 元数据，不覆盖候选代码。
- `app/index.html:360-377` 是 VO 工具栏，`app/index.html:374` 的 `#sms-toggle` 证明固定工具栏入口模式已经存在。
- `app/index.html:983-1035`、`app/style.css:1625-1875` 和 `app/sms-panel.js:1-120,273-331` 已实现“入口 + 数量徽标 + 左侧列表 + 右侧详情”的收件箱范式；决策中枢复用其产品模式和基础设计令牌，不复制 SMS 业务逻辑。
- `app/style.css:2141-2155` 与 `app/sms-panel.js:952-960` 已实现工具栏关注徽标；决策中枢沿用同一视觉语言和数量封顶表达。
- `app/style.css:3990-4015` 与 `app/sms-panel.js:566-589` 已实现窄屏列表/详情切换；决策中枢沿用该响应式行为。
- `app/style.css:138-150` 已定义 `--ui-bg`、`--ui-surface`、`--ui-border`、`--ui-text`、`--gold`；组件不得复制全局令牌。
- `app/vo-dialogs.js:20-37,48-131,134-150` 已提供带键盘和焦点处理的 `window.VODialogs.showConfirm`；执行锁定后的变更确认直接复用。
- `app/project-orchestration-task-dialog.js:1-169` 已采用浏览器/Node 双用 UMD 边界；现有 Fake DOM 契约测试模式可直接复用。
- `app/dashboard_realtime.py:174-209,221-267` 已集中构造 Dashboard 快照、计算分区差异并通过同一 SSE 流发送事件；决策状态应作为新的 `decisions` 分区接入，而不是另建推送通道。
- `app/dashboard-realtime.js:168-174,215-268` 已使用唯一的 `/api/dashboard/events` `EventSource` 分发快照和分区事件，并带现有 fetch 降级；正式接入时只增加 `dashboard.decisions` 状态和组件更新钩子。
- `app/server.py:29126-29132` 已集中注入 Dashboard SSE 的数据加载器，适合作为后续决策安全投影加载器的接线点。
- 修改前基线：`node tests/check_project_orchestration_task_dialog.mjs` 通过；`node tests/test_management_token_dialog.js` 通过；`.venv/bin/python -m pytest -q tests/test_meeting_center_ui.py` 为 `6 passed`。
- SSE 修改前基线：`.venv/bin/python -m pytest -q tests/test_dashboard_realtime.py` 为 `8 passed`；`node tests/check_dashboard_realtime_static.mjs` 通过。

## Proposed Follow-up Integration Boundary

- 飞书卡片提交与本地提交必须写入同一份权威决策状态；组件本身不判断哪个入口获胜。
- 正式控制面板复用 `/api/dashboard/events`，在快照和差量事件中增加 `decisions` 分区；不得创建第二个 `EventSource`、WebSocket 或轮询循环。
- 后端决策加载器只向 Dashboard 输出控制面板所需的安全投影；现有 Dashboard fetch 降级路径同时覆盖该分区。
- `app/dashboard-realtime.js` 维护 `dashboard.decisions`，收到较新快照后通过薄适配调用 `HumanDecisionCenter.update(snapshot)`。
- 组件不拥有网络连接、飞书回调或持久化，只按 `revision` 协调完整快照；重复或过期快照不得回滚已处理状态。
- 本阶段的 MP-03 用示例控制器模拟同一 `dashboard.decisions` 契约和“飞书已处理”事件。UI 确认后，再单独规格化并实施权威状态服务、飞书回调与正式 SSE 接线。

## Modification Points

### MP-01 人工决策中枢组件

修改点 ID: MP-01
对应 scenario: 固定入口；徽标提醒；高风险自动打开；待决策队列；历史；完整决策详情；生命周期；响应式切换
文件: app/human-decision-center.js
符号: HumanDecisionCenter；sortPendingDecisions；shouldAutoOpenDecision；resolveDecisionAnswer；mount；update；open；close；selectDecision；destroy
变量: centerState；decisionSnapshot；snapshotRevision；elements；callbacks
类型: HumanDecisionCenterState；HumanDecisionSnapshot；number；Record<string, HTMLElement>；HumanDecisionCenterCallbacks
目标变化: 新增可嵌入 VO 控制面板、同时管理入口徽标、决策列表、详情卡和历史的独立组件
未决假设: 无

- 当前定义/读写：文件尚不存在；`mount({ toggle, panel }, snapshot, callbacks)` 计划绑定正式页面或展览页提供的入口和 panel host；`update(snapshot)` 替换只读决策快照；交互只写 `centerState` 并通过回调报告操作。
- `decisionSnapshot` 来源：正式阶段由 `dashboard.decisions` 提供；本期只来自 MP-03 示例控制器。`update(snapshot)` 仅接纳更新 revision，并用完整快照协调待处理、历史、徽标和当前详情。
- `centerState` 写入：打开/关闭、待处理/历史视图、选中 ID、A-D、自由输入、详情展开和窄屏 list/detail 视图。
- 关键规则：普通新增仅更新徽标；`shouldAutoOpenDecision` 仅对高风险或临近超时事项返回 true；无手动选择时默认聚焦最需关注事项。
- 外部处理规则：当前事项若在新快照中已由飞书处理，组件立即清除本地草稿和重复提交能力，将其展示为包含最终答案、处理入口、处理时间与下一步动作的只读历史项。
- 复用：调用 `window.VODialogs.showConfirm` 处理锁定后的变更确认；使用现有 UMD、DOM 文本安全写入和回调边界。
- 排除替代点：本期不修改 `app/index.html`、`sms-panel.js`、`chat.js`、会议模块或后端；不内置示例数据、fetch、WebSocket、EventSource、localStorage 或调度器。

### MP-02 中枢作用域样式

修改点 ID: MP-02
对应 scenario: 工具栏入口徽标；双栏中枢；风险关注态；窄屏列表/详情切换
文件: app/human-decision-center.css
符号: .human-decision-center-toggle；.human-decision-center；.human-decision-center__list；.human-decision-center__detail；.human-decision-center__history；@media (max-width: 900px)
变量: 现有 --ui-* 与 --gold custom properties
类型: CSS custom properties 与 scoped selectors
目标变化: 新增与 VO 控制面板一致、可独立复用的中枢面板和响应式样式
未决假设: 无

- 只使用 `.human-decision-center*` 前缀，读取现有设计令牌；JS 通过 `data-state`、`data-risk`、`aria-*` 和状态 class 表达 UI。
- 桌面复用 SMS 的双栏交互模式；900px 以下复用 list/detail 单视图与返回列表行为，但不引用或覆盖 `.sms-*` 选择器。
- 不向 5,000+ 行的 `app/style.css` 追加业务样式，不复制 SMS 拖拽、缩放、联系人和消息能力。

### MP-03 已删除的控制面板展览页

修改点 ID: MP-03
对应 scenario: 本地验收完整中枢；普通徽标提醒；高风险自动打开；无真实业务副作用
文件: app/human-decision-center-prototype.html；app/human-decision-center-prototype.js
符号: #human-decision-center-showcase；#human-decision-center-toggle；#human-decision-center-panel；HumanDecisionCenterPrototype；mountShowcase
变量: DEMO_SNAPSHOTS；showcaseState；simulatedDashboard
类型: Readonly<Record<string, HumanDecisionSnapshot>>；{ view: string }；{ decisions: HumanDecisionSnapshot }
目标变化: UI 评审阶段曾提供临时展览宿主；正式集成验收后已整体删除
未决假设: 无

- 临时文件曾覆盖普通待决策、高风险、临近超时、提醒、超时、修改、锁定、历史和飞书迁移等 UI 评审状态。
- 正式控制面板 E2E 通过后删除这两个文件；组件、生产适配器和回归测试不依赖展览数据。

### MP-04 中枢与展览宿主契约测试

修改点 ID: MP-04
对应 scenario: human-decision-center-ui 全部 scenarios
文件: tests/check_human_decision_center.mjs
符号: FakeElement；createDocument；center contract；showcase separation assertions
变量: html；css；Center；Prototype
类型: string；string；HumanDecisionCenter module；HumanDecisionCenterPrototype module
目标变化: 新增零第三方依赖的中枢规则、DOM 行为、无副作用和展览宿主可删除性验证
未决假设: 无

- 复用 Node `assert`、`fs`、`createRequire` 和现有 Fake DOM 测试惯例。
- 验证：关注排序、普通徽标、高风险/临近超时自动打开、队列/历史、答案优先级、三次提醒风险分支、编辑锁定、飞书处理快照协调、revision 去重与防回滚、mount/update/open/close/destroy、回调、确认框复用、响应式规则和无网络副作用。
- 不新增 jsdom、Playwright 或前端框架；视觉细节由本地浏览器验收补足。
