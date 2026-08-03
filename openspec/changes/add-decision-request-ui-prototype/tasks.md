## 1. 组件规则与快照协调（MP-01、MP-04）

- [x] 1.1 在 `tests/check_human_decision_center.mjs` 建立 Node `assert`、`createRequire` 与最小 Fake DOM 测试骨架，先写 `sortPendingDecisions`、`shouldAutoOpenDecision`、`resolveDecisionAnswer` 的失败用例，覆盖关注排序、状态转换和“自定义输入优先于 A-D”；验证命令：`node tests/check_human_decision_center.mjs` 应因实现缺失而失败。
- [x] 1.2 在新文件 `app/human-decision-center.js` 建立 UMD 导出边界并实现三个纯函数；不得访问网络、存储或时钟循环；验证命令：`node tests/check_human_decision_center.mjs` 中 1.1 用例通过。
- [x] 1.3 扩展契约测试，覆盖 `snapshotRevision` 只接纳更大安全整数、重复/旧 revision 防回滚、外部处理清理 `centerState.drafts`、保持或回退 `selectedDecisionId`，并先确认新增用例失败。
- [x] 1.4 实现 `decisionSnapshot`、`snapshotRevision` 与 `centerState` 的初始化和协调函数，使 `update(snapshot)` 原子替换快照、清理草稿、协调选择并只对新关注转换触发一次自动打开；验证命令：`node tests/check_human_decision_center.mjs`。
- [x] 1.5 执行 Task 1 代码审查：逐项对照 MP-01、版本协调设计与相关 scenarios，确认完整快照是唯一业务输入、飞书已处理结果不会被本地草稿覆盖、无越界网络能力；修复发现的问题后重新运行测试。

## 2. 中枢 DOM 生命周期与决策交互（MP-01、MP-04）

- [x] 2.1 先补充 `mount/update/open/close/selectDecision/destroy` 的 Fake DOM 失败用例，覆盖监听器绑定/清理、普通新增只更新徽标、高风险或临近超时自动打开一次、默认选择最需关注事项。
- [x] 2.2 实现 `HumanDecisionCenter.mount` 与公开生命周期方法，使用宿主注入的 `toggle`、`panel`、`callbacks` 和局部 `elements`，不得查询或改写组件范围外 DOM；验证命令：`node tests/check_human_decision_center.mjs`。
- [x] 2.3 先补充待决策列表、历史、详情卡、任务详情展开、A-D、推荐理由、自定义答案、必填提示、提醒/超时和只读结果的失败用例，并验证所有动态文本均经安全 DOM API 写入。
- [x] 2.4 实现列表、徽标、详情与历史渲染以及事件委托；`onSubmit` 仅报告 `{ decisionId, answer, optionId }`，不乐观修改 `decisionSnapshot`；收到飞书已处理快照时清除提交能力并展示 `resolution.channel/resolvedAt/nextAction`。
- [x] 2.5 先补充提交前修改和执行锁定后变更的失败用例，再实现草稿编辑与 `window.VODialogs.showConfirm` 复用；宿主无确认能力时禁用锁定变更，不使用原生 `confirm`。
- [x] 2.6 执行 Task 2 代码审查：对照完整决策详情、提醒超时、提交反馈、修改边界、双端镜像和无重复提交 scenarios，检查焦点、键盘、ARIA 与销毁清理；修复后运行 `node tests/check_human_decision_center.mjs`。

## 3. 作用域样式与响应式行为（MP-02、MP-04）

- [x] 3.1 在契约测试中先声明 `app/human-decision-center.css` 的失败断言：所有业务选择器使用 `.human-decision-center*` 作用域、读取现有 `--ui-*`/`--gold`、包含 900px 窄屏切换且不定义 `.sms-*`。
- [x] 3.2 新增 `app/human-decision-center.css`，实现工具栏入口徽标、双栏收件箱、风险/推荐/提醒/只读状态、任务详情和窄屏列表/详情单视图；不得向 `app/style.css` 追加业务样式。
- [x] 3.3 补充并验证 `aria-live`、选中/展开状态、焦点可见性、长文本换行、无横向滚动和 `99+` 徽标表达所需的 DOM/CSS 契约；验证命令：`node tests/check_human_decision_center.mjs`。
- [x] 3.4 执行 Task 3 代码审查：对照 SMS 产品范式和现有设计令牌，确认只复用视觉语言而未复制 SMS 业务逻辑，桌面与窄屏核心路径完整；修复后重新运行契约测试。

