# 变量级修改点分析

## 分析基线

- 仓库：`/Users/bytedance/cosh/my-virtual-office`
- Git 基线：`c17c1e474ce8c9f5e4a16bc30006b8412d39734f`
- CodeGraph：`.codegraph/` 存在；已先使用 `codegraph explore` 检查 Human Decisions、Agent profile 与相关调用面，再以当前工作区源码逐行复核。索引报告存在 pending changes，因此行号与最终判断以当前源码为准。
- OpenSpec：`openspec validate add-personal-assets --json` 通过。
- 基线测试：`60 passed`，Agent Guide 静态检查通过。
  - `tests/test_human_decisions.py`
  - `tests/test_human_decision_workflow.py`
  - `tests/test_hr_agent_auth.py`
  - `tests/test_hr_http_contract.py`
  - `tests/test_human_decision_skill.py`
  - `node tests/check_agent_guide_static.mjs`

## 已核验的权威边界

1. `app/services/human_decisions.py:84-286` 的 `HumanDecisionStore` 已是决策唯一持久化权威，具有 revision、幂等创建、A-D 选项、终态冲突保护与原子写入；`app/services/human_decision_workflow.py:43-165` 负责投递、终态更新和 continuation。个人资产不得复制 decision status、resolution 或历史。
2. `HumanDecisionStore.process_due`（`app/services/human_decisions.py:639` 起）会在提醒耗尽后按推荐项自动决议。敏感读取请求必须把拒绝设为安全推荐；只有明确、结构化的批准选项可以释放数据，自由文本和超时结果不能被推断为批准。
3. `app/services/agent_profile_store.py:170-384` 提供了适合本功能复用的实现范式：独立 schema、乐观 revision、局部 patch、0600 原子替换。但 Agent profile 是 Agent 资料而非 owner 资料，不能作为个人资产的数据权威。
4. 当前 `app/server.py:28868-28886` 的 Human Decisions Agent 门禁只校验 loopback、Origin、action 和非空 Agent ID；`app/services/hr_agent_auth.py` 还校验 Agent 已注册且 active。个人资产读取会披露 owner 数据，必须采用后者级别的身份校验，不能照搬较弱门禁。
5. `app/server_routes.dispatch` 当前没有接入 `OfficeHandler`；可验证的模块化 HTTP 范式是 `app/services/hr_http.py` 加 `app/server.py:29345-29557,29779-29781,32490-32492` 的薄委派。
6. `app/index.html:363-385,941-968,1249-1263` 与独立的 `archive-room.js/css`、`human-resources.js/css` 证明顶栏入口、modal host、聚焦 JS/CSS 是现有 UI 集成边界。业务样式不应继续堆入大型 `app/style.css`。
7. VO Skill 由 `skills/catalog.md` 暴露，`app/agent-guide.js:10-35` 提供分类元数据，`skills/vo-operating-guidelines/SKILL.md` 承担意图路由；建档引导应进入这条链路，不应再创建页面向导。

## 修改点卡片

### MP-PA-01 个人资产持久化权威

修改点 ID：MP-PA-01  
对应 scenario：创建内置信息；追加未建模信息；更新单条；删除单条；非法或冲突写入；标记敏感；建议等待确认。  
仓库/基线：本仓库 / `c17c1e474ce8c9f5e4a16bc30006b8412d39734f`  
文件：计划新增 `app/services/personal_asset_store.py`。  
符号：计划新增 `PersonalAssetStore`、`PersonalAssetEntry`、`PersonalAssetSuggestion`、`PersonalAssetAccessLink`、`PersonalAssetUsageRecord`、`PersonalAssetStoreError`、`PersonalAssetValidationError`、`PersonalAssetConflictError`。  
变量与类型：

- 根对象 `root: dict[str, object] = {schemaVersion, revision, entries, suggestions, accessLinks, usageRecords}`。
- `entries: dict[str, PersonalAssetEntry]`；entry 字段为 `id: str`、`category: str`、`label: str`、`value: JSONValue`、`sensitivity: "standard" | "sensitive"`、`revision: int`、`createdAt/updatedAt: str`。
- `suggestions: dict[str, PersonalAssetSuggestion]`；保存 proposal、来源、状态和幂等键，但在 owner 接受前不写入 `entries`。
- `accessLinks: dict[str, PersonalAssetAccessLink]`；只保存 `requestId -> decisionId/request scope/requestingAgent/taskContext/expiry` 的关联，不保存或复制 HUMAN DECISIONS 的授权状态。
- `usageRecords: list[PersonalAssetUsageRecord]`；只保存 Agent、任务上下文、entry IDs/category scope、时间和 outcome，不复制 entry value。

