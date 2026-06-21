# Archive Room Phase 7 Checklist

确认状态：已确认

## Pending Confirmation Scope

### CHK-001: Long-Lived Rules Enter Pending Queue

- 关联需求点：待确认队列收录长期规则。
- 验证方法：产生或构造一条长期业务规则、流程规则、质量标准或项目约定建议。
- 预期结果：该建议进入项目待确认队列，带有 proposed content、confidence、impact、reason、sources 和 created time。

### CHK-002: High-Impact Suggestions Enter Pending Queue

- 关联需求点：待确认队列收录高影响建议。
- 验证方法：产生或构造一条会影响项目状态、风险判断、任务结论或后续执行方向的建议。
- 预期结果：该建议进入待确认队列，并标记合理的 impact area 和优先级。

### CHK-003: Conflicts With Confirmed Content Enter Pending Queue

- 关联需求点：所有与 confirmed 内容冲突的项都进入治理闭环。
- 验证方法：先确认一条规则，再产生一条与它冲突的新建议。
- 预期结果：尤其是 human_confirmed 内容不被覆盖；新建议以 conflict/pending 形式进入待确认队列。

### CHK-004: Ordinary AI Inferences Do Not Flood Queue

- 关联需求点：Phase 7 不确认所有 AI 推断。
- 验证方法：产生普通摘要、低影响补充、普通上下文推断。
- 预期结果：普通低影响推断不会自动进入主待确认队列；可作为普通 archive entry、archive-manager-confirmed 摘要或低优先补充存在，并带清晰 authority。

## Pending Detail UI

### CHK-005: Dedicated Pending Section In Project Detail

- 关联需求点：项目详情页必须有专门的 pending confirmation 区域。
- 验证方法：打开有待确认项的项目档案详情页。
- 预期结果：详情页有明确的待确认/治理区域；不只是项目卡片 pending 数量。

### CHK-006: Pending Item Shows Required Fields

- 关联需求点：待确认项需要展示足够判断信息。
- 验证方法：查看任一 pending item 卡片或详情。
- 预期结果：显示建议内容、置信度、影响范围、生成原因、来源引用、创建时间和当前状态。

### CHK-007: Source References Are Usable

- 关联需求点：待确认项必须可追溯。
- 验证方法：查看来自任务、会议、聊天或产物的 pending item。
- 预期结果：来源信息可读，能区分任务/会议/聊天/产物等来源；来源缺失时明确显示不可用。

### CHK-008: Conflict Item Is Summary-First

- 关联需求点：冲突项详情先解释冲突是什么。
- 验证方法：打开一个 conflict pending item。
- 预期结果：先显示一句人能读懂的冲突摘要，再允许查看 confirmed 内容、新建议和双方来源。

### CHK-009: Pending Queue Default Ordering

- 关联需求点：排序为严重冲突 > 高影响建议 > 长期规则 > 普通待确认 > 已暂缓。
- 验证方法：准备多种状态/影响级别的待确认项并打开项目详情。
- 预期结果：列表顺序符合治理优先级，已暂缓项排后或默认折叠。

## User Actions

### CHK-010: Confirm Pending Item

- 关联需求点：用户可以确认待确认项。
- 验证方法：对一个 pending item 点击确认。
- 预期结果：该项从主待确认队列移出，生成 confirmed archive entry 或 confirmed rule，并保存确认记录。

### CHK-011: Reject Pending Item

- 关联需求点：用户可以拒绝待确认项。
- 验证方法：对一个 pending item 点击拒绝。
- 预期结果：该项从主待确认队列移出或转为 rejected processed history；不会作为 active truth 出现在 AI 上下文中。

### CHK-012: Defer Pending Item

- 关联需求点：用户可以暂缓待确认项。
- 验证方法：对一个 pending item 点击暂缓。
- 预期结果：该项状态变为 deferred，仍可见但排后或默认折叠；不会被误认为 confirmed。

### CHK-013: Edit Then Confirm

- 关联需求点：用户可编辑后确认。
- 验证方法：修改一条 pending item 的建议内容后确认。
- 预期结果：用户编辑后的内容成为 confirmed 内容；原始 AI 建议作为来源/历史保留。

### CHK-014: Optional Reason Field

- 关联需求点：操作理由可选，不强制。
- 验证方法：分别在不填写理由和填写理由时执行确认/拒绝/暂缓。
- 预期结果：不填写理由也能完成操作；填写理由时记录在 action history 中。

### CHK-015: Action Retry Does Not Corrupt State

- 关联需求点：治理动作应能应对重复点击或请求重试。
- 验证方法：快速重复执行同一个确认/拒绝/暂缓动作，或刷新后重试。
- 预期结果：不会产生重复 confirmed entry 或损坏 pending record；UI 显示最终一致状态。

## Confirmed Protection And AI Context

### CHK-016: Human-Confirmed Content Is Strongly Protected

- 关联需求点：AI 不能自动覆盖 human_confirmed 内容。
- 验证方法：确认一条规则后，触发档案管理员产生冲突建议。
- 预期结果：human_confirmed 内容保持不变；冲突建议进入 pending/conflict，而不是自动覆盖。

