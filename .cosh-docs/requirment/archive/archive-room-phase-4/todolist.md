# Archive Room Phase 4 Todolist

## TODO-001: Map Existing Agent And Archive Room Surfaces

- 目标：明确 Phase 4 需要接入的现有 Agent、OpenClaw、Archive Room、Projects 和 chat 入口。
- 涉及区域：agent discovery/provider code、Archive Room APIs/UI、project task assignment UI/API、chat routing。
- 输入：Phase 4 requirement/review/checklist、现有 Phase 1-3 Archive Room 实现、OpenClaw agent profile 格式。
- 输出：实现前的代码路径和数据流确认。
- 依赖：无。
- 完成标准：确认 archive manager identity、状态持久化、自动创建、办公室可见、任务分配保护、chat 边界所需改动点。
- 关联 checklist：CHK-001、CHK-006、CHK-014、CHK-017、CHK-020、CHK-021。

## TODO-002: Define Durable Archive Manager State

- 目标：建立 Archive Room 管理全局档案管理员生命周期所需的状态记录。
- 涉及区域：`VO_STATUS_DIR/archive-room/`、server-side archive manager helpers。
- 输入：manager identity、agent id、display name、provider kind、paused flag、auto-created marker、last action、last error、recent activity。
- 输出：可读写的 archive manager status record。
- 依赖：TODO-001。
- 完成标准：状态可持久化；重启后能恢复 manager identity、paused 状态、auto-created marker 和 recent activity。
- 关联 checklist：CHK-001、CHK-003、CHK-005、CHK-010、CHK-019。

## TODO-003: Detect And Auto-Create The Archive Manager

- 目标：当 `档案管理员` 不存在时自动创建，并避免重复创建。
- 涉及区域：OpenClaw agent discovery/create flow、Archive Room status API。
- 输入：existing agent registry/discovery、desired archive manager identity。
- 输出：idempotent detect/create behavior and status updates。
- 依赖：TODO-001、TODO-002。
- 完成标准：已有 manager 时复用；缺失时自动创建并显示 `已自动创建`；重复打开/重启/并发请求不产生多个 manager。
- 关联 checklist：CHK-001、CHK-002、CHK-003。

## TODO-004: Create Prompt, Soul, Identity, And Agent Profile Contract

- 目标：让自动创建/维护后的档案管理员具备明确身份、性格、工作作风和输出纪律。
- 涉及区域：OpenClaw agent profile files such as `agent.md`、identity、soul、prompt-related files。
- 输入：Phase 4 clarified product rules and OpenClaw profile conventions。
- 输出：`档案管理员` profile content and validation logic。
- 依赖：TODO-001、TODO-003。
- 完成标准：profile 明确 archive-only role、冷静精确重证据的工作风格、非执行 AI 边界、越界请求处理、结构化输出要求。
- 关联 checklist：CHK-015、CHK-016、CHK-014、CHK-017。

## TODO-005: Add Structured Operational Output Contract

- 目标：定义并验证档案管理员面向 VO 的维护输出格式，使 VO 可识别、持久化和渲染。
- 涉及区域：manual整理 result handling、archive manager output parsing/rendering、recent activity。
- 输入：manager profile output rules、Archive Room data model。
- 输出：稳定字段、标签或结构化块的维护结果约定。
- 依赖：TODO-002、TODO-004。
- 完成标准：手动整理或模拟维护输出可被 VO 识别为状态、摘要、来源、错误或建议；关键动作不依赖不可控长篇自由文本解析。
- 关联 checklist：CHK-016、CHK-010、CHK-011、CHK-013。

## TODO-006: Implement Archive Room Global Manager Status Bar

- 目标：在 Archive Room 顶部展示全局档案管理员状态和关键操作。
- 涉及区域：`app/archive-room.js`、`app/archive-room.css`、Archive Room status API。
- 输入：manager status record、agent status、paused/error state。
- 输出：状态条和状态文案。
- 依赖：TODO-002、TODO-003。
- 完成标准：显示 missing、auto-created、idle、working/整理中、paused、error；说明这是全局档案管理员。
- 关联 checklist：CHK-005、CHK-004、CHK-007、CHK-008。

## TODO-007: Implement Pause And Resume Controls

- 目标：让用户可暂停/恢复档案管理员。
- 涉及区域：Archive Room APIs/UI、manager state、main office presence/status projection。
- 输入：paused flag、user action、recent activity。
- 输出：pause/resume API and UI behavior。
- 依赖：TODO-002、TODO-006。
- 完成标准：暂停后状态持久化、办公室显示暂停、不会主动维护；恢复后回到 idle/可工作状态并记录活动。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-010、CHK-019。

## TODO-008: Surface Paused Notice In Project Detail

- 目标：在 paused 状态下对项目详情展示轻量新鲜度提示。
- 涉及区域：Archive Room project detail UI。
- 输入：manager paused state。
- 输出：项目详情轻量提示。
- 依赖：TODO-006、TODO-007。
- 完成标准：暂停时项目详情显示档案可能不会自动更新；不在每个条目/产物重复刷屏。
- 关联 checklist：CHK-009、CHK-020。

## TODO-009: Implement Current-Project Manual整理

