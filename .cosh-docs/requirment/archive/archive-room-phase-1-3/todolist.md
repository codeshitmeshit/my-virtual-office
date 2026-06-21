# Archive Room Phase 1-3 Todolist

## TODO-001: Confirm Existing Project And UI Entry Points

- 目标：梳理现有项目列表、任务数据、主应用导航和页面挂载方式，为 Archive Room 接入选择最小改动路径。
- 涉及区域：主应用 HTML/JS、项目模块、服务端项目读取路径、现有导航或侧边入口。
- 输入：`requirement.md`、`checklist.md`、现有项目/任务数据结构。
- 输出：实现前的代码定位结果和接入点选择。
- 依赖：无。
- 完成标准：明确 Archive Room 入口、overview 数据来源、detail 数据来源和 artifact 访问路径；不改变现有项目/聊天/会议流程。
- 关联 checklist：CHK-009, CHK-010, CHK-015, CHK-027。

## TODO-002: Add Archive Data Model And Durable Storage

- 目标：建立 Phase 1 所需的项目档案数据基础，受 `VO_STATUS_DIR` 控制。
- 涉及区域：服务端 archive 数据读写、项目档案文件、初始化/派生逻辑。
- 输入：现有项目和任务记录、`VO_STATUS_DIR`、需求中的 confidence/source/stale/artifact metadata 规则。
- 输出：可读取和写入的项目 archive records。
- 依赖：TODO-001。
- 完成标准：每个项目可拥有 durable archive record；数据重启后保留；记录支持 confidence level、source references、stale flags、pending confirmation counters、artifact metadata。
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-005, CHK-006, CHK-007, CHK-030。

## TODO-003: Implement Safe Initial Archive Derivation

- 目标：从现有项目/任务数据派生基础档案，缺失字段时优雅降级。
- 涉及区域：archive 初始化逻辑、overview 派生字段、fallback 状态。
- 输入：已有项目名称、状态、任务数量、更新时间、可得 artifact metadata。
- 输出：基础档案初始化结果和缺失字段 fallback。
- 依赖：TODO-002。
- 完成标准：已有项目至少形成基础档案；缺少风险、待确认、活跃 AI、artifact metadata 时显示空/0/unknown，不伪造信息。
- 关联 checklist：CHK-003, CHK-004, CHK-008。

## TODO-004: Add Archive Room First-Level Navigation

- 目标：在主应用中加入一级“档案室”入口。
- 涉及区域：主应用入口 UI、路由/视图切换、i18n 文案（如适用）。
- 输入：现有主导航模式和 Archive Room 页面容器。
- 输出：可点击进入的 Archive Room 主入口。
- 依赖：TODO-001。
- 完成标准：用户可从主应用一级入口打开 Archive Room；入口不是项目详情内部 Tab；不破坏现有导航。
- 关联 checklist：CHK-009, CHK-015。

## TODO-005: Build Project Overview List

- 目标：实现 Archive Room 默认项目总览视图。
- 涉及区域：Archive Room 前端列表/卡片、overview 数据接口或读取逻辑、空状态和错误状态。
- 输入：archive overview records、项目基础状态、风险/待确认/更新时间/artifact counts。
- 输出：项目概览列表或卡片视图。
- 依赖：TODO-002, TODO-003, TODO-004。
- 完成标准：展示项目名称、当前状态、任务数量、完成率、风险数、待确认数、活跃 AI、最近更新时间、产物数量中的可得字段；没有数据时有空状态；加载失败有错误状态。
- 关联 checklist：CHK-010, CHK-011, CHK-013, CHK-014, CHK-029。

## TODO-006: Implement Attention-First Sorting

- 目标：让项目总览优先回答“哪些项目需要人类关注”。
- 涉及区域：overview 排序逻辑、排序文案或默认顺序。
- 输入：风险数、待确认数、最近更新时间。
- 输出：默认风险/待确认优先且兼顾最近更新的排序。
- 依赖：TODO-005。
- 完成标准：有风险/待确认的项目排前；同等关注级别下最近更新项目靠前。
- 关联 checklist：CHK-012。

## TODO-007: Add Minimal Archive Manager Placeholder

- 目标：保留主需求连续性，但不提前实现 Phase 4 AI 生命周期。
- 涉及区域：Archive Room overview 状态区域或占位文案。
- 输入：Phase 1-3 范围边界。
- 输出：最小 archive manager 状态占位。
- 依赖：TODO-005。
- 完成标准：只显示“后续阶段启用”“未接入”或等价状态；不自动创建 AI，不提供暂停/恢复，不显示整理记录。
- 关联 checklist：CHK-009A, CHK-028。

## TODO-008: Build Project Archive Detail View

- 目标：用户可从总览进入单项目档案详情。
- 涉及区域：Archive Room detail view、返回总览、项目档案读取。
- 输入：单项目 archive record。
- 输出：项目档案详情页或详情面板。
- 依赖：TODO-005。
- 完成标准：总览项目可打开详情并返回；详情分区展示当前状态、目标/摘要、关键决策、风险/阻塞、规则、来源/时间线入口。
- 关联 checklist：CHK-016, CHK-017, CHK-026, CHK-029。

