# Archive Room Phase 1-3 Checklist

确认状态：已确认

## Phase 1: Archive Data Foundation

### CHK-001: Archive storage location

- 关联需求点：Phase 1 stores durable archive records under `VO_STATUS_DIR`.
- 验证方法：启动应用后创建或 derive 一个项目档案，检查数据是否写入 `VO_STATUS_DIR` 下的稳定 archive 位置。
- 预期结果：项目档案数据不写入临时前端状态；存储位置可由 `VO_STATUS_DIR` 控制。

### CHK-002: Archive data survives restart

- 关联需求点：Archive data must survive server restart.
- 验证方法：创建或更新项目档案数据，重启 VO 服务，再打开 Archive Room 或读取对应 API。
- 预期结果：项目档案、概览字段、artifact metadata、confidence level、source references 和 stale flags 仍可读取。

### CHK-003: Initial archive derivation from projects and tasks

- 关联需求点：Phase 1 derives initial project archive data from existing project/task records where available.
- 验证方法：准备已有项目和任务数据，打开 Archive Room 或触发 archive initialization。
- 预期结果：每个已有项目至少能形成基础档案记录；可展示项目名称、基本状态、任务数量、更新时间等可得信息。

### CHK-004: Missing source data degradation

- 关联需求点：Existing records may not contain every archive field.
- 验证方法：准备缺少风险、待确认、活跃 AI 或 artifact metadata 的项目。
- 预期结果：系统显示空、0、unknown 或合理占位状态，不崩溃，不伪造不可得信息。

### CHK-005: Confidence levels

- 关联需求点：Archive entries distinguish confirmed fact, AI inference, and pending confirmation suggestion.
- 验证方法：准备三类不同 confidence level 的 archive entries 并读取或展示。
- 预期结果：每条关键档案内容能明确显示或返回其可信等级；待确认建议不会被标成已确认事实。

### CHK-006: Source references

- 关联需求点：Important archive entries should be source-backed when sources are available.
- 验证方法：为决策、风险、任务产物或上下文条目登记来源任务、会议、聊天、文件或时间戳。
- 预期结果：条目能显示或返回来源引用；来源不可用时显示明确的 source unavailable 状态。

### CHK-007: Stale context handling

- 关联需求点：Outdated context is kept but marked stale.
- 验证方法：将一条上下文标记为 stale 或 superseded。
- 预期结果：旧内容没有被静默删除；它在数据和 UI 中明确显示为过期或被替代。

### CHK-008: No raw history duplication

- 关联需求点：Archive keeps source references instead of duplicating all raw history.
- 验证方法：检查 archive record 中对聊天、会议、任务记录的保存方式。
- 预期结果：archive record 只保存必要摘要、metadata 和 source reference，不复制完整聊天或会议全文作为默认档案内容。

## Phase 2: Archive Room Main Navigation And Project Overview

### CHK-009: First-level Archive Room entry

- 关联需求点：Archive Room is a first-level main application module.
- 验证方法：启动主应用并查看主导航或一级入口区域。
- 预期结果：存在清晰的“档案室”入口；点击后进入 Archive Room 总览，而不是项目详情内部 Tab。

### CHK-009A: Minimal archive manager placeholder

- 关联需求点：Phase 1-3 keeps only minimal archive management AI status visibility.
- 验证方法：打开 Archive Room 并查看 archive manager 相关状态区域或占位文案。
- 预期结果：只显示“后续阶段启用”“未接入”或等价占位；不自动创建 AI，不提供暂停/恢复，不显示整理记录。

### CHK-010: Project overview list

- 关联需求点：Archive Room first screen is a project overview list.
- 验证方法：进入 Archive Room。
- 预期结果：默认展示项目列表或项目卡片/行；每个项目可进入详情。

### CHK-011: Overview metrics

- 关联需求点：Overview shows project status metrics.
- 验证方法：准备包含任务、风险、待确认、artifact metadata 和更新时间的项目。
- 预期结果：项目概览展示项目名称、当前状态、任务数量、完成率、风险数、待确认数、活跃 AI、最近更新时间、产物数量中的可得字段。

### CHK-012: Risk and pending confirmation priority sorting

- 关联需求点：Default ordering prioritizes risk and pending confirmation, then recent update.
- 验证方法：准备多个项目：一个有风险或待确认项，一个无风险但最近更新，一个普通项目。
- 预期结果：有风险/待确认的项目优先；同等关注级别下最近更新项目靠前。

### CHK-013: Empty state