- 目标：允许用户对当前项目手动触发一次整理，并记录结果。
- 涉及区域：Archive Room project detail UI/API、manager action runner、archive record update path、recent activity。
- 输入：current project id、manager status、structured output contract。
- 输出：current-project manual整理 action。
- 依赖：TODO-002、TODO-005、TODO-006。
- 完成标准：只整理当前项目；状态短暂显示 working/整理中；完成或失败都记录 recent activity；不触发全部项目、启动、每日或事件调度。
- 关联 checklist：CHK-011、CHK-012、CHK-013、CHK-010、CHK-022。

## TODO-010: Implement Creation And Action Failure Degraded Mode

- 目标：确保 manager 创建或操作失败时 Archive Room 仍可只读使用。
- 涉及区域：Archive Room APIs/UI、error state、recent activity。
- 输入：OpenClaw unavailable/create failure/manual整理 failure。
- 输出：read-only degraded behavior and user-visible error。
- 依赖：TODO-002、TODO-003、TODO-006、TODO-009。
- 完成标准：错误可理解；状态条和活动日志显示失败；项目列表、详情、产物预览仍可用。
- 关联 checklist：CHK-004、CHK-013、CHK-020。

## TODO-011: Make Archive Manager Visible In Main Office

- 目标：办公室主视图中可见真实 `档案管理员` Agent，且状态与 Archive Room 一致。
- 涉及区域：agent discovery/status projection、office rendering/status labels。
- 输入：OpenClaw agent identity、manager paused/error/idle state。
- 输出：main office visible agent state。
- 依赖：TODO-003、TODO-007。
- 完成标准：自动创建或识别后办公室可见；paused 显示为暂停而非隐藏或误报离线。
- 关联 checklist：CHK-006、CHK-007、CHK-008。

## TODO-012: Enforce Archive Manager Role Boundaries In Chat

- 目标：限制档案管理员只处理档案相关聊天，并对越界请求给出清晰反馈。
- 涉及区域：chat routing, agent prompt/guardrails, Archive Room manager identity。
- 输入：archive-related request, out-of-scope request。
- 输出：archive-only chat behavior。
- 依赖：TODO-004。
- 完成标准：档案相关问题可响应；普通执行/闲聊/任务执行请求会说明职责边界并引导用户使用合适 AI。
- 关联 checklist：CHK-014、CHK-015。

## TODO-013: Prevent Normal Project Task Assignment

- 目标：避免档案管理员被作为普通执行/审查 AI 分配项目任务。
- 涉及区域：project task assignee/reviewer UI、project task create/update APIs、workflow dispatch validation。
- 输入：archive manager agent id。
- 输出：UI disable/hidden state and server-side rejection or safe guard。
- 依赖：TODO-003、TODO-011。
- 完成标准：UI 不可选或清楚标记不可用；直接 API 保存也不能让其成为普通执行/审查 AI。
- 关联 checklist：CHK-017、CHK-021。

## TODO-014: Remove Delete Capability From Archive Room Manager Controls

- 目标：确保 Archive Room 不提供删除档案管理员入口。
- 涉及区域：Archive Room manager controls。
- 输入：manager status and user controls。
- 输出：allowed controls only。
- 依赖：TODO-006、TODO-007。
- 完成标准：Archive Room 仅提供暂停、恢复、当前项目手动整理等允许操作，不提供删除。
- 关联 checklist：CHK-018。

## TODO-015: Add Automated And Focused Regression Tests

- 目标：覆盖 Phase 4 后端状态、创建、暂停恢复、失败降级、角色边界和 Phase 1-3 回归。
- 涉及区域：tests for server helpers/APIs/UI static behavior where feasible。
- 输入：Phase 4 implementation。
- 输出：automated tests and deterministic fixtures。
- 依赖：TODO-002 至 TODO-014。
- 完成标准：测试覆盖 detect/create idempotency、state persistence、pause/resume、manual整理 scope、failure degraded mode、assignment guard、structured output validation、Phase 1-3 core APIs。
- 关联 checklist：CHK-001 至 CHK-022。

## TODO-016: Run Live/MCP Acceptance Checks

- 目标：在真实启动服务中验收 Archive Room Phase 4 用户路径。
- 涉及区域：running VO service、Archive Room UI、main office UI、project detail。
- 输入：implemented Phase 4 and sample projects。
- 输出：live acceptance record。
- 依赖：TODO-015。
- 完成标准：真实 UI 验证自动创建、状态条、暂停/恢复、当前项目手动整理、办公室可见、失败降级可观测、Phase 1-3 产物预览不回归。
- 关联 checklist：CHK-002、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-011、CHK-018、CHK-020。

## TODO-017: Update Requirement Archive And Parent Requirement Notes

- 目标：记录 Phase 4 实现、测试结果、边界和后续 Phase 5/6/7 遗留项。
- 涉及区域：`.cosh-docs/requirment/archive-room-phase-4/` and parent `archive-room` notes/checklist if needed。
- 输入：implementation summary, test results, user acceptance。
- 输出：checklist test records, status updates, parent progress note。
- 依赖：TODO-015、TODO-016。
- 完成标准：Phase 4 checklist 写入测试记录；`status.json` 推进到 implementation_done/tested/done 的合适阶段；父需求同步记录 Phase 4 完成后剩余 Phase 5-7。
- 关联 checklist：CHK-020、CHK-021、CHK-022。

