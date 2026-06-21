# Archive Room Checklist

确认状态：已确认

## Acceptance Checklist

### CHK-001: Archive Room main navigation

- 关联需求点：Archive Room is a first-level app module.
- 验证方法：启动主应用，检查主导航或一级入口区域。
- 预期结果：存在清晰的“档案室”入口；点击后进入 Archive Room，而不是项目详情内部 Tab。

### CHK-002: Project overview list

- 关联需求点：第一版核心页面是项目列表页。
- 验证方法：进入 Archive Room，查看项目列表。
- 预期结果：每个项目展示基本情况，包括任务数量、完成率、风险数、待确认数、活跃 AI、更新时间和产物数量中的核心字段。

### CHK-003: Default sorting

- 关联需求点：项目列表默认风险/待确认优先，并兼顾最近更新。
- 验证方法：准备多个项目，其中至少一个有风险或待确认项，另一个最近更新。
- 预期结果：有风险/待确认的项目优先显示；同等关注级别下最近更新项目靠前。

### CHK-004: Archive data persistence

- 关联需求点：Archive data is durable under VO storage.
- 验证方法：创建或更新项目档案后重启 VO 服务。
- 预期结果：项目档案、状态、产物元数据、待确认项和 archive manager 状态在重启后仍可读取。

### CHK-005: Confidence levels

- 关联需求点：内容可信等级为已确认事实 / AI 推断 / 待确认建议。
- 验证方法：查看项目档案中的不同类型条目。
- 预期结果：每条关键档案内容能区分 confirmed fact、AI inference、pending confirmation suggestion，且 UI/AI 输出不会把待确认建议当作已确认事实。

### CHK-006: Source references

- 关联需求点：准确性优先，档案内容应可追溯来源。
- 验证方法：打开关键决策、风险、任务产物或上下文条目。
- 预期结果：条目提供来源引用，例如任务、会议、通信事件、文件或时间戳；来源不可用时应显示明确状态。

### CHK-007: Stale context handling

- 关联需求点：过期上下文保留但标记过期。
- 验证方法：制造或导入一条被新信息替代的上下文记录。
- 预期结果：旧内容不会被静默删除；它显示为过期或已被替代，并保留历史说明或来源。

### CHK-008: Project archive detail view

- 关联需求点：人类可查看项目当前状态、决策、风险、阻塞、规则、入场包和时间线。
- 验证方法：从 Archive Room 打开单个项目档案。
- 预期结果：详情页清楚展示当前状态、关键决策、风险/阻塞、长期规则、AI 入场包摘要和相关历史/来源入口。

### CHK-009: Task artifacts visibility

- 关联需求点：第一版产物优先收录任务产物。
- 验证方法：为项目准备任务完成报告、实现说明、测试结果、交付文档和关联文件。
- 预期结果：这些产物出现在项目档案的产物区，带有类型、来源任务、更新时间和可打开入口。

### CHK-010: Document preview

- 关联需求点：文档可阅读。
- 验证方法：在产物区打开 Markdown/TXT/PDF 或受支持文档。
- 预期结果：支持的文档可在 Archive Room 中阅读；不支持预览时提供下载或打开方式。

### CHK-011: Image preview

- 关联需求点：图片可看。
- 验证方法：在产物区打开 PNG/JPG/WebP 等图片。
- 预期结果：图片可预览，并保留下载或打开入口。

### CHK-012: Video playback

- 关联需求点：视频文件希望可播放。
- 验证方法：在产物区打开浏览器支持的视频文件。
- 预期结果：视频可在 Archive Room 中播放；不支持格式时显示合理错误并提供下载或打开入口。

### CHK-013: Audio playback

- 关联需求点：音频文件可播放。
- 验证方法：在产物区打开浏览器支持的音频文件。
- 预期结果：音频可播放；不支持格式时显示合理错误并提供下载或打开入口。

### CHK-014: Generic attachment fallback

- 关联需求点：其他附件可下载或打开。
- 验证方法：在产物区打开压缩包、未知二进制文件或不支持预览的文件。
- 预期结果：系统不崩溃；提供下载或打开入口，并说明当前不能内嵌预览。

### CHK-015: Missing archive manager auto-creation

- 关联需求点：档案管理 AI 不存在时自动创建 OpenClaw agent。
- 验证方法：在没有 archive manager 的环境中启动或打开 Archive Room。
- 预期结果：系统尝试自动创建全局 OpenClaw 档案管理 AI；Archive Room 显示“已自动创建”或清楚的创建失败状态。

### CHK-016: Archive manager status

- 关联需求点：用户可感知和管理 archive manager。
- 验证方法：查看 Archive Room 中 archive manager 状态区。
- 预期结果：能看到运行中、暂停、缺失、创建中、整理中、异常等必要状态，以及最近整理记录。

### CHK-017: Pause and resume archive manager

- 关联需求点：用户可以暂停/恢复，不能从 Archive Room 删除。
- 验证方法：点击暂停和恢复控制，并检查是否存在删除控制。
- 预期结果：暂停后不再自动整理；恢复后可继续整理；第一版不提供删除按钮或删除动作。