- 关联需求点：Archive Room should not show blank screens when no data exists.
- 验证方法：在无项目或无 archive data 的环境中打开 Archive Room。
- 预期结果：显示清晰空状态，说明当前没有项目档案或可归档项目。

### CHK-014: Overview load failure state

- 关联需求点：User-visible data states should be clear.
- 验证方法：模拟 archive overview load failure 或损坏 archive metadata。
- 预期结果：Archive Room 显示可理解错误状态；主应用其余区域不受影响。

### CHK-015: Existing project flows remain available

- 关联需求点：Archive Room should not replace or break Projects module.
- 验证方法：在加入 Archive Room 后执行现有项目列表、项目详情、任务查看和任务编辑基本流程。
- 预期结果：原有项目功能仍可使用，URL/按钮/数据没有被 Archive Room 破坏。

## Phase 3: Project Archive Detail And Artifact Preview

### CHK-016: Project archive detail navigation

- 关联需求点：Humans can inspect one project's archive.
- 验证方法：从 Archive Room 项目总览点击一个项目。
- 预期结果：进入该项目档案详情页或详情面板，并可返回总览。

### CHK-017: Project context sections

- 关联需求点：Detail view shows current state, goals/summary, decisions, risks, blockers, rules, onboarding/context summary, and source references when available.
- 验证方法：准备包含这些字段的项目档案。
- 预期结果：详情页以清晰分区展示可得内容；缺失字段显示合理空状态，不显示误导性假数据。

### CHK-017A: Human-readable onboarding package

- 关联需求点：Phase 3 provides a human-readable standard onboarding package, but not automatic AI loading.
- 验证方法：打开项目档案详情中的入场包区域。
- 预期结果：用户可以查看并复制项目目标、当前状态、关键决策、风险/阻塞等入场内容；页面不承诺 AI 自动读取。

### CHK-018: Entry confidence and stale markers in detail

- 关联需求点：Important entries show confidence level and stale state.
- 验证方法：在详情页查看 confirmed fact、AI inference、pending confirmation suggestion 和 stale entries。
- 预期结果：用户能分辨可信等级和过期状态。

### CHK-019: Artifact list metadata

- 关联需求点：Task artifacts and associated files are visible.
- 验证方法：为项目登记任务完成报告、实现说明、测试结果、交付文档和关联文件。
- 预期结果：产物区显示名称、类型、来源任务或来源记录、创建/更新时间、文件大小或可得 metadata，以及打开入口。

### CHK-019A: Explicit artifact association boundary

- 关联需求点：Phase 1-3 only covers artifacts explicitly associated with projects or tasks.
- 验证方法：准备一组明确关联任务的产物，以及一组仅存在于项目工作区但未登记关联的普通文件。
- 预期结果：明确关联的产物进入档案室产物区；未关联文件不会被无差别展示为档案产物。

### CHK-020: Document preview or open behavior

- 关联需求点：Documents are readable or openable.
- 验证方法：打开 Markdown、TXT、PDF 或浏览器支持的文档产物。
- 预期结果：支持的文档可阅读或打开；不支持时提供下载/打开 fallback。

### CHK-021: Image preview

- 关联需求点：Images are previewable.
- 验证方法：打开 PNG、JPG、JPEG、GIF 或 WebP artifact。
- 预期结果：图片可在 Archive Room 中预览，并保留下载或打开入口。

### CHK-022: Video playback

- 关联需求点：Videos are playable when browser-supported.
- 验证方法：打开 MP4、WebM 或浏览器支持的视频 artifact。
- 预期结果：视频可以使用浏览器原生控件播放；不支持格式显示合理错误并提供下载/打开 fallback。

### CHK-023: Audio playback

- 关联需求点：Audio is playable when browser-supported.
- 验证方法：打开 MP3、WAV、OGG 或浏览器支持的音频 artifact。
- 预期结果：音频可以使用浏览器原生控件播放；不支持格式显示合理错误并提供下载/打开 fallback。

### CHK-024: Generic attachment fallback

- 关联需求点：Other attachments are downloadable or openable.
- 验证方法：打开压缩包、未知二进制文件或不支持预览的 artifact。
- 预期结果：系统不崩溃；提供下载或打开入口，并说明当前不能内嵌预览。

### CHK-025: Artifact access boundaries

- 关联需求点：Artifact preview must not expose arbitrary local files.
- 验证方法：尝试通过 artifact preview/open route 访问 VO 数据根之外的路径、路径穿越路径或未登记文件。
- 预期结果：请求被拒绝；只允许访问合法 archive/artifact roots 或注册 artifact metadata 中的文件。

