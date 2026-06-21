# Archive Room Phase 8 Checklist

确认状态：已确认

## Schedule Configuration

### CHK-001: Project Frequency Is Visible

- 关联需求点：项目详情应显示当前整理频率。
- 验证方法：打开 Archive Room 中一个开启长期维护的项目详情。
- 预期结果：长期维护区域显示当前频率，默认是事件触发 + 每日巡检。

### CHK-002: Frequency Adjustment Entry

- 关联需求点：频率配置应显示为当前频率 + 调整按钮，不干扰主要档案阅读。
- 验证方法：查看项目详情长期维护区域，并点击调整入口。
- 预期结果：默认只显示当前频率和调整入口；点击后可选择事件触发、每日、每周，以及可选自定义间隔。

### CHK-003: Frequency Persistence

- 关联需求点：频率配置必须持久化。
- 验证方法：修改项目频率后刷新页面并重启 VO。
- 预期结果：项目仍显示修改后的频率；不会回退到默认值。

### CHK-004: Disabled Maintenance Greys Frequency

- 关联需求点：关闭长期维护时频率配置灰置保留。
- 验证方法：关闭项目长期维护后查看长期维护区域。
- 预期结果：频率配置不可操作或明显灰置，但仍显示原配置；重新开启长期维护后继续使用该配置。

### CHK-005: Next And Last Scheduled Times

- 关联需求点：用户应看到下一次计划整理、上次计划整理。
- 验证方法：设置每日或每周频率并触发/模拟计划整理。
- 预期结果：项目详情显示 next scheduled整理 和 last scheduled整理，时间含义清楚。

### CHK-006: Last Event-Triggered Time

- 关联需求点：事件触发整理和计划整理应分开显示。
- 验证方法：触发一次任务完成、重要消息或会议结论整理。
- 预期结果：last event-triggered整理 更新时间变化；last scheduled整理 不被误更新。

## Scheduled Maintenance Behavior

### CHK-007: Daily Schedule Runs

- 关联需求点：默认事件触发 + 每日巡检。
- 验证方法：对默认频率项目触发每日巡检条件。
- 预期结果：产生 scheduled/daily 类型的整理记录，并更新项目档案。

### CHK-008: Weekly Schedule Runs

- 关联需求点：支持每周计划整理。
- 验证方法：将项目频率设置为每周并触发/模拟每周巡检。
- 预期结果：只有满足每周条件时才产生 scheduled/weekly 整理记录。

### CHK-009: Event-Only Skips Scheduled Runs

- 关联需求点：支持仅事件触发。
- 验证方法：将项目频率设置为仅事件触发并触发计划巡检。
- 预期结果：不会执行计划整理；维护记录显示按配置跳过或不产生计划整理噪音。

### CHK-010: Event Triggers Still Work Under Any Frequency

- 关联需求点：计划频率不能阻塞事件触发整理。
- 验证方法：分别在事件触发、每日、每周配置下触发重要事件。
- 预期结果：重要事件均可触发整理，并记录为 event-triggered。

### CHK-011: Paused Manager Skips Scheduled Runs

- 关联需求点：档案管理员暂停时计划整理不执行并记录原因。
- 验证方法：暂停档案管理员后触发计划巡检。
- 预期结果：项目不执行计划整理；维护记录包含 paused skip reason。

### CHK-012: Disabled Project Maintenance Skips Scheduled Runs

- 关联需求点：项目长期维护关闭时计划整理不执行并记录原因。
- 验证方法：关闭项目长期维护后触发计划巡检。
- 预期结果：项目不执行计划整理；维护记录包含 project maintenance disabled skip reason。

### CHK-013: Duplicate Runs Are Prevented

- 关联需求点：启动、计划和事件触发靠近时不能重复刷整理。
- 验证方法：在短时间内触发启动巡检、计划巡检和同类事件整理。
- 预期结果：重复整理被合并、跳过或冷却；维护记录解释去重/跳过原因。

## Archive-Manager-First Governance

### CHK-014: Low-Risk Source-Backed Content Auto-Confirms

- 关联需求点：低风险来源明确内容应由档案管理员自动确认。
- 验证方法：制造来源明确的任务结果摘要、产物描述或重要消息分类。
- 预期结果：内容以 archive_manager_confirmed 或合适 authority 入档，不进入人工确认队列。

### CHK-015: Wording Drift Auto-Merges