类型：owner profile authority / 乐观并发 / 原子持久化。  
当前定义/读写：文件不存在；现有 `AgentProfileStore.update`（`app/services/agent_profile_store.py:305-361`）已验证 expected revision、局部合并和原子写入模式，`_atomic_write`（363-384）已验证 0600 临时文件替换模式。  
目标变化：在 `STATUS_DIR/personal-assets.json` 建立单一 owner profile 权威；内置 category 只是稳定枚举提示，任意自定义 label/category 仍可持久化；所有 create/update/delete/accept-suggestion 操作在同一锁内验证 expected revision 并原子提交。敏感值只存在权威 entry/suggestion 中，不写入访问日志或决策关联。  
上游：MP-PA-02 owner 命令、MP-PA-03 Agent 读取/建议/Skill 确认写入。  
下游：MP-PA-04 HTTP 投影、MP-PA-05 UI。  
测试锚点：计划新增 `tests/test_personal_asset_store.py`，覆盖重启持久化、扩展 category、局部更新、删除隔离、revision 冲突、损坏 JSON、原子替换失败、0600 权限、建议接受幂等、usage 不含 value。  
排除方案：不写入 `office-config.json`；不复用 Agent profile；不使用 localStorage；不把 decisions 嵌入本 store。  
未决假设：当前 VO 是单 owner 部署，现有管理 token 即 owner 管理边界；若未来支持多用户，需要把 owner ID 引入 schema 与鉴权，不能仅靠当前单文件模型扩展。

### MP-PA-02 Owner 管理与建议确认应用服务

修改点 ID：MP-PA-02  
对应 scenario：Owner 打开个人资产；创建/更新/删除；待确认建议；接受或拒绝建议；建档确认后批量保存。  
文件：计划新增 `app/services/personal_asset_service.py`。  
符号：计划新增 `PersonalAssetService.snapshot/create_entry/update_entry/delete_entry/list_suggestions/accept_suggestion/reject_suggestion/apply_confirmed_batch`、`PersonalAssetServiceResult`。  
变量与类型：`expectedRevision: int`、`entryPatch: Mapping[str, object]`、`confirmedChanges: Sequence[Mapping[str, object]]`、`suggestionId: str`、`idempotencyKey: str`、`source: {kind, agentId, contextId}`。  
类型：transport-free application service / owner command boundary。  
当前定义/读写：不存在；`app/services/hr_http.py` 已证明 HTTP 解析可与应用服务分离，`HumanDecisionWorkflow` 已证明 workflow 组合应在 service 层而非 handler 内完成。  
目标变化：集中执行 owner CRUD、批量建档确认与 suggestion 终态转换；`apply_confirmed_batch` 要么整批通过并提交，要么保持原 profile 不变；接受建议时在同一 store transaction 中写 entry 与 suggestion terminal state。返回 owner-safe 完整值投影，但不包含内部 idempotency 或 access linkage。  
上游：MP-PA-04 管理 HTTP；MP-PA-03 的手动 Skill 确认写入口。  
下游：MP-PA-01 store。  
测试锚点：计划新增 `tests/test_personal_asset_service.py`，覆盖 batch 原子性、部分 patch 保留无关 entry、suggestion accept/reject、重复请求、稳定错误码和 owner 投影。  
排除方案：不在 `app/server.py` 直接操作 JSON；不让前端组合“接受建议 + 新建 entry”两个非原子请求。  
未决假设：无。

### MP-PA-03 任务级 Agent 访问、敏感决策与 Skill 写入边界

修改点 ID：MP-PA-03  
对应 scenario：读取相关非敏感上下文；拒绝无目的全量读取；敏感读取发起/批准/拒绝或超时；成功披露留痕；Agent 用于项目判断；Agent/工作流提出建议；Skill 经 owner 明确确认后保存。  
文件：计划新增 `app/services/personal_asset_agent_auth.py`、`app/services/personal_asset_agent_access.py`、`app/services/personal_asset_agent_api.py`。  
符号：计划新增 `PersonalAssetAgentAuthenticator.authenticate`、`AuthenticatedPersonalAssetAgent`、`PersonalAssetAgentAccess.request_context`、`PersonalAssetAgentAccess.submit_suggestion`、`PersonalAssetAgentAPI.apply_owner_confirmed_changes`、`SensitiveAccessDecisionTemplate`。  
变量与类型：