### CHK-018: Startup inspection

- 关联需求点：每次 VO 启动后一次巡检。
- 验证方法：启动 VO 后检查 archive manager 维护记录。
- 预期结果：记录一次启动后检查；如果 archive manager 暂停，应显示跳过原因。

### CHK-019: Daily inspection

- 关联需求点：每天一次巡检。
- 验证方法：通过可控时间或调度测试触发每日巡检。
- 预期结果：每日巡检记录被写入；重复运行不会产生大量重复档案项。

### CHK-020: Event-triggered整理

- 关联需求点：任务完成、会议结束、项目状态变化、AI 阶段总结、阻塞、重要产物、冲突提醒等触发整理。
- 验证方法：分别触发至少任务完成、项目状态变化和重要产物产生。
- 预期结果：相关项目档案被更新，并记录触发来源和整理结果。

### CHK-021: Important chat classification

- 关联需求点：显式标记一定归档，archive AI 也可自动识别重要内容。
- 验证方法：标记一条聊天为重要，并准备一条涉及决策/风险/阻塞/产物的未标记聊天。
- 预期结果：显式标记聊天进入整理；自动识别的重要聊天进入候选或档案，并带有分类原因。

### CHK-022: Pending confirmation queue

- 关联需求点：长期有效规则和高影响建议需要人类确认。
- 验证方法：产生一个架构约定、业务规则、质量标准或流程规范类建议，并打开 Archive Room 项目详情页。
- 预期结果：该建议进入待确认队列，标记为 pending confirmation suggestion；项目卡片显示 pending 数量；项目详情页有专门的 pending confirmation 区域，逐条展示建议内容、置信度、影响范围、原因、来源引用和创建时间；人类可在详情页确认、拒绝或暂缓处理。

### CHK-023: Confirmed entry protection

- 关联需求点：已确认内容不能被自动覆盖。
- 验证方法：先确认一条长期规则，再产生冲突的新 AI 推断。
- 预期结果：已确认内容保留；新内容被标记为冲突或待确认，不能自动替换 confirmed fact。

### CHK-024: Conflict escalation

- 关联需求点：严重冲突先提醒执行 AI，持续违反后升级给人类。
- 验证方法：模拟执行 AI 行为违反已确认规则，并持续执行冲突操作。
- 预期结果：第一次严重冲突提醒执行 AI；持续违反后产生人类可见升级提醒。

### CHK-025: Reminder severity

- 关联需求点：严重冲突打断，普通风险提示，低价值补充只记录。
- 验证方法：分别制造严重冲突、普通风险和低价值补充。
- 预期结果：三类提醒的呈现强度不同，低价值补充不会打断执行流。

### CHK-026: AI onboarding package

- 关联需求点：新 AI 默认获得标准入场包。
- 验证方法：请求某项目的 AI onboarding context。
- 预期结果：返回项目目标、当前状态、关键规则、当前任务、关键决策、风险/阻塞和相关目录索引。

### CHK-027: Human-readable archive introduction

- 关联需求点：用户打开项目档案时，应先理解“这个档案是干什么的、里面有什么、以后会放什么、可以用来做什么”。
- 验证方法：打开一个有真实任务、产物和维护记录的项目档案详情页。
- 预期结果：详情页在机械摘要之外展示档案说明和信息地图，包括档案用途、已包含的信息类型、未来会继续补充的信息、可用于人类验收/追踪/交接和 AI 入场/上下文查询的能力。

### CHK-028: Project basic information in archive detail

- 关联需求点：档案基础情况应包含项目基础信息，而不是只有 Goal/Current State/Next Step 的机械概括。
- 验证方法：打开项目档案详情页，并对照项目原始数据。
- 预期结果：项目基础信息清楚展示项目名称、描述、状态、任务进度、最近更新、长期维护状态、活跃 AI/参与者（如有）、产物数量、待确认数量和主要来源类型；缺失字段应显示“暂无/未记录”，不能让用户误解为空事实。

### CHK-029: AI context query response shape

- 关联需求点：执行 AI 查询时先返回最相关结论，再附来源和可继续加载目录项。
- 验证方法：针对一个具体任务请求项目上下文。
- 预期结果：响应先给结论，再给 source references，并给出可选继续加载的 archive entries。

### CHK-030: Project-characterized AI context injection

- 关联需求点：Phase 6 应让 AI 的项目/任务上下文体现项目自己的特征，而不是只使用通用机械摘要。
- 验证方法：让同一个 AI 分别进入两个不同项目或两个不同任务，查看其入场包/任务上下文/提醒内容。
- 预期结果：AI 获得的上下文能体现当前项目的业务背景、目标、已确认规则、用户偏好、决策风格、重要历史、风险和相关产物；不同项目的上下文有可感知差异；该上下文只作为项目/任务补充，不改写 AI 的全局身份、安全边界或通用工具规则。

### CHK-031: Degraded mode

- 关联需求点：Archive Room should remain usable when archive AI creation or整理 fails.
- 验证方法：模拟 OpenClaw unavailable、agent creation failure or archive manager error。
- 预期结果：Archive Room 仍能查看已有项目和产物；自动整理能力显示异常或降级，不导致主应用不可用。

