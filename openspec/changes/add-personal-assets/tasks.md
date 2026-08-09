<!-- cosh-dashboard-control {"mode":"continuous","sequence":1,"mode_updated_at":"2026-08-08T17:40:41+08:00"} -->

## 1. 个人资产持久化权威（D1、MP-PA-01）

- [x] 1.1 测试先行新增 `tests/test_personal_asset_store.py`，再在新文件 `app/services/personal_asset_store.py` 实现 `PersonalAssetStore`、entry/suggestion/access-link/usage 数据类型、稳定 `personal_asset_*` 错误、root/entry revision、局部 CRUD、suggestion 终态、幂等 receipt、usage 有界保留和 0600 原子写入。
  - 对应 scenarios：创建内置信息、追加未建模信息、更新单条、删除单条、非法或冲突写入、敏感分类、建议等待确认、脱敏使用记录。
  - 精确变量：`root.schemaVersion/revision/entries/suggestions/accessLinks/usageRecords/idempotency`，entry 的 `id/category/label/value/sensitivity/revision/createdAt/updatedAt`，access link 的 `decisionId/agentId/taskContext/entryIds/expiresAt/consumedAt`。
  - 复用依据：按 `AgentProfileStore.update/_atomic_write` 的 revision、临时文件、`fsync`、0600、`os.replace` 范式实现；不导入或修改 Agent profile。
  - 中文注释：放在原子 transaction、B 一次性消费预留接口、敏感值不得进入 usage/access link、损坏文件不得降级为空 profile 的分支旁。
  - 观测：领域预期错误只返回稳定 code；store 不记录 value、完整 payload 或敏感 label，不引入新 logger。
  - 不得修改：`office-config.json`、`app/services/agent_profile_store.py`、Human Decisions 文件、现有 status 文件。
  - 验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_store.py`；覆盖重启 round-trip、自定义 category、partial update/delete 隔离、stale revision、无效 JSON/value 大小深度、原子替换失败、0600、suggestion 幂等、usage 无 value、并发一次性 consume。
  - 回滚：删除新 store 与聚焦测试；不得删除已经生成的 `personal-assets.json` 用户数据。

## 2. Owner 管理与建议确认服务（D2、MP-PA-02）

- [x] 2.1 测试先行新增 `tests/test_personal_asset_service.py`，再在新文件 `app/services/personal_asset_service.py` 实现 `PersonalAssetService.snapshot/create_entry/update_entry/delete_entry/list_suggestions/accept_suggestion/reject_suggestion/apply_confirmed_batch` 和 owner-safe projection。
  - 对应 scenarios：Owner 查看、创建、编辑、删除、接受/编辑后接受/拒绝建议；Skill 明确确认后的批量保存、修正和取消。
  - 精确变量：`expectedRevision: int`、`entryPatch: Mapping[str, object]`、`confirmedChanges: Sequence[Mapping[str, object]]`、`suggestionId/idempotencyKey: str`、`source: {kind, agentId, contextId}`。
  - 复用依据：只组合 Task 1 的 store transaction；复用 `HRServiceResult`/现有 service result 的返回风格，不导入 `server.py`。
  - 中文注释：解释 batch 全有或全无、suggestion 接受与 entry 写入同事务、owner projection 隐藏 accessLinks/usage/idempotency 的原因。
  - 观测：预期 validation/conflict 不重复打印；unexpected failure 由上层统一边界记录，不在 service 输出 value。
  - 不得修改：`app/server.py`、任何 UI、Agent API、Human Decisions 与 HR 服务。
  - 验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_store.py tests/test_personal_asset_service.py`；覆盖 batch 原子性、无关 entry 保留、suggestion terminal conflict、重复请求和安全投影。
  - 回滚：删除 service 与测试，不改变 Task 1 的持久化 schema。

## 3. Active Agent 与标准信息访问（D3、D5、MP-PA-03）

