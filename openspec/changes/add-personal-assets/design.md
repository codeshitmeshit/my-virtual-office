## Context

Virtual Office 目前没有 owner 个人资料权威。Agent profile 存储的是 Agent 自身资料，HUMAN DECISIONS 存储的是人工决策，二者都不能承载职业、兴趣、聊天偏好、资金关注、VO 方向和办公室目标等 owner 信息。

本设计只基于已确认的 MP-PA-01 至 MP-PA-06。实现遵循“最小语义修改”：新增个人资产领域文件，在现有入口只做薄接线；不重构、不迁移、不改变 Human Decisions、HR、Dashboard、项目执行和既有 Skill 的语义。

当前部署边界是 single owner。浏览器 owner 写操作继续使用已有 management token；Agent 调用只接受无 Origin 的 loopback 请求，并要求 HR repository 中已注册且 active 的 Agent。该信任模型不等价于密码学 owner 签名。

### 已证实的现状

- MP-PA-01：`app/services/agent_profile_store.py:170-384` 已提供乐观 revision 与 0600 原子 JSON 写入范式，但它的权威对象是 Agent profile。
- MP-PA-03：`app/services/human_decisions.py:84-286,639+` 和 `app/services/human_decision_workflow.py:43-165` 已提供唯一 HUMAN DECISIONS 生命周期、A-D 选项、超时推荐和 continuation。
- MP-PA-04：`app/services/hr_http.py` 与 `app/server.py:29345-29557,29779-29781,32490-32492` 是当前生效的模块化 HTTP 接线范式；`server_routes.dispatch` 未接线。
- MP-PA-05：`app/index.html:363-385,941-968,1249-1263` 与独立的 `archive-room.js/css`、`human-resources.js/css` 是现有 toolbar + modal 集成方式。
- MP-PA-06：`skills/catalog.md`、`app/agent-guide.js:10-35` 与 `skills/vo-operating-guidelines/SKILL.md` 共同构成 VO Skill 的发现和路由链路。

## Goals / Non-Goals

**Goals:**

- 建立一份可扩展、可持久化、支持并发冲突保护的 owner 个人资产权威。
- 提供 owner 的概览、创建/编辑、删除和待确认建议管理能力。
- 允许 active local Agent 按明确任务和 entry scope 请求最少必要上下文。
- 对敏感读取复用既有 HUMAN DECISIONS，并以 fail-closed 规则解释结果。
- 提供仅由 owner 手动调用的建档 Skill，在明确确认后幂等写入权威 profile。
- 保持 UI 与现有 VO toolbar、modal、色彩、字号、边框和响应式习惯一致。

**Non-Goals:**

- 不提供交易、行情、收益分析或外部账户同步。
- 不把完整 profile 注入默认 Agent prompt，也不修改 provider prompt 装配链。
- 不新增个人资产授权页面、授权状态机、决策历史或 HUMAN DECISIONS 路由。
- 不提供页面内 onboarding wizard、聊天框、首次打开自动引导或未确认草稿持久化。
- 不重构 Human Decisions 的认证、存储、Dashboard 投影、Feishu 投递或 continuation。
- 不重构 HR authenticator 为通用框架；个人资产只实现同等级、领域内聚的最小认证边界。
- 不新增多 owner 身份体系或密码学 confirmation receipt。

## Decisions

### D1（MP-PA-01）：独立 revisioned JSON 是唯一个人资产权威

新增 `app/services/personal_asset_store.py`，使用 `STATUS_DIR/personal-assets.json`。根数据固定为：

```text
schemaVersion: 1
revision: integer
entries: {entryId -> entry}
suggestions: {suggestionId -> suggestion}
accessLinks: {requestId -> decision linkage}
usageRecords: [sanitized usage]
idempotency: {operation key -> stable result reference}
```

`entries` 的稳定字段是 `id/category/label/value/sensitivity/revision/createdAt/updatedAt`。内置 category 只用于 UI 排序和默认标签，不限制 owner 新增自定义 category。`value` 只接受有大小和深度边界的 JSON value；首版 UI 编辑文本或简单列表，但存储不把未来扩展锁死在单字符串字段上。

所有 mutation 在单一 store lock 内执行：读取 root、验证 root revision 或 entry revision、局部修改、增加 root revision、写临时文件、`fsync`、权限设为 0600、原子替换。失败不发布部分状态。