- 关联需求点：普通表述差异不应打扰人工。
- 验证方法：制造两条语义一致但表述不同的非人工确认档案内容。
- 预期结果：档案管理员自动合并或保留更清晰版本；旧内容标记 stale/merged，不进入人工确认队列。

### CHK-016: Stronger New Source Replaces Non-Human Content

- 关联需求点：新来源更强时可替换非人工确认内容。
- 验证方法：先生成 archive_manager_confirmed 内容，再生成更晚、更强来源的新内容。
- 预期结果：新内容成为当前有效内容；旧内容被标记 stale；治理历史保留替换关系。

### CHK-017: Objective Facts Can Become Stale

- 关联需求点：source/system confirmed 事实可以因新事实变旧。
- 验证方法：制造项目状态、任务状态或产物状态变化。
- 预期结果：旧 source/system confirmed 事实被标记 stale；新事实作为当前客观状态；不会误进入人工确认。

### CHK-018: Human-Confirmed Rules Are Not Auto-Replaced

- 关联需求点：人工确认规则不可自动覆盖。
- 验证方法：先创建 human_confirmed 规则，再制造相反的新建议。
- 预期结果：旧 human_confirmed 规则保持有效；新建议进入人工确认队列，说明不能自动处理的原因。

### CHK-019: High-Trust Source Conflict Escalates

- 关联需求点：两个高可信来源互相冲突时需要人兜底。
- 验证方法：制造两个互相冲突且都高可信的来源。
- 预期结果：内容进入人工确认队列；条目说明双方来源和需要人做出的选择。

### CHK-020: Owner Decision Escalates

- 关联需求点：高影响 owner 业务决策仍需人工。
- 验证方法：制造涉及业务策略、流程标准或质量标准变更的建议。
- 预期结果：建议进入人工确认队列；条目说明为什么需要 owner 判断。

## Governance Visibility

### CHK-021: Automatic Governance Notice

- 关联需求点：自动处理后应轻提示但不形成新待办。
- 验证方法：触发自动合并、自动标记过期或自动替换非人工内容。
- 预期结果：长期维护区域显示最近自动处理提示；提示不要求用户确认。

### CHK-022: Notice Shows Recent 3-5 Actions

- 关联需求点：轻提示显示最近 3-5 条。
- 验证方法：连续触发超过 5 次自动治理。
- 预期结果：UI 仅展示最近 3-5 条，完整历史仍可从维护/治理历史查看。

### CHK-023: Source Comparison Summary

- 关联需求点：自动替换或冲突应展示来源对比摘要。
- 验证方法：触发 stronger-source replacement 或 high-trust conflict。
- 预期结果：UI/API 中可看到旧来源、新来源、来源类型、时间和档案管理员判断。

### CHK-024: Stale Content Remains Inspectable

- 关联需求点：旧内容不能静默消失。
- 验证方法：让档案管理员自动标记旧内容 stale。
- 预期结果：旧内容仍可查看，带 stale 标记、替代内容引用和原因。

### CHK-025: Human Pending Item Explains Why Automation Was Insufficient

- 关联需求点：人工队列只放高价值事项，并解释需要人做什么。
- 验证方法：制造必须人工确认的冲突。
- 预期结果：pending item 包含管理员判断、无法自动处理原因、需要人选择的选项或决策点。

## AI Context And Trust

### CHK-026: Stale Content Is Not Active Guidance

- 关联需求点：AI 不应把 stale/replaced 内容当作当前指导。
- 验证方法：请求项目 AI context，项目中包含 stale 和 replacement 内容。
- 预期结果：context 中当前指导优先使用新内容；stale 内容最多作为历史或 optional reference，不作为 active guidance。

### CHK-027: Pending Human Items Are Low Trust

- 关联需求点：pending human items 不能被 AI 当作已确认事实。
- 验证方法：请求包含 pending owner decision 的项目 context。
- 预期结果：pending 内容带低可信/未确认标记，并提示需要人工确认。

### CHK-028: Automatic Governance Is Auditable In Context

- 关联需求点：自动治理必须可追溯。
- 验证方法：请求发生过自动替换的项目 context。
- 预期结果：context 保留 source references、authority、stale/replacement 关系或可继续加载的治理历史入口。

## Regression And Safety

### CHK-029: Phase 7 Manual Governance Still Works