- [x] 3.1 测试先行新增 `tests/test_personal_asset_agent_auth.py`、`tests/test_personal_asset_agent_api.py` 的标准访问部分，再新增 `app/services/personal_asset_agent_auth.py`、`app/services/personal_asset_agent_access.py`、`app/services/personal_asset_agent_api.py`，实现 active local Agent 认证、精确 entry scope 的非敏感读取、pending suggestion 和 confirmed-onboarding batch 操作隔离。
  - 对应 scenarios：相关非敏感上下文读取、无任务目的全量请求拒绝、Agent 使用已披露信息、Agent/工作流只提出建议、Skill 明确确认后写入。
  - 精确变量：auth 的 `remoteHost/origin/action/aiId`；读取的 `entryIds/purpose/taskContext/requestId`；onboarding 的 `confirmedChanges/confirmationSummaryDigest/idempotencyKey`。
  - 复用依据：采用 `HRAgentAuthenticator` 已验证的 loopback、Origin、registered/active repository 规则，但在新领域文件内实现 action=`personal-assets`；不重构或继承 HR authenticator，不复用较弱的 server Human Decisions header check。
  - 行为边界：空 scope、通配符、超上限、宽泛 purpose、未知/inactive Agent 拒绝；标准披露与脱敏 usage 在一个 store transaction 内幂等完成；`suggest-change` 永不直写 entries；`apply-confirmed-onboarding` 不被普通 suggestion flag 替代。
  - 中文注释：解释 exact scope、混合敏感/标准请求不部分返回、trusted-Agent confirmation digest 不是密码学签名。
  - 观测：只允许 requestId、Agent ID、entry count、operation/outcome code；禁止 value、完整 body、确认原文和敏感 label。
  - 不得修改：`app/services/hr_agent_auth.py`、HR repository schema、provider prompt、项目/会议/聊天执行模块、Human Decisions。
  - 验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_agent_auth.py tests/test_personal_asset_agent_api.py tests/test_personal_asset_store.py tests/test_personal_asset_service.py`。
  - 回滚：删除三个 Agent 聚焦模块和测试，不改变 owner API/store 数据。

## 4. 敏感读取接入 HUMAN DECISIONS（D4、MP-PA-03）

- [x] 4.1 在 `tests/test_personal_asset_agent_access.py` 先建立 Human Decision workflow fake/真实 store 契约，再最小扩展 `PersonalAssetAgentAccess.request_context`：创建安全拒绝优先的 A-D request、保存 requestId→decisionId linkage、重试时读取权威 snapshot、按 Agent/task/scope/expiry 解释 B/C，并原子消费 B 与写 usage。
  - 对应 scenarios：敏感读取需要决策、批准、拒绝或超时、成功披露审计、拒绝不形成成功使用记录。
  - 精确变量：decision payload 的 `source/title/situation/reason/options/recommendation/taskDetail/deadlineAt`；linkage 的 `requestId/decisionId/agentId/taskContext/entryIds/expiresAt/consumedAt`；resolution 的 `status/optionId/channel/resolvedAt`。
  - 复用依据：只调用现有 `HumanDecisionWorkflow.create/snapshot`；A=拒绝且 recommendation=A，B=一次，C=当前任务，D/自由文本不授权。不得修改 Human Decision store、workflow、route、Dashboard、Feishu 或 continuation。
  - 失败语义：pending、A、D、custom、timeout A、缺失 decision、过期、Agent/task 不匹配、扩大 scope、workflow unavailable 全部零披露；混合敏感/标准请求零部分披露。
  - 中文注释：紧贴 fail-closed resolution 解释、scope 子集判断、B consume+usage 同事务以及“不建立第二授权权威”。
  - 观测：预期 deny/pending 不记 error；unexpected dependency failure只记录 decisionId/requestId/outcome code，不记录 situation/reason/value。
  - 验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_agent_access.py tests/test_human_decisions.py tests/test_human_decision_workflow.py`；覆盖 A/B/C/D/custom、超时、B 并发一次、C 同任务子集、跨任务/扩 scope、敏感值零提前泄漏。
  - 回滚：回退 access service 的敏感组合和测试；既有 HUMAN DECISIONS 数据与代码保持原样。

## 5. Runtime、HTTP 与 server 薄接线（D6、MP-PA-04）