- 身份输入 `remoteHost/origin/action/aiId`，action 固定 `personal-assets`；输出必须是 HR repository 中 `status == active` 的 Agent identity。
- 读取输入 `entryIds: list[str]`、`purpose: str`、`taskContext: {type: task|meeting|chat, id, label, projectId?}`、`requestId/idempotencyKey: str`。
- 非敏感输出 `entries: list[{id, category, label, value, sensitivity}]`；敏感未决输出 `decisionId: str`、`status: "decision_required"`，不含 value。
- 决策模板固定四项机器语义：`A=拒绝`、`B=仅允许一次披露`、`C=允许当前任务范围`、`D=缩小范围/自定义处理`；安全 recommendation 固定为 A。只有明确 B/C 且 scope 匹配时视为批准；D/自由文本必须保持不披露，直到能得到结构化批准范围。
- owner-confirmed Skill 写入携带 `confirmedChanges`、`taskContext`、`confirmationSummaryDigest`、`idempotencyKey`；服务端记录来源但不保存整段聊天。

类型：trusted Agent capability / disclosure policy / Human Decisions adapter。  
当前定义/读写：`HumanDecisionWorkflow.create`（`app/services/human_decision_workflow.py:46-81`）会创建唯一决策并绑定 task/meeting/chat continuation；`snapshot`（43-44）读取权威终态。`HumanDecisionStore.create`（`app/services/human_decisions.py:152-245`）要求 A-D，`resolve`（247-286）保护终态冲突，`process_due`（639 起）会按推荐项超时收口。  
目标变化：

1. 标准条目：验证 active Agent、具体 entry IDs、purpose 与 taskContext 后只返回请求子集，并在同一成功路径追加一条脱敏 usage record。
2. 敏感条目：首次请求通过注入的 `HumanDecisionWorkflow.create` 创建安全拒绝优先的 HUMAN DECISIONS 请求，并在 MP-PA-01 只保存 linkage；continuation 恢复或重试时按 decisionId 读取权威 snapshot。不得在个人资产中维护 approval status/history。
3. `B` 每个 access request 最多成功披露一次；`C` 只对同一 Agent、同一 taskContext、同一 approved entry scope 生效；扩大 scope 必须新建决策。拒绝、超时推荐 A、scope 不匹配、未知或自由文本结果一律不披露。
4. Agent suggestion 只进入 pending suggestions。手动 onboarding Skill 在展示精确变更摘要并得到 owner 明确确认后，才调用幂等 batch write；普通 Agent 不能借该接口声称任意对话已获 owner 授权，因此 API 必须将调用来源限定为显式 Skill 操作契约并留下来源审计。

上游：MP-PA-04 Agent HTTP；MP-PA-06 onboarding Skill。  
下游：MP-PA-01 store、MP-PA-02 batch service、现有 `HumanDecisionWorkflow`。  
测试锚点：计划新增 `tests/test_personal_asset_agent_auth.py`、`tests/test_personal_asset_agent_access.py`、`tests/test_personal_asset_agent_api.py`，覆盖非 loopback/Origin/错误 action/未知或 inactive Agent、最小披露、全量拒绝、敏感值零提前泄漏、A/B/C/D、超时默认拒绝、一次性消费、task/scope 绑定、重试幂等、usage 去值、Skill 确认写入与普通建议隔离。  
排除方案：不把完整 profile 注入默认 Agent prompt；不复用较弱的 `_reject_untrusted_human_decision_agent_request`；不把“decision 已 resolved”笼统解释为批准；不创建第二套授权页面或状态机。  
未决假设：当前 Agent 调用协议没有可独立验证的“owner 在聊天中确认”签名。设计阶段需把 Skill 写入口限制为本地 active Agent + 显式操作类型 + 精确摘要摘要值 + 幂等 task context，并明确这是单 owner trusted-Agent 边界；若需要对恶意 Agent 也安全，则必须增加签名 confirmation receipt，属于扩展范围。

### MP-PA-04 模块化 Runtime 与 HTTP 接线