`accessLinks` 只保存 `decisionId`、请求 Agent、task context、entry scope、expiry 与一次性消费标记。它不保存 decision status、resolution、选项文字或历史。`usageRecords` 只保存 scope 和 outcome，不复制 `value`。

**理由：** owner profile 与 Agent profile/Human Decisions 的生命周期和安全边界不同。独立文件避免交叉迁移，并能复用仓库已验证的 revision + atomic write 习惯。

**替代方案：**

- 写入 `office-config.json`：拒绝，因为会把 owner 敏感数据混入广泛读取的办公室配置。
- 扩展 `AgentProfileStore`：拒绝，因为会把 owner 与 Agent 身份语义合并。
- 拆成 profile/audit/suggestion 三个文件：首版拒绝；跨文件事务会扩大恢复与一致性语义。一个聚焦 store 内部保持清晰分区即可。

### D2（MP-PA-02）：一个 transport-free service 承担 owner mutation

新增 `app/services/personal_asset_service.py`，集中提供 snapshot、entry CRUD、suggestion 终态转换和 confirmed batch。

- 浏览器 CRUD 传 `expectedRevision`，冲突返回稳定 `personal_asset_revision_conflict`，不静默覆盖。
- `accept_suggestion` 在一个 store transaction 内写入 entry 并终结 suggestion；前端不串联两个请求。
- `apply_confirmed_batch` 先验证全部 create/update/delete，再一次提交；任一项目无效则零写入。
- owner snapshot 返回完整 entry value 和 pending suggestion，但移除 idempotency、accessLinks 与内部 usage 结构。

**理由：** 让 HTTP、UI 和 Skill 共用同一个 mutation 语义，`server.py` 不承担业务判断。

**替代方案：** 为 CRUD、suggestion 和 onboarding 分别建 service。首版拒绝，因为三者都只是同一 owner profile transaction 的命令，会增加重复验证和非必要接口层。

### D3（MP-PA-03）：Agent 读取是显式 task-scoped capability，不进入默认 prompt

新增 `app/services/personal_asset_agent_auth.py`、`personal_asset_agent_access.py` 和薄的 `personal_asset_agent_api.py`。

认证请求字段为 `remoteHost/origin/action/aiId`。必须满足：IP 是 loopback、没有 Origin、action 精确等于 `personal-assets`、Agent 在 HR repository 中存在且 `status == active`。认证输出只含稳定 Agent identity。

读取请求必须提供：

- 非空且有数量上限的 `entryIds`；
- 非空、有长度上限的 `purpose`；
- `taskContext.type` 为 `task|meeting|chat`，并含稳定 `id` 和 `label`；task 可额外带 `projectId`；
- 幂等 `requestId`。

请求 `entryIds` 为空、包含通配符、超过上限或 purpose 只是“全部资料”等宽泛目的时拒绝。服务只读取命中的 entries，不做 category 自动扩张。

标准 entries 可直接返回，并为这次实际披露写一条脱敏 usage record。混合标准/敏感请求不部分披露：先对完整请求返回 `decision_required`，避免 Agent 把部分结果误认为完整上下文；Agent 可自行拆成两个明确请求。

**理由：** 显式 entry scope 是能证明“最少披露”的最小契约；不触碰任何 provider prompt 或项目执行装配逻辑。

**替代方案：** 在每次 Agent prompt 注入 profile summary。拒绝，因为无法保证 task relevance，并扩大泄漏面。

### D4（MP-PA-03）：敏感读取只引用 HUMAN DECISIONS，按结构化选项 fail closed

首次敏感请求通过注入的 `HumanDecisionWorkflow.create` 创建既有决策：

- `source` 直接使用当前 `taskContext`，从而复用 task/meeting/chat continuation；
- decision situation/reason 只写 entry label/category、scope、purpose 和 requesting Agent，不写 value；
- A = 拒绝，且 recommendation 固定为 A；
- B = 仅允许一次披露；
- C = 允许当前 task context 内重复读取相同或更小 scope；
- D = 缩小范围/自定义处理，不自动授权。

个人资产存储 `requestId -> decisionId` linkage。重试或 continuation 恢复后，access service 调用 `HumanDecisionWorkflow.snapshot()` 查找 decision。只有以下条件全部成立才披露：

1. decision 已 resolved；
2. optionId 为 B 或 C；
3. requesting Agent、task context、expiry 和请求 scope 与 linkage 匹配；
4. B 尚未消费，或 C 仍在同一 task context 且请求没有扩大 scope。