- [x] 5.1 测试先行新增 `tests/test_personal_asset_http.py`、`tests/test_personal_asset_server_wiring.py`，再新增 `app/services/personal_asset_runtime.py`、`app/services/personal_asset_http.py` 并最小修改 `app/server.py`，接通 `/api/personal-assets` 与 `/api/agent/personal-assets` 的 GET/POST/OPTIONS。
  - 对应 scenarios：全部 owner 管理、Agent 读取/建议/onboarding confirmed write 的可达性和授权边界。
  - 精确符号/变量：`PersonalAssetRuntime`、`build_personal_asset_runtime`、`PersonalAssetHTTPRoutes.handles/is_management/management_get/management_post/agent_post`、`PersonalAssetHTTPResponse`、`MANAGEMENT_PREFIX/AGENT_PREFIX`、server 的 `_personal_asset_runtime/_lock/_get_personal_asset_runtime` 与 auth request 组装。
  - 复用依据：按 `HRHTTPRoutes` 和 server 的 lazy runtime/handler 委派模式；management 继续复用 `_reject_untrusted_management_request`，runtime 注入 `STATUS_DIR`、HR repository、`HUMAN_DECISION_WORKFLOW` 与 clock。
  - 最小修改：`server.py` 只允许 import、runtime getter、auth request、GET/POST/OPTIONS delegate；禁止放入字段验证、profile mutation、decision mapping 或 JSON 持久化。
  - 中文注释：解释 Agent browser Origin 拒绝、management/Agent 路径分流和 dependency unavailable 的 fail-closed 行为。
  - 观测：复用 server 既有异常边界；稳定领域错误不重复日志，unexpected 只含 request ID/path operation/code，不含 body/value/token。
  - 不得修改：`server_routes.dispatch`、Human Decisions routes、HR routes/auth、Dashboard SSE、全局 management token 语义。
  - 验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_http.py tests/test_personal_asset_server_wiring.py tests/test_hr_agent_auth.py tests/test_hr_http_contract.py tests/test_human_decision_server_wiring.py tests/test_human_decision_http_e2e.py`。
  - 回滚：移除 server 薄接线和两个新 runtime/HTTP 文件；保留 `personal-assets.json`。

## 6. 三态个人资产 UI（D7、MP-PA-05）

- [x] 6.1 在 `tests/check_personal_assets_ui.mjs` 先写 toolbar/modal/三态/安全 DOM/i18n/响应式失败契约，再新增 `app/personal-assets.js`、`app/personal-assets.css`，并对 `app/index.html`、`app/locales/zh.json`、`app/locales/en.json` 做纯增量接线；完成桌面与窄屏浏览器验收。
  - 对应 scenarios：导航打开、持久化概览、创建/编辑/删除、待确认建议、敏感分类；不存在页面 onboarding 和敏感授权。
  - 精确变量：`state.open/loading/revision/entries/suggestions/view/selectedEntryId/editorDraft/busyAction/notice/error/returnFocus`；`view` 仅允许 `overview|editor|suggestions`；DOM 为 `#personal-assets-toggle/#personalAssetsModal/#personal-assets-content`。
  - 复用依据：现有 toolbar + modal host、`i18n.managementFetch`、`VODialogs.showConfirm`、Archive Room/Human Resources 的局部 state/escape/focus 模式和现有 CSS token。
  - 最小修改：入口放在 Archive Room 与 Human Resources 同级，增加说明 title/i18n、active class 与 `aria-current`；`index.html` 只加 button/modal/CSS/JS；CSS 全部 `.personal-assets-*` 作用域。
  - 中文注释：仅为 revision 冲突刷新、suggestion 接受事务语义和禁止页面授权/onboarding 的非显然边界添加说明；不逐行注释渲染代码。
  - 观测：前端错误只展示稳定、安全消息，不 console 输出响应 body 或 entry value。
  - 不得修改：`app/style.css` 业务规则、Agent Management、Archive Room、HUMAN DECISIONS UI、Dashboard SSE；不得出现 onboarding/authorization 第四视图。
  - 验证：`node tests/check_personal_assets_ui.mjs && node tests/check_agent_guide_static.mjs`；浏览器验证空态、内置/扩展分类、敏感 badge、CRUD、revision conflict、suggestion accept/edit/reject、焦点恢复、导航 active、桌面/窄屏且无横向溢出。
  - 回滚：移除独立 JS/CSS 和 index/locale 增量；后端与用户数据保持可用。

## 7. 手动建档 Skill 与发现链路（D8、MP-PA-06）