### CHK-026: Source references from detail and artifacts

- 关联需求点：Source references should be visible for important entries and artifacts.
- 验证方法：打开详情中的关键决策、风险、规则或 artifact source link。
- 预期结果：能看到或跳转到来源记录；来源不可用时显示清楚提示。

### CHK-027: Regression for chat and meeting flows

- 关联需求点：Archive Room should not replace raw provider-native chat logs or meeting history.
- 验证方法：执行现有聊天窗口、agent chat bubbles、meeting history、workflow chat 基本流程。
- 预期结果：原有聊天和会议功能仍可使用；Archive Room 不破坏原始记录读取。

## Phase 1-3 Overall Acceptance

### CHK-028: Phase 1-3 scope boundary

- 关联需求点：Archive manager AI lifecycle and automatic整理 are outside this sub-requirement.
- 验证方法：检查本次实现和 UI 文案。
- 预期结果：Phase 1-3 不要求自动创建 archive manager AI、不要求暂停/恢复、不要求每日巡检、不要求 AI context query；如果出现占位状态，应明确为后续阶段。

### CHK-028A: AI onboarding remains soft acceptance

- 关联需求点：New AI quick onboarding is a soft acceptance signal in Phase 1-3.
- 验证方法：检查项目详情和入场包内容。
- 预期结果：详情页提供足够信息让新 AI 理论上能理解项目，但不要求验证自动 AI 接入、自动加载或 AI 查询。

### CHK-029: Human quick status check

- 关联需求点：Humans can quickly understand project status and artifacts.
- 验证方法：让用户打开 Archive Room 并查看项目总览与一个项目详情。
- 预期结果：用户无需翻聊天记录即可判断项目状态、风险/待确认数量、最近更新和主要产物。

### CHK-030: Compatibility across local and container storage

- 关联需求点：Archive data follows `VO_STATUS_DIR`.
- 验证方法：分别以本地默认 `./data` 和自定义 `VO_STATUS_DIR` 启动。
- 预期结果：archive data 在对应状态目录中创建和读取，不硬编码单一环境路径。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-19T17:52:41+08:00
- 用户确认摘要：用户要求生成 todolist；视为确认当前 Phase 1-3 checklist，并纳入后续澄清边界：Phase 1-3 仅显示最小 archive manager 占位；项目总览优先风险/待确认；入场包为人类可读可复制；产物只覆盖明确项目/任务关联来源；AI 快速接手为软验收。

## 实现与验证记录

- 实现时间：2026-06-19T18:15:45+08:00
- 实现摘要：已添加 Archive Room Phase 1-3，包括 `VO_STATUS_DIR/archive-room/projects` 持久化档案记录、`/api/archive-room` 和 `/api/archive-room/projects/<id>`、一级工具栏入口、档案室弹窗、项目关注列表、项目详情、可复制入场包、明确关联任务产物列表、文档/图片/视频/音频预览，以及安全 artifact file 路由。
- 范围边界：archive manager 只显示“后续阶段启用”占位；未实现自动创建、暂停/恢复、定时巡检、AI 自动入场或 AI context query。
- 已执行测试：
  - `.venv/bin/python tests/test_archive_room_phase_1_3.py`：通过。
  - `.venv/bin/python tests/test_project_execution.py`：通过；过程中 gateway 不可达日志为现有测试降级路径。
  - `.venv/bin/python -m py_compile app/server.py`：通过。
  - `node --check app/archive-room.js`：通过。
- Smoke 记录：临时服务曾成功返回 `/api/archive-room` JSON 和 `/archive-room.js` 静态资源；受 sandbox/local networking 状态影响，首页 curl 后续连接不稳定，未作为最终验证依据。

## 测试通过确认记录

- 确认项：tested
- 确认时间：2026-06-20T07:50:53+08:00
- 用户确认摘要：用户完成 Archive Room Phase 1-3 人工验收并明确表示“可以了，我验收通过了”。验收过程中覆盖真实项目数据、图片/视频/音频/Markdown 产物预览、产物弹窗两栏布局、来源展示、按来源/按路径目录视图，以及三层路径产物测试项目效果。

## 最终完成确认记录

- 确认项：done
- 确认时间：2026-06-20T07:50:53+08:00
- 用户确认摘要：用户要求归档 Phase 1-3 需求；Archive Room Phase 1-3 已按人工验收结论闭环。