- 关联需求点：Phase8 不替代 Phase7 人工确认能力。
- 验证方法：对必须人工确认项执行确认、编辑确认、暂缓、拒绝。
- 预期结果：原有治理动作仍可用，状态和历史正确。

### CHK-030: Artifact Browsing Is Unaffected

- 关联需求点：Phase8 不应破坏产物查看。
- 验证方法：打开含文档、图片、视频或音频的项目产物浏览。
- 预期结果：产物列表、路径/来源视图和预览能力保持可用。

### CHK-031: Archive Manager Degraded Mode

- 关联需求点：OpenClaw/档案管理员不可用时系统应降级。
- 验证方法：模拟 archive manager 不可用后打开 Archive Room。
- 预期结果：已有档案和频率配置仍可查看；自动治理和计划整理显示不可用或跳过原因，不导致主应用崩溃。

### CHK-032: Same-Event Phase7 Versus Phase8 Comparison

- 关联需求点：Phase8 应减少人工确认。
- 验证方法：用同一批事件构造低风险补充、普通表述冲突、非人工内容被强来源替代、人类规则冲突和高可信来源冲突。
- 预期结果：相比 Phase7，Phase8 中低风险和非人工冲突大多由档案管理员自动处理；人工队列只剩替换 human_confirmed、高可信无法判断和 owner 决策类事项。

### CHK-033: Main App Regression

- 关联需求点：Archive Room Phase8 不应破坏主应用其他流程。
- 验证方法：检查项目列表、任务详情、聊天、会议、Archive Room 打开关闭和项目切换。
- 预期结果：现有主应用流程仍可用。

## Confirmation Record

- 确认项：Archive Room Phase 8 checklist
- 确认时间：2026-06-21T02:30:32+08:00
- 用户确认摘要：pass

## Implementation And Test Record

- 实现时间：2026-06-21T03:10:00+08:00
- 实现摘要：已完成 Phase8 维护频率配置与档案管理员优先治理。后端支持 `event_only`、`daily`、`weekly`、`custom` 频率状态、计划巡检跳过原因、事件触发时间、长期维护开关保留配置、自动治理轻提示、来源对比、旧条目 stale/replacement 关系，以及 AI context 排除 stale 内容。前端长期维护区新增当前频率、下次/上次计划、事件触发时间、跳过原因、调整频率面板、自动治理提示、stale 标记和来源对比展示，并补齐档案室相关汉化。
- 真实数据：已创建真实验收项目 `Archive Room Phase 8 Frequency Governance Acceptance`，项目 ID `7e8fb87a-bff6-4442-9854-c761e8c97532`。项目包含周巡检配置、事件触发记录、2 条自动治理记录、1 条 stale 替代关系、1 条 owner-level 待确认冲突，以及文档/图片/视频/音频产物。
- 自动化测试：通过 `node --check app/archive-room.js`、`.venv/bin/python -m py_compile app/server.py`、`.venv/bin/python tests/test_archive_room_phase_8.py`、`.venv/bin/python tests/test_archive_room_phase_7.py`、`.venv/bin/python tests/test_archive_room_phase_6.py`、`.venv/bin/python tests/test_archive_room_phase_4.py`。
- Chrome DevTools 验收：通过 `node tests/chrome_archive_room_phase8_check.mjs` 连接共享 Chrome DevTools CDP。由于内置 `mcp__chrome_devtools` 在当前环境报缺少 X server，脚本使用同一 CDP 端口并注入真实 `archive-room.js/css`，以真实 API 数据快照验证 UI。结果确认项目可见、每周频率可见、调整频率面板可见、自动治理可见、stale 可见、来源对比可见、pending 可见、产物弹窗两栏可见、按路径视图可见、图片/视频/音频/Markdown 产物可见，截图保存到 `/tmp/archive-room-phase8-cdp.png`。
- 汉化检查：Phase8 新增区域与档案室主要按钮/状态已汉化。Chrome 扫描剩余 `Project`、`Current` 来自真实项目数据/历史档案标题，不是固定 UI 文案。

## Final Acceptance Record

- 确认项：Archive Room Phase 8 final acceptance
- 确认时间：2026-06-22T00:49:20+08:00
- 用户确认摘要：用户确认“我暂时没问题了，这个需求可以验收了”。
- 验收结论：通过。验收范围包含 Phase8 维护频率配置、计划/事件巡检展示、档案管理员优先治理、stale/source comparison/pending 展示、产物浏览、滚动位置保持、按钮对齐和档案室顶部留白调整。