- [x] 7.1 测试先行新增 `tests/test_personal_asset_skill.py` 并扩展 `tests/check_agent_guide_static.mjs`，再新增 `skills/vo-personal-assets/SKILL.md`，对 `skills/catalog.md`、`skills/vo-operating-guidelines/SKILL.md`、`app/agent-guide.js` 做纯增量发现/路由更新。
  - 对应 scenarios：owner 手动调用、页面不自动引导、逐步收集、跳过、停止、再次继续/追加、确认/修正/取消、敏感分类不授予 Agent standing access。
  - 精确变量/契约：对话内 `collectionDraft/skippedTopics/confirmedChanges/sensitivityByEntry/idempotencyKey`；Agent Guide `categoryById['vo-personal-assets']='workspace'`；API actions=`profile-outline|apply-confirmed-onboarding`；outline 只返回 revision 和无 value 元数据，sensitive label 脱敏。
  - 复用依据：复用现有 catalog → Agent Guide 和 operating-guidelines 路由方式；跨会话继续通过先读权威 profile 推导，不新增 onboarding progress store。
  - Prompt 约束：任何 provider-visible prompt 必须通过 `services.bridge_input_output_formatting` 传 key-value/nested mapping，使用 XML 外层与转义后的 untrusted data boundary；Skill 示例不得用裸字符串拼接动态内容。
  - 中文注释：Skill 规则明确“手动触发”“确认前零写入”“未确认草稿不持久化”“敏感 classification 不等于授权”。
  - 观测：Skill 不输出 token、管理凭证、完整敏感值日志或确认原文；只报告保存 scope。
  - 不得修改：setup wizard、页面 UI、全局 Codex skills、Human Decisions Skill 语义、Agent Guide 新分类/i18n。
  - 验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_skill.py && node tests/check_agent_guide_static.mjs`；覆盖 frontmatter 触发、手动调用、跳过/停止/继续/追加、摘要确认循环、cancel 零写入、header/action/idempotency、敏感不授权、XML/formatter 规则。
  - 回滚：移除 skill 和三处发现增量；不删除已由 owner 确认保存的 profile。

## 8. 跨边界验证与交付门禁

- [x] 8.1 运行个人资产全部聚焦测试、Human Decisions/HR/Agent Guide 回归、OpenSpec 校验和本地浏览器 E2E；检查最终 diff 只覆盖 MP-PA-01 至 MP-PA-06，并在 `openspec/changes/add-personal-assets/verification-evidence.md` 记录命令、实际结果、浏览器证据、未覆盖项和回滚结论。
  - 对应 scenarios：三个 capability 下的全部 scenarios；验证 D1-D8 的端到端组合，不新增实现语义。
  - 精确验证：`.venv/bin/python -m pytest -q tests/test_personal_asset_store.py tests/test_personal_asset_service.py tests/test_personal_asset_agent_auth.py tests/test_personal_asset_agent_api.py tests/test_personal_asset_agent_access.py tests/test_personal_asset_http.py tests/test_personal_asset_server_wiring.py tests/test_personal_asset_skill.py tests/test_human_decisions.py tests/test_human_decision_workflow.py tests/test_hr_agent_auth.py tests/test_hr_http_contract.py tests/test_human_decision_server_wiring.py`；`node tests/check_personal_assets_ui.mjs`；`node tests/check_agent_guide_static.mjs`；`openspec validate add-personal-assets --json`。
  - 浏览器 E2E：当前 VO 真实 toolbar/modal 上验证 overview/editor/suggestions、重启持久化、标准 Agent 最小读取、敏感 request→HUMAN DECISIONS→B/C 恢复、A/超时拒绝，以及页面上没有 onboarding/authorization。
  - 安全审查：序列化文件、HTTP 响应、decision payload、usage、日志和测试 fixture 不复制敏感 value；B 并发最多披露一次；C 不跨 task；management/Origin/active Agent 边界保持。
  - 范围审查：确认未修改 Human Decisions、HR auth、provider prompt、Dashboard SSE、`office-config.json`、`app/style.css` 业务规则及其他用户工作树变更；运行范围内 whitespace/diff 检查。
  - 中文注释与观测审查：核心原子性/fail-closed/无第二权威分支都有原因注释；错误只在责任边界记录一次且字段脱敏。
  - 回滚：按 D1-D8 反向移除接线和新模块；保留 `personal-assets.json` 为可恢复 owner 数据。本任务不得自动删除数据、暂存文件、提交或归档。