A、D、自由文本、缺失 resolution、超时 recommendation、过期、scope 扩大或 identity 不匹配均返回 denied/no-context。B 的消费标记和 usage record 与披露在同一 store transaction 内写入，避免并发重复消费。C 不形成跨任务 standing grant。

**理由：** `HumanDecisionStore.process_due` 会按 recommendation 收口，明确推荐 A 才能保证超时不泄露。只保存 linkage 可满足可恢复性，同时不产生第二授权权威。

**替代方案：** 扩展 HumanDecisionStore 增加个人资产字段或 approval 类型。拒绝，因为本需求只需组合其公开 workflow，修改会扩大现有决策语义和回归面。

### D5（MP-PA-03）：Agent suggestion 与 onboarding confirmed write 使用不同操作

Agent API 对外暴露四类明确 action：

- `request-context`：只读并按 D3/D4 留痕；
- `suggest-change`：只创建 pending suggestion，永不直接修改 entries；
- `profile-outline`：只供 owner 手动调用的建档 Skill 读取 revision 和无 value 条目目录；返回 entry ID/category/sensitivity/updatedAt，standard 条目可返回 label，sensitive 条目的 label 固定脱敏；
- `apply-confirmed-onboarding`：只供 `vo-personal-assets` Skill 在 owner 明确确认精确摘要后提交 confirmed batch。

`apply-confirmed-onboarding` 要求 active local Agent、task context、`confirmationSummaryDigest`、精确 `confirmedChanges` 与幂等键。摘要 digest 只用于把调用和 Agent 已展示的变更集合绑定，不被描述为 owner 密码学签名。来源审计保存 Agent/task/digest，不保存整段聊天或 entry values。

首版不自动解析自然语言确认，也不让普通 suggestion action 携带 `confirmed=true` 绕过 pending 状态。

**理由：** 两个显式操作是避免“建议即写入”的最小语义隔离，同时满足 Skill 确认后持久化。

**替代方案：** 所有 Agent 写入都变成 suggestion，再要求用户去页面二次确认。拒绝，因为会破坏已确认的“Skill 对话确认后直接持久化”场景。

### D6（MP-PA-04）：新增 runtime/routes，server.py 只做薄接线

新增：

- `app/services/personal_asset_runtime.py`：组装 store、service、authenticator、agent access/API 和 routes；
- `app/services/personal_asset_http.py`：识别 management 与 Agent path，解析输入并将领域错误映射为 HTTP response。

路径前缀：

- management：`/api/personal-assets`
- Agent：`/api/agent/personal-assets`

`app/server.py` 只增加 import、lazy runtime/lock/getter、auth request 组装，以及 GET/POST/OPTIONS 委派。runtime 注入 `STATUS_DIR`、`_get_hr_application_runtime().repository`、`HUMAN_DECISION_WORKFLOW` 和 clock。management 分支继续先走 `_reject_untrusted_management_request()`；Agent 分支不读取 management token。

不把 personal-assets 加入 Dashboard SSE；UI 打开与 mutation 后使用已有 `i18n.managementFetch` 获取 snapshot。个人资产没有需要全局实时推送的已确认 scenario。

**理由：** 这是当前仓库已生效的最小模块化模式，并满足 AGENTS.md 对大型 `server.py` 的约束。

**替代方案：** 新增 `server_routes/personal_assets.py`。首版拒绝，因为统一 dispatch 尚未接线，反而需要额外改造入口。

### D7（MP-PA-05）：toolbar + modal 只呈现三种 UI 状态

新增 `app/personal-assets.js` 与 `app/personal-assets.css`，`app/index.html` 只增加 stylesheet/script、toolbar button 和 modal host。`app/locales/zh.json`、`en.json` 只增加本功能键。

前端 state 固定为：

```text
open, loading, revision, entries, suggestions,
view: overview | editor | suggestions,
selectedEntryId, editorDraft, busyAction, notice, error, returnFocus
```

打开 modal 时 toolbar button 设置现有 active class 与 `aria-current="page"`，关闭时清除并恢复焦点。入口 title/i18n 解释“查看和维护 Agent 可按需使用的个人资料”。

- overview：展示持久化 entries、category、更新时间、敏感标签和 pending suggestion 数量；
- editor：创建或编辑 label/category/value/sensitivity，保存时携带 revision；删除需要现有确认 dialog；
- suggestions：查看 proposed diff，接受、编辑后接受或拒绝。