## 4. 可删除的控制面板展览宿主（MP-03、MP-04）

- [x] 4.1 先在契约测试中声明临时宿主边界：`app/human-decision-center-prototype.html` 只包含模拟工具栏、状态控件、入口和 panel host；`app/human-decision-center-prototype.js` 是唯一示例数据持有者，组件源码不得包含 `DEMO_SNAPSHOTS`。
- [x] 4.2 新增 `app/human-decision-center-prototype.html`，加载组件与作用域样式，显著标识“静态模拟/不连接真实飞书和生产数据”，并提供可在浏览器直接打开的 VO 控制面板展览环境。
- [x] 4.3 新增 `app/human-decision-center-prototype.js`，实现 `DEMO_SNAPSHOTS`、`showcaseState` 和 `simulatedDashboard.decisions`；覆盖普通、高风险、临近超时、三次提醒、两种超时结果、已提交可修改、执行锁定、历史等验收状态。
- [x] 4.4 增加“飞书已处理”演示：生成更高 revision 的完整快照，把当前事项迁移为 `resolved` 且 `resolution.channel = "feishu"`，通过 `center.update(simulatedDashboard.decisions)` 驱动徽标、队列和只读详情实时更新。
- [x] 4.5 实现展览范围内的本地提交和变更回调，仅生成新的内存快照；测试并确认源码不存在 fetch、EventSource、WebSocket、localStorage、机器人发送和生产 API 写入。
- [x] 4.6 执行 Task 4 代码审查：对照所有 UI scenarios 和“删除两个 prototype 文件不影响组件”的边界，确认展览数据没有泄漏进组件；修复后运行 `node tests/check_human_decision_center.mjs`。

## 5. 验证与 UI 交付门禁

- [x] 5.1 运行新增测试 `node tests/check_human_decision_center.mjs`，并运行回归测试 `node tests/check_project_orchestration_task_dialog.mjs`、`node tests/test_management_token_dialog.js`、`.venv/bin/python -m pytest -q tests/test_meeting_center_ui.py`、`.venv/bin/python -m pytest -q tests/test_dashboard_realtime.py` 和 `node tests/check_dashboard_realtime_static.mjs`。
- [x] 5.2 使用本地浏览器完成桌面与窄屏 UI 评审，并在正式 VO 页面复验 ABCD、自定义优先、历史、锁定和 SSE 迁移。
- [x] 5.3 执行最终范围审查、范围内 whitespace 检查和 `openspec validate add-decision-request-ui-prototype --json`；正式集成文件限定为 OpenSpec 6～10 节声明的服务、薄接线、生产适配器、SSE、飞书和 Skill。
- [x] 5.4 向用户交付静态 HTML 路径、测试证据和已知边界并暂停，等待 UI 确认；未经确认不得删除 prototype 文件或进入正式控制面板/SSE/飞书集成阶段。

## 6. 权威决策状态与 API

- [x] 6.1 在新服务模块实现原子持久化、单调 revision、幂等创建、ABCD/自定义答案优先级、终态冲突与执行前重开边界。
- [x] 6.2 新增创建、快照、提交和重开 REST API；遗留 server 仅保留薄路由接线。
- [x] 6.3 为状态服务和 API 增加聚焦测试，覆盖任务、会议、聊天来源及安全投影。

## 7. 正式控制面板与 SSE

- [x] 7.1 在正式工具栏加入决策入口与面板宿主，并通过新适配器挂载已确认组件。
- [x] 7.2 将 `decisions` 加入现有 Dashboard 快照、差量事件和 fetch 降级；不得创建第二个 EventSource。
- [x] 7.3 增加后端 SSE 与前端静态/交互测试，验证飞书处理后本地队列实时迁移。