### CHK-017: Human-Confirmed Content Appears In Context Directory

- 关联需求点：确认后的内容进入上下文目录/关键规则区。
- 验证方法：确认一条长期规则后查看项目档案上下文目录。
- 预期结果：确认内容作为 human_confirmed fact/rule 展示，并带确认记录或确认状态。

### CHK-018: Pending And Deferred Content Are Lower Trust In AI Context

- 关联需求点：AI 上下文不能把 pending/deferred 当作确认事实。
- 验证方法：请求项目 context package 或 AI 入场包。
- 预期结果：pending/deferred 内容如出现，明确标注未确认或暂缓，不作为 confirmed guidance。

### CHK-019: Rejected Content Is Not Active Guidance

- 关联需求点：拒绝项不能继续作为事实使用。
- 验证方法：拒绝一个 pending item 后请求 AI 上下文。
- 预期结果：被拒绝内容不作为 active truth 或 confirmed rule 出现；如展示历史，必须明确是 rejected。

## Processed History

### CHK-020: Lightweight Processed History Exists

- 关联需求点：详情页可查看已确认/已拒绝/已暂缓历史。
- 验证方法：处理多条 pending item 后打开项目详情历史入口。
- 预期结果：能查看 processed history，包含状态、操作者、时间、可选理由和来源摘要。

### CHK-021: Processed History Does Not Dominate Main UI

- 关联需求点：已处理历史是轻量入口，不是主区域。
- 验证方法：打开有大量 processed history 的项目详情页。
- 预期结果：主待确认区仍聚焦未处理/暂缓项；历史入口可查看但不淹没主要内容。

## Overview Discovery

### CHK-022: Overview Prioritizes Pending And Risk

- 关联需求点：总览页默认 pending/risk 优先。
- 验证方法：准备多个项目，其中部分有 pending 或 risk。
- 预期结果：有 pending/risk 的项目优先显示；同等优先级下再考虑最近更新。

### CHK-023: Filter Projects With Pending Confirmations

- 关联需求点：总览页支持只看有待确认项目。
- 验证方法：启用 pending filter。
- 预期结果：列表只显示待确认数量大于 0 或存在 deferred pending 的项目。

### CHK-024: Filter Projects With Risks

- 关联需求点：总览页支持只看有风险项目。
- 验证方法：启用 risk filter。
- 预期结果：列表只显示存在风险、冲突、阻塞或风险计数大于 0 的项目。

### CHK-025: Recent Update Sorting

- 关联需求点：总览页支持最近更新排序。
- 验证方法：切换到最近更新排序。
- 预期结果：项目按 archive/project update time 排序；不破坏 pending/risk 默认排序能力。

## Stale And Conflict Visibility

### CHK-026: Stale Entries Are Clearly Marked

- 关联需求点：过期上下文应保留但标记过期。
- 验证方法：准备 stale archive entry。
- 预期结果：UI 和 AI context 都能区分 stale 内容，不能将其当作最新事实。

### CHK-027: Conflict Entries Show Both Sides

- 关联需求点：冲突项要能帮助人判断。
- 验证方法：打开 conflict pending item 详情。
- 预期结果：能查看 confirmed side、新建议 side、冲突原因/摘要和双方来源。

## Regression And Degraded Mode

### CHK-028: Archive Index Remains Visible

- 关联需求点：Phase 7 不破坏 Phase 6 档案索引。
- 验证方法：打开项目详情页。
- 预期结果：档案索引仍展示当前任务、关键决策、风险/冲突、待确认、关键产物、重要消息/会议。

### CHK-029: Artifact Browsing Still Works

- 关联需求点：Phase 7 不破坏 Phase 1-3 产物能力。
- 验证方法：打开项目产物弹窗并预览文档、图片、视频、音频。
- 预期结果：产物列表、来源/路径视图和预览继续可用。

### CHK-030: Archive Manager Maintenance Still Works

- 关联需求点：Phase 7 不破坏 Phase 4-5 管理员和维护。
- 验证方法：查看管理员状态，触发手动整理或维护事件。
- 预期结果：管理员状态、暂停/恢复、维护记录和事件整理继续可用。

### CHK-031: AI Onboarding And Context Still Work

- 关联需求点：Phase 7 不破坏 Phase 6 AI 上下文能力。
- 验证方法：请求 AI 入场包和 project context API。
- 预期结果：返回结构正常，并正确体现 confirmed/pending/deferred/rejected 状态。

### CHK-032: Missing Archive Manager Degrades Gracefully

- 关联需求点：档案管理员不可用时档案室仍可查看。
- 验证方法：模拟 archive manager 不可用。
- 预期结果：已存在 pending/confirmed/history 仍可查看；需要管理员参与的新整理显示降级或错误，不导致主应用不可用。

## Data Durability And Observability

### CHK-033: Governance State Survives Restart

- 关联需求点：确认、拒绝、暂缓和历史记录必须持久化。
- 验证方法：执行多种治理动作后重启 VO。
- 预期结果：pending 状态、confirmed 内容、rejected/deferred 历史和确认记录全部保留。