模块不得出现第四种 onboarding/authorization view，不显示 HUMAN DECISIONS 操作，不在空状态自动发起问答。CSS 全部使用 `.personal-assets-*` 作用域，复用现有 token 和 modal 结构，不向 `style.css` 添加业务规则。

**理由：** 用户已验收产品边界；独立模块可做到最小 index 接线并避免污染大型样式文件。

**替代方案：** 单独 HTML 页面或把个人资产塞入 Agent Management。拒绝，因为顶栏同级 modal 是现有产品导航和视觉基准。

### D8（MP-PA-06）：建档只由手动 Skill 驱动，不保存未确认草稿

新增 `skills/vo-personal-assets/SKILL.md`，并最小更新 catalog、operating guidelines、Agent Guide category map 和一致性测试。分类复用现有 `workspace`，不为一个 Skill 新增导航分类和 i18n。

Skill 仅在 owner 明确调用时运行：

1. 通过 `profile-outline` 读取当前 profile 的已有/缺失范围；不使用 management token，不从该目录读取 value；
2. 逐步询问基本信息、职业与方向、兴趣、聊天偏好、目标和可选敏感项；
3. 允许跳过、修正、停止；
4. 展示 create/update/sensitivity/skips 的精确摘要；
5. owner 明确确认后计算摘要 digest，调用 `apply-confirmed-onboarding`；
6. 报告实际保存 scope。

未确认 `collectionDraft` 只存在当前对话。再次调用时通过读取权威 profile 推导继续/追加，不建立草稿 store。Skill 中若构造 Agent prompt，必须通过 `services.bridge_input_output_formatting` 的 key-value/nested mapping 输入并使用 XML 外层；动态内容放入 untrusted boundary。

**理由：** 满足手动触发和可恢复体验，同时避免第二份 profile、页面 wizard 与 prompt 注入风险。

**替代方案：** 持久化 onboarding progress。首版拒绝，因为现有 requirement 只要求以后可继续，不要求恢复未确认逐字草稿；从权威 profile 继续已经满足场景。

## Data and Control Flow

### Owner UI mutation

```text
toolbar/modal
  -> managementFetch(/api/personal-assets/...)
  -> PersonalAssetHTTPRoutes
  -> PersonalAssetService
  -> PersonalAssetStore (revision check + atomic write)
  -> owner-safe snapshot
```

### Non-sensitive Agent read

```text
active local Agent
  -> agent_post(request-context)
  -> PersonalAssetAgentAuthenticator
  -> PersonalAssetAgentAccess validates task + exact entryIds
  -> PersonalAssetStore discloses selected standard entries
     and appends one sanitized usage record
```

### Sensitive Agent read

```text
request-context
  -> access link absent
  -> HumanDecisionWorkflow.create(recommendation=A)
  -> persist requestId -> decisionId linkage
  -> return decision_required, no values

HUMAN DECISIONS resolves and resumes current task
  -> same request-context/requestId retries
  -> read authoritative decision snapshot
  -> validate B/C + Agent/task/scope/expiry
  -> atomically consume B when applicable + usage record
  -> disclose only approved entries
```

### Manual Skill onboarding

```text
owner manually invokes vo-personal-assets
  -> Skill reads current snapshot scope
  -> conversational draft (memory only)
  -> exact summary + owner confirmation
  -> apply-confirmed-onboarding with digest/idempotency
  -> PersonalAssetService.apply_confirmed_batch
  -> one atomic profile update
```

## Scenario → Modification Point → Test Mapping

| Scenario group | Design / modification points | Planned verification |
|---|---|---|
| Built-in and extensible profile persistence | D1 / MP-PA-01 | `tests/test_personal_asset_store.py` |
| Partial update, delete, invalid/conflicting write | D1-D2 / MP-PA-01, MP-PA-02 | store + service tests |
| Overview, editor, pending suggestions; no onboarding/auth page | D2, D7 / MP-PA-02, MP-PA-05 | `tests/check_personal_assets_ui.mjs` + browser acceptance |
| Owner-managed sensitivity classification | D1-D2, D7 / MP-PA-01, MP-PA-02, MP-PA-05 | store/service/UI tests |
| Task-scoped non-sensitive read and full-profile rejection | D3 / MP-PA-03 | `tests/test_personal_asset_agent_access.py` |
| Sensitive request through HUMAN DECISIONS | D4 / MP-PA-03 | access tests + existing Human Decisions regression |
| B once, C current task, A/D/timeout deny | D4 / MP-PA-03 | concurrency, retry, timeout and scope tests |
| Sanitized usage records | D1, D3-D4 / MP-PA-01, MP-PA-03 | store/access serialized-output assertions |
| Active local Agent and HTTP boundaries | D3, D6 / MP-PA-03, MP-PA-04 | auth/http/server-wiring tests |
| Manual Skill, skip/stop/continue/append | D8 / MP-PA-06 | `tests/test_personal_asset_skill.py` |
| Confirm/correct/cancel before persistence | D5, D8 / MP-PA-03, MP-PA-06 | agent API + Skill contract tests |