修改点 ID：MP-PA-04  
对应 scenario：所有 owner 管理、Agent 读取、建议与 Skill 持久化场景。  
文件：计划新增 `app/services/personal_asset_runtime.py`、`app/services/personal_asset_http.py`；最小修改 `app/server.py`。  
符号：计划新增 `PersonalAssetRuntime`、`build_personal_asset_runtime`、`PersonalAssetHTTPRoutes.handles/is_management/management_get/management_post/agent_post`；`app/server.py` 仅新增 lazy runtime getter、auth request 组装和 GET/POST 薄委派。  
变量与类型：`MANAGEMENT_PREFIX = "/api/personal-assets"`、`AGENT_PREFIX = "/api/agent/personal-assets"`、`PersonalAssetHTTPResponse(status, payload)`、`_personal_asset_runtime` 与 lock。  
类型：composition root / transport adapter。  
当前定义/读写：`HRHTTPRoutes` 与 `app/server.py:22908-22909,22963-22988,29345-29557,29779-29781,32490-32492` 是当前已接线的模块化范式；`server_routes.dispatch` 未接线，不能只新增 route module 后宣称可达。  
目标变化：runtime 注入 `STATUS_DIR`、HR Agent repository、`HUMAN_DECISION_WORKFLOW` 与 clock；HTTP 层只做 path/query/body 解析、管理 token 分流、Agent auth request 转换和错误码映射。`server.py` 不包含 profile 校验、敏感策略、suggestion 状态转换或 persistence 决策。  
上游：OfficeHandler。  
下游：MP-PA-01/02/03。  
测试锚点：计划新增 `tests/test_personal_asset_http.py`、`tests/test_personal_asset_server_wiring.py`，覆盖 management token、Agent header、body size、404、稳定状态码、重启 runtime、thin-wiring 静态断言；OPTIONS 对 Agent 路径拒绝 browser Origin。  
排除方案：不把新业务分支直接堆入 `do_GET/do_POST`；不依赖未启用的 `server_routes.dispatch`；不新建第二个 HUMAN DECISIONS endpoint。  
未决假设：无。

### MP-PA-05 与现有 VO 风格一致的三态管理 UI

修改点 ID：MP-PA-05  
对应 scenario：Owner 从导航打开；查看持久化概览；进入新建/编辑；确认待处理建议；页面上不存在 onboarding 与敏感授权。  
文件：计划新增 `app/personal-assets.js`、`app/personal-assets.css`；最小修改 `app/index.html`、`app/locales/zh.json`、`app/locales/en.json`。  
符号：计划新增 `window.PersonalAssets`、`openPersonalAssets/closePersonalAssets`、`loadSnapshot`、`renderOverview`、`renderEditor`、`renderSuggestions`、`saveEntry/deleteEntry/resolveSuggestion`。  
变量与类型：

- `state = {open, loading, revision, entries, suggestions, view, selectedEntryId, editorDraft, busyAction, notice, error, returnFocus}`。
- `view: "overview" | "editor" | "suggestions"`，禁止 `onboarding` 或 `authorization` 状态。
- DOM host：`#personalAssetsModal`、`#personal-assets-content`；toolbar 按钮 `#personal-assets-toggle`。

类型：focused browser module / scoped CSS / i18n UI。  
当前定义/读写：`app/index.html:363-385` 是顶栏；`941-968` 展示 modal host 模式；`1249-1263` 装载聚焦 JS。`archive-room.js:1` 与 `human-resources.js:1` 使用封装 state、转义和现有 modal 交互。  
目标变化：在 Archive Room 与 Human Resources 同级增加“🧠 个人资产”入口与说明性 title/i18n；modal 打开时入口使用现有 active 视觉语义并设置 `aria-current`，关闭时恢复焦点。UI 严格只有 overview/editor/suggestions：概览按内置与扩展分类展示敏感标签；编辑支持 label/category/value/sensitivity；建议页支持查看差异、接受、编辑后接受、拒绝。不存在“Skill 引导建档”页面，也不存在“允许 Agent 读取敏感信息”控件或卡片。  
样式约束：新 CSS 只使用 `.personal-assets-*` 作用域并读取现有 VO 色彩/边框/字号语言；桌面与窄屏均覆盖，Figma 原型只作为结构验收，不引入与基准站不同的新视觉体系。  
上游：toolbar 与 owner 操作。  
下游：MP-PA-04 management API。  
测试锚点：计划新增 `tests/check_personal_assets_ui.mjs` 与浏览器验收脚本，验证三态、导航 active/注释、DOM 文本转义、i18n、revision 冲突刷新、无 onboarding/authorization 文案与控件、响应式 CSS。  
排除方案：不保留此前 Figma 的独立敏感授权页；不保留页面建档引导；不向 `style.css` 追加业务样式；不引入前端框架。  
未决假设：无。

### MP-PA-06 手动触发的个人资产建档 Skill 与发现链路