### CHK-032: Security and file access boundaries

- 关联需求点：artifact preview must not expose arbitrary local files.
- 验证方法：尝试通过 artifact preview 访问非授权路径、路径穿越或 VO 数据根之外的文件。
- 预期结果：请求被拒绝；只允许访问合法 archive/artifact roots 中的文件。

### CHK-033: Regression for existing project/chat features

- 关联需求点：Archive Room should not replace or break existing project/task/chat flows.
- 验证方法：执行现有项目列表、任务详情、聊天、agent chat bubble、meeting history 等关键流程。
- 预期结果：原有流程仍可使用，已有数据不会被 Archive Room 迁移或整理破坏。

### CHK-034: Observability of maintenance activity

- 关联需求点：用户能看到 archive manager 最近整理记录。
- 验证方法：触发自动创建、事件整理、启动巡检、每日巡检和暂停跳过。
- 预期结果：Archive Room 显示清晰的维护记录，包括时间、触发原因、结果和错误摘要。

### CHK-035: Phase acceptance

- 关联需求点：需求需要拆成多个 phase 可逐步交付。
- 验证方法：按 requirement.md 中 Phase 1 到 Phase 7 的 exit criteria 逐项检查。
- 预期结果：每个 phase 都有明确可验收结果，后续 phase 不要求前一 phase 之外的隐藏功能才能验证。

### CHK-036: Archive maintenance frequency controls

- 关联需求点：Phase 8 应支持为长期维护项目设置档案整理频率。
- 验证方法：打开 Archive Room 项目详情页，选择一个开启长期维护的项目，设置整理频率为事件触发、每日、每周或自定义间隔；触发对应调度或模拟时间推进，并检查维护记录。
- 预期结果：项目详情页显示当前整理频率、下一次计划整理时间、上次计划整理时间和上次事件触发整理时间；调度按项目配置执行；事件触发整理不受计划频率阻塞；暂停档案管理员或关闭项目长期维护时，计划整理不会执行，并记录清晰的跳过原因。

### CHK-037: Archive-manager-first governance

- 关联需求点：Phase 8 应减少人工操作，让档案管理员优先自动治理，人工只做兜底确认。
- 验证方法：分别制造低风险来源明确补充、普通表述冲突、旧 AI 推断被新强来源替代、与人工确认规则冲突、两个高可信来源冲突的场景。
- 预期结果：低风险和来源明确内容由档案管理员自动确认；普通表述差异或旧 AI 推断可由档案管理员自动合并/标记过期；只有替换人工确认规则、两个高可信来源冲突或需要 owner 业务决策的内容进入人工确认队列；人工队列中的条目必须说明档案管理员的判断、不能自动处理的原因，以及需要人选择什么。

## Parent Closeout Record

- 确认项：Archive Room parent checklist and final closeout
- 确认时间：2026-06-22T00:54:03+08:00
- 用户确认摘要：用户确认“可以的，争取今天把他收尾掉吧”。
- 覆盖方式：父需求 checklist 由已完成归档的 `archive-room-phase-1-3`、`archive-room-phase-4`、`archive-room-phase-5`、`archive-room-phase-6`、`archive-room-phase-7`、`archive-room-phase-8` 及 `functional-furniture-bookshelf-archive` 分阶段验收覆盖。
- 总体验收结论：通过。覆盖档案室一级入口、项目列表、项目详情、产物预览、档案管理员生命周期与角色边界、事件/计划整理、AI 入场上下文、人工治理、维护频率、档案管理员优先治理、书架绑定入口，以及近期验收中修正的滚动保持、按钮对齐和顶部留白问题。
- 归档说明：父需求作为总验收壳闭环归档，不再生成重复 todolist。

## Main Acceptance Run

- 执行时间：2026-06-22T01:05:12+08:00
- 执行范围：主需求总体验收动作，不新增开发拆解。
- 需求状态检查：通过 `requirement_status.py --all`，确认 `archive-room`、`archive-room-phase-1-3`、`archive-room-phase-4`、`archive-room-phase-5`、`archive-room-phase-6`、`archive-room-phase-7`、`archive-room-phase-8` 和 `functional-furniture-bookshelf-archive` 均为已完成归档。
- 服务健康检查：`GET /health` 返回 `{"ok": true, "status": "running"}`。
- 档案室 API 检查：`GET /api/archive-room` 返回 `ok: true`，档案管理员状态为已接入，项目列表和维护数据可读取。
- 静态检查：`node --check app/archive-room.js` 和 `node --check tests/chrome_archive_room_phase8_check.mjs` 通过。
- UI/CDP 验收：`node tests/chrome_archive_room_phase8_check.mjs` 通过。确认项目可见、每周频率可见、调整频率面板可见、点击调整后滚动保持、自动治理可见、stale 可见、来源对比可见、待确认可见、产物弹窗可见、按路径视图可见、图片/视频/音频/Markdown 产物可见。
- 验收结论：通过，主需求进入最终验收可确认状态。