## Minimal Change Boundary

### Files intentionally modified

- New focused domain/runtime/UI/Skill files named in MP-PA-01 through MP-PA-06.
- Thin wiring only in `app/server.py` and `app/index.html`.
- Additive keys only in `app/locales/zh.json`, `app/locales/en.json`.
- Additive discovery entries only in `skills/catalog.md`, `skills/vo-operating-guidelines/SKILL.md`, `app/agent-guide.js`.
- Focused new tests and minimal expansion of Agent Guide static checks.

### Files and semantics intentionally unchanged

- `app/services/human_decisions.py` and `human_decision_workflow.py`.
- HUMAN DECISIONS management/Agent routes, Dashboard projection, UI and Feishu cards.
- `app/services/hr_agent_auth.py` and HR API semantics.
- Agent provider prompt assembly and project/meeting/chat execution payloads.
- `office-config.json`, Agent profiles, Archive Room and Agent Management.
- Global `app/style.css` business selectors.

## Failure Semantics and Observability

- Validation and conflict errors use stable `personal_asset_*` codes and never echo values.
- Store read/write corruption returns unavailable/invalid errors; no fallback to an empty profile after an existing file is invalid.
- Sensitive request failure is fail closed. Human Decisions or HR repository unavailable returns no context and a retryable/unavailable code.
- Usage records are written exactly once per successful disclosure using request idempotency; denied requests never become successful usage.
- Core domain branches receive concise Chinese comments explaining atomicity, fail-closed approval and no-second-authority constraints.
- Reuse the repository's existing server logging/exception boundary. New logs, if needed at runtime composition or unexpected failure, include requestId/Agent ID/entry count/outcome code only; never include labels when sensitive, values, request bodies, tokens or decision free text. Expected deny/conflict paths return structured errors without error-level log storms.

## Risks / Trade-offs

- **[Trusted Agent can falsely assert conversational confirmation]** → Keep `apply-confirmed-onboarding` separate, require active loopback Agent + exact change digest + task context + idempotency, audit metadata, and explicitly document that this is not a signature. Strong owner receipts require a future identity capability.
- **[Human Decisions timeout could approve accidentally]** → Recommendation is always A/deny; only B/C option IDs are machine approvals; all other terminal shapes fail closed.
- **[Concurrent B reads disclose twice]** → Consume B and append usage in the same locked store transaction before returning the value.
- **[One JSON file grows through audit records]** → Bound usage retention by a documented maximum and prune oldest sanitized records during mutation; do not add a background job in this change.
- **[Mixed sensitive and standard request delays standard context]** → Return no partial data and require explicit split requests. This is safer and keeps response semantics unambiguous.
- **[Single-owner assumption limits future multi-user support]** → Keep owner identity out of misleading API fields; document deployment boundary. A later multi-user change must add real authenticated owner IDs and migration.
- **[UI visually drifts from production VO]** → Reuse current toolbar/modal/token patterns and perform browser comparison against the current local UI, not only the older Figma prototype.

## Migration Plan

1. Add store/service/auth/access/API/runtime/HTTP modules and focused tests without wiring routes.
2. Add thin server wiring and verify management/Agent route contracts plus existing Human Decisions/HR regressions.
3. Add toolbar/modal UI and i18n; verify only the three allowed views and current VO styling.
4. Add Skill and discovery-chain updates; verify manual triggering and confirmed batch contract.
5. Restart VO once to construct the lazy runtime. With no file present, snapshot is an empty profile; the first mutation creates `personal-assets.json` atomically.

No legacy data migration is required because no prior personal asset authority exists.

**Rollback:** remove route/UI/Skill discovery wiring and the new modules. Preserve `STATUS_DIR/personal-assets.json` as recoverable user data unless the owner explicitly requests deletion. Older code ignores this file, so rollback does not require destructive migration.

## Open Questions

None for this scope. Multi-owner authentication and signed owner confirmation receipts are explicitly future changes, not unresolved implementation choices.