修改点 ID：MP-PA-06  
对应 scenario：Owner 手动调用；打开页面不自动引导；逐步收集/跳过/停止/继续/追加；确认后写入；修正或取消；敏感条目不产生 standing authorization。  
文件：计划新增 `skills/vo-personal-assets/SKILL.md`；修改 `skills/catalog.md`、`skills/vo-operating-guidelines/SKILL.md`、`app/agent-guide.js`；扩展 `tests/check_agent_guide_static.mjs`；计划新增 `tests/test_personal_asset_skill.py`。  
符号：`categoryById["vo-personal-assets"] = "workspace"`（或新增独立 personal category；优先复用 workspace 以避免只含一个条目的分类）、catalog path、operating-guideline intent route。  
变量与契约：Skill 使用对话内 `collectionDraft`（不持久化权威 profile）、`skippedTopics`、`confirmedChanges`、`sensitivityByEntry`、`idempotencyKey`；所有给 Agent 的示例 prompt 必须遵循仓库 XML 外层与动态内容转义要求。  
类型：manually invoked VO Skill / conversational onboarding contract。  
当前定义/读写：`skills/catalog.md` 列出当前 VO skills；`app/agent-guide.js:10-35` 从 catalog 发现并分类；`skills/vo-operating-guidelines/SKILL.md:90-220` 路由专用 skill；`tests/check_agent_guide_static.mjs` 对 catalog、分类与文件存在性做静态一致性检查。  
目标变化：仅在 owner 明确调用 Skill 时开始；先读取已有 profile 范围，逐题补充但允许跳过/停止；再次调用时支持继续或 append；写入前展示 creates/updates/sensitivity/skips 的精确摘要，修正后重新确认，取消则零写入。确认后调用 MP-PA-03 的专用幂等 batch capability。敏感 classification 只改变 entry policy，不创建 HUMAN DECISIONS 或 standing grant。  
上游：owner 手动调用 Skill。  
下游：MP-PA-03 owner-confirmed Skill write、MP-PA-01 profile。  
测试锚点：`tests/test_personal_asset_skill.py` 验证 frontmatter 触发条件、手动调用措辞、问题可跳过/停止/恢复、确认门禁、API/header/idempotency、敏感不授权、XML prompt 约束；扩展 Agent Guide 静态测试保证可发现。  
排除方案：不创建 setup wizard、页面聊天框、自动弹出或首次访问引导；不把 Skill 草稿作为第二份持久化 profile。  
未决假设：Skill 的跨会话“继续”由每次调用先读取权威 profile 并询问缺失/待追加内容实现，不单独持久化未确认草稿；用户停止前已明确确认的批次可保存，未确认内容丢弃。

## 跨修改点风险与设计前约束

1. **HUMAN DECISIONS 语义必须 fail closed**：resolved 不等于 approved。只有结构化 B/C、Agent/task/scope/expiry 全部匹配才可披露；A、D、自由文本、缺失、冲突和超时默认都不披露。超时 recommendation 必须是 A。
2. **不建立第二授权状态**：个人资产只持久化 linkage 和 disclosure usage；决策状态、resolution、提醒、历史与 UI 永远来自现有 HUMAN DECISIONS。
3. **Skill 确认的可信度**：当前系统只能验证 active local Agent，不能密码学验证聊天里的 owner confirmation。本版本必须明确 trusted-Agent + single-owner 边界，接口保留 confirmation digest 与 task context，不能伪装成强身份签名。
4. **敏感日志最小化**：HTTP 错误、decision situation/reason、usage、suggestion activity 均不得复制敏感 value。决策 UI 只展示 entry label/category/scope 与用途，不展示被请求的真实值。
5. **UI 范围冻结**：正式个人资产 UI 只有 overview、editor、suggestions；此前“敏感授权页”和“Skill 引导建档页”从后续 design/tasks 中删除。敏感授权只在 HUMAN DECISIONS，建档只在 Skill。

## 建议确认结果

- 接受 MP-PA-01 至 MP-PA-06 作为后续 `design.md` 和 `tasks.md` 的唯一实现边界。
- 接受敏感读取的 fail-closed 映射：A 拒绝且为超时推荐，B 仅一次，C 当前任务，D/自由文本不直接授权。
- 接受当前版本的 single-owner + trusted-active-local-Agent 部署约束；强签名 owner receipt 作为未来独立能力，不在本次隐式扩张。
- 确认后才进入 design；本文件不代表已授权实现代码。