## TODO-009: Add Confidence, Source, And Stale Presentation

- 目标：在详情中表达可信等级、来源和过期状态。
- 涉及区域：detail entry rendering、标签/状态文案、source link display。
- 输入：archive entries 的 confidence level、source references、stale flags。
- 输出：用户可理解的可信等级、来源和 stale 标记。
- 依赖：TODO-002, TODO-008。
- 完成标准：confirmed fact、AI inference、pending confirmation suggestion 和 stale entries 可区分；来源不可用时显示清楚提示。
- 关联 checklist：CHK-005, CHK-006, CHK-007, CHK-018, CHK-026。

## TODO-010: Add Human-Readable Onboarding Package Section

- 目标：在项目详情中展示可读可复制的标准入场包，为后续 AI 入场打基础。
- 涉及区域：project detail onboarding/context section、复制交互。
- 输入：项目目标、当前状态、关键决策、风险/阻塞、可得上下文摘要。
- 输出：人类可查看和复制的入场包。
- 依赖：TODO-008, TODO-009。
- 完成标准：用户能查看并复制入场内容；UI 不承诺自动 AI 读取或 AI 查询。
- 关联 checklist：CHK-017A, CHK-028A。

## TODO-011: Register And Display Explicitly Associated Artifacts

- 目标：展示与项目/任务明确关联的任务产物，避免无差别展示所有文件。
- 涉及区域：artifact metadata、artifact list UI、任务来源关联。
- 输入：任务完成报告、实现说明、测试结果、交付文档、关联文件 metadata。
- 输出：项目详情中的产物列表。
- 依赖：TODO-002, TODO-008。
- 完成标准：产物区显示名称、类型、来源任务/来源记录、创建或更新时间、文件大小或可得 metadata、打开入口；未明确关联的普通文件不作为档案产物展示。
- 关联 checklist：CHK-019, CHK-019A。

## TODO-012: Implement Safe Artifact Open And Preview Flow

- 目标：为 artifact 提供安全的打开、预览和 fallback 行为。
- 涉及区域：artifact 访问路由或资源服务、前端 preview modal/panel、下载/open fallback。
- 输入：注册 artifact metadata、允许访问的 archive/artifact roots。
- 输出：安全 artifact preview/open/download 体验。
- 依赖：TODO-011。
- 完成标准：只允许访问合法 archive/artifact roots 或注册 artifact metadata 中的文件；路径穿越、未登记文件、VO 数据根之外访问被拒绝。
- 关联 checklist：CHK-020, CHK-021, CHK-022, CHK-023, CHK-024, CHK-025。

## TODO-013: Add Document, Image, Video, And Audio Preview UI

- 目标：覆盖 Phase 3 常见产物预览体验。
- 涉及区域：preview UI、文档查看、图片查看、video/audio native controls、unsupported fallback。
- 输入：Markdown/TXT/PDF、PNG/JPG/GIF/WebP、MP4/WebM、MP3/WAV/OGG 等 artifact。
- 输出：常见文档和媒体预览能力。
- 依赖：TODO-012。
- 完成标准：文档可读或可打开；图片可预览；浏览器支持的视频/音频可播放；不支持格式显示合理错误并可下载或打开。
- 关联 checklist：CHK-020, CHK-021, CHK-022, CHK-023, CHK-024。

## TODO-014: Add Regression And Data State Tests

- 目标：覆盖 Phase 1-3 的核心验收，防止破坏既有功能。
- 涉及区域：服务端数据测试、前端可用性测试、已有项目/聊天/会议回归。
- 输入：checklist 中的数据状态、空状态、错误状态、存储路径、安全边界、现有流程。
- 输出：可重复执行的测试或验证脚本，以及人工验证记录入口。
- 依赖：TODO-002 至 TODO-013。
- 完成标准：覆盖 archive persistence、overview/detail、artifact preview safety、现有项目/聊天/会议回归；测试结果可用于 checklist 验收。
- 关联 checklist：CHK-001, CHK-002, CHK-013, CHK-014, CHK-015, CHK-025, CHK-027, CHK-030。

## TODO-015: Update Documentation And Checklist Evidence

- 目标：记录 Phase 1-3 范围、使用方式、非目标和测试结果，支持后续 phase 接续。
- 涉及区域：需求归档、README 或内部文档、checklist 测试记录。
- 输入：实现结果、测试输出、人工验证结果。
- 输出：更新后的说明和 checklist 证据。
- 依赖：TODO-014。
- 完成标准：文档说明 Phase 1-3 不含 AI 生命周期和自动整理；记录如何打开 Archive Room、如何查看详情、如何预览产物、哪些内容属于后续 phase。
- 关联 checklist：CHK-028, CHK-028A, CHK-029, CHK-030。