## 8. 飞书投递与回调

- [x] 8.1 复用 `feishu_notifications` 构建带情景、ABCD、自定义输入和提交动作的卡片。
- [x] 8.2 优先使用通知机器人；未配置时降级到聊天机器人配置的回退会话。
- [x] 8.3 飞书回调写入同一状态权威，自定义输入优先，并将已处理终态更新回原卡片。
- [x] 8.4 增加投递、降级、幂等回调、冲突与卡片终态更新测试。

## 9. 通用决策 Skill

- [x] 9.1 新增任务、会议、聊天共用的 VO 人工决策 Skill，明确触发条件、受影响分支等待、请求/响应契约和自定义答案优先级。
- [x] 9.2 将 Skill 加入 VO 操作指南路由并验证可通过 `/skills/vo-human-decision/SKILL.md` 发现。
- [x] 9.3 将共享决策升级规则注入聊天、会议和项目执行 Prompt；验证重大未授权选择进入决策中枢，普通可验证不确定性继续自主处理。

## 10. 最终验收

- [x] 10.1 运行聚焦测试、相关 Dashboard/飞书回归、广覆盖测试与 OpenSpec 校验，并记录既有全仓阻塞。
- [x] 10.2 在桌面与窄屏正式 VO 页面完成浏览器 E2E：入口、弹窗、提交、历史与 SSE 更新。
- [x] 10.3 完成飞书侧投递/回调/卡片终态及 VO 实时同步验收；保存可复核证据。
- [x] 10.4 UI 确认后删除临时 HTML 与示例控制器；生产入口只加载独立组件与正式适配器。

## 11. 聊天决策完成后自动续跑

- [x] 11.1 在聊天 Prompt 暴露可信的 Agent/provider/conversation 上下文，并更新 Skill：chat 的 `source.id` 必须使用当前 `conversationId`，创建后当前 turn 结束而非轮询。
- [x] 11.2 在权威 Store 中持久化私有聊天续跑绑定与 `waiting/queued/running/retry_wait/completed/failed/uncertain` 状态机，安全投影不得泄漏绑定、token、租约或原始错误。
- [x] 11.3 新增聚焦的聊天续跑模块，通过共享 XML formatter 构造不可信数据边界，原子领取并区分成功、可安全重试和不确定投递结果。
- [x] 11.4 让本地、飞书与低风险超时首次终态统一排队续跑，重复回调不得重复调度；周期处理可恢复排队任务。
- [x] 11.5 复用 VO Agent 通信服务在原 Agent/原 conversation 内投递稳定来源消息，服务端只从可信 Agent API 请求头建立绑定。
- [x] 11.6 运行 Store、Workflow、飞书、HTTP、Prompt、Skill、通信与 Dashboard 回归测试，并完成 OpenSpec 校验。

## 12. 会议与项目任务决策完成后原生续跑

- [x] 12.1 将私有续跑绑定泛化为 `chat/meeting/task`，保留聊天兼容接口，并让 task 来源安全保存 `projectId`。
- [x] 12.2 新增会议适配器：仅对绑定同一 decision 的 `awaiting_user_decision` 会议执行幂等 `continue_decision`，再唤醒原会议运行器。
- [x] 12.3 新增项目任务适配器：活动 attempt 创建决策后保持非终态，Provider 返回不得进入 Review/完成；resolve 后复用原 attempt 并只重投当前 task。
- [x] 12.4 通过统一 continuation dispatcher 复用原子 claim、租约、三次重试和 uncertain 语义，按来源分派原生 adapter。
- [x] 12.5 更新 Skill：会议使用真实 meetingId，项目任务同时携带 projectId/taskId，三种来源创建后均结束当前 turn 且不轮询。
- [x] 12.6 运行 Store、dispatcher、会议生命周期、项目 lifecycle、Prompt、飞书/HTTP 与 Dashboard 聚焦回归，并完成严格 OpenSpec 校验。