### CHK-034: Governance Activity Is Observable

- 关联需求点：用户能理解治理动作发生过。
- 验证方法：执行确认/拒绝/暂缓/编辑确认。
- 预期结果：项目维护记录或治理历史中可看到动作摘要、时间、操作者和结果。

## Confirmation Authority And Auto-Confirmation

### CHK-035: Objective Source Facts Are Auto-Confirmed

- 关联需求点：客观事实可以由系统或来源直接确认，不需要进入人工队列。
- 验证方法：构造任务完成、产物生成、会议结束、项目状态变化或产物路径/来源映射等客观事件。
- 预期结果：对应档案内容以 `system_confirmed` 或 `source_confirmed` authority 入档；不会进入主待人工确认队列；保留可追溯来源。

### CHK-036: Archive Manager Can Confirm Low-Risk Source-Backed Summaries

- 关联需求点：档案管理员可以确认低风险、来源充分的摘要或分类。
- 验证方法：让档案管理员整理会议摘要、任务结果摘要、重要消息分类或产物描述。
- 预期结果：低风险整理结果只有经过档案管理员判断后才以 `archive_manager_confirmed` authority 入档；展示来源、置信度、整理时间和判断者；不被标成 human_confirmed。

### CHK-037: Human Queue Excludes Auto-Confirmable Items

- 关联需求点：人工待确认队列只处理长期规则、高影响建议和冲突治理。
- 验证方法：同一项目中同时准备客观事实、低风险摘要、长期规则、高影响建议和冲突建议。
- 预期结果：客观事实和低风险摘要不出现在主人工待确认队列；长期规则、高影响建议和冲突建议进入 pending_human_confirmation。

### CHK-038: Authority Labels Are Visible In UI And API

- 关联需求点：用户、前端和 AI 都能区分不同确认权限。
- 验证方法：查看项目详情、档案索引、上下文目录和 project context API。
- 预期结果：`system_confirmed` / `source_confirmed`、`archive_manager_confirmed`、`human_confirmed`、`pending_human_confirmation`、`deferred`、`rejected` 均有可识别字段或标签。

### CHK-039: AI Context Respects Confirmation Authority

- 关联需求点：AI 使用档案上下文时应按权限层级处理可信度。
- 验证方法：请求 AI 入场包或 project context API，并包含多种 authority/status 的内容。
- 预期结果：human_confirmed 被作为最高可信指导；source/system-confirmed 被作为可信客观状态；archive_manager_confirmed 被作为来源支持的上下文；pending/deferred 明确低可信或未确认；rejected 不作为 active guidance。

### CHK-040: Ordinary Business AI Cannot Self-Confirm Processed Content

- 关联需求点：AI 处理内容是否可确认由档案室管理员判断。
- 验证方法：让普通业务 AI 产出摘要、分类或建议，并尝试直接写入 confirmed authority。
- 预期结果：普通业务 AI 只能提交来源和建议；不能直接写入 `archive_manager_confirmed` 或 `human_confirmed`；需要档案管理员判断后才能成为 archive_manager_confirmed，或进入 pending_human_confirmation。

## Confirmation Record

- 确认项：Archive Room Phase 7 checklist
- 确认时间：2026-06-20T22:05:59+08:00
- 用户确认摘要：pass

## Implementation Test Record

- 测试时间：2026-06-20T23:29:00+08:00
- 自动化测试：
  - `python3 -m py_compile app/server.py tests/test_archive_room_phase_7.py`
  - `.venv/bin/python tests/test_archive_room_phase_7.py`
  - `.venv/bin/python tests/test_archive_room_phase_1_3.py`
  - `.venv/bin/python tests/test_archive_room_phase_4.py`
  - `.venv/bin/python tests/test_archive_room_phase_5.py`
  - `.venv/bin/python tests/test_archive_room_phase_6.py`
  - `node --check app/archive-room.js`
- 真实数据验收：
  - 使用 `tests/seed_archive_room_phase7_fixture.py` 创建真实验收项目 `Archive Room Phase 7 Governance Acceptance`。
  - 项目包含 source/system 确认、archive_manager_confirmed、human_confirmed、pending_human_confirmation、冲突待确认、处理历史和产物。
- Chrome MCP 验收：
  - 使用沙箱外 `chrome-devtools-mcp --browserUrl http://127.0.0.1:9224` 连接 VO 共享浏览器。
  - MCP 验收结果：`hasGovernanceText=true`、`hasAuthorityLegend=true`、`hasConflict=true`、`hasActions=true`、`hasArtifactModal=true`、`contextLegend=true`。
  - 截图：`/tmp/archive-room-phase7-mcp-isolated-2.png`。
- 覆盖说明：CHK-001 至 CHK-040 均已通过后端自动化测试、真实数据 API 验证或 Chrome MCP UI 验证覆盖。

## Final Acceptance Record

- 确认项：Archive Room Phase 7 final acceptance
- 确认时间：2026-06-21T02:14:28+08:00
- 用户确认摘要：用户初步验收通过，同意归档 Phase 7。
