# Archive Room Phase 4 Checklist

确认状态：已确认

## Archive Manager Identity And Creation

### CHK-001: Detect Existing Archive Manager

- 关联需求点：Phase 4 detects whether the global archive management AI exists.
- 验证方法：准备已存在 `档案管理员` 的环境并打开 Archive Room。
- 预期结果：系统识别已有 archive manager，不重复创建，状态条显示真实 manager 状态。

### CHK-002: Auto-Create Missing Archive Manager

- 关联需求点：Missing archive manager should be automatically created and surfaced as `已自动创建`.
- 验证方法：在没有 archive manager 的环境打开 Archive Room。
- 预期结果：系统自动创建名为 `档案管理员` 的 OpenClaw agent；Archive Room 显示 `已自动创建` 和创建时间。

### CHK-003: Auto-Create Idempotency

- 关联需求点：Archive manager is one global agent.
- 验证方法：重复打开 Archive Room、重启服务后再次打开、并发请求 Archive Room。
- 预期结果：不会创建多个档案管理员；状态记录始终指向同一个真实 agent。

### CHK-004: Creation Failure Degraded Mode

- 关联需求点：Archive Room remains read-only usable if creation fails.
- 验证方法：模拟 OpenClaw 不可用或创建失败。
- 预期结果：Archive Room 顶部显示创建失败和可理解原因；项目列表、项目详情、产物预览仍可浏览。

## Status, Visibility, And Controls

### CHK-005: Global Status Bar

- 关联需求点：Archive manager status is most visible in an Archive Room top-level status bar.
- 验证方法：打开 Archive Room，观察不同状态下的顶部状态条。
- 预期结果：能展示 missing、auto-created、idle、working/整理中、paused、error 中的可得状态，并说明这是全局档案管理员。

### CHK-006: Main Office Agent Visibility

- 关联需求点：Archive manager is dual-visible in Archive Room and the main office.
- 验证方法：自动创建或识别 archive manager 后回到办公室主视图。
- 预期结果：办公室中能看到真实 Agent `档案管理员`；状态与 Archive Room 一致。

### CHK-007: Pause Control

- 关联需求点：Users can pause the archive manager.
- 验证方法：点击暂停并刷新 Archive Room / 主办公室。
- 预期结果：状态变为 paused；不会主动维护档案；已有档案仍可读。

### CHK-008: Resume Control

- 关联需求点：Users can resume the archive manager.
- 验证方法：在 paused 状态点击恢复。
- 预期结果：状态回到 idle 或可工作状态；办公室 Agent 不再显示暂停。

### CHK-009: Paused Notice In Project Detail

- 关联需求点：Project detail should show a lightweight paused notice.
- 验证方法：暂停 archive manager 后进入任意项目详情。
- 预期结果：项目详情显示轻量提示，说明档案可能不会自动更新；不会在每个条目/产物重复刷屏。

### CHK-010: Recent Maintenance Activity

- 关联需求点：Recent lifecycle and maintenance activity should be visible.
- 验证方法：执行自动创建、暂停、恢复、手动整理、失败场景。
- 预期结果：Archive Room 可看到简短活动日志，包含动作、时间、结果和失败原因。

## Manual Current-Project整理

### CHK-011: Manual整理 For Current Project

- 关联需求点：Pause still allows user to manually trigger one整理 for the currently open project.
- 验证方法：打开项目详情并点击当前项目手动整理。
- 预期结果：只整理当前项目；状态短暂显示 working/整理中；完成后记录活动日志。

### CHK-012: Manual整理 Scope Boundary

- 关联需求点：Phase 4 does not include all-project/event/startup/daily maintenance.
- 验证方法：触发当前项目手动整理后检查其他项目和系统计划任务。
- 预期结果：不会批量整理全部项目，不注册事件触发器，不创建启动/每日巡检任务。

### CHK-013: Manual整理 Failure

- 关联需求点：Action failures should not break Archive Room.
- 验证方法：模拟 manager 不可用或整理失败后点击手动整理。
- 预期结果：显示错误并记录活动；Archive Room 仍可浏览现有档案。

## Role Boundaries

### CHK-014: Archive-Only Chat Boundary

- 关联需求点：The archive manager may chat only about archive-related topics.
- 验证方法：分别向 `档案管理员` 发送档案相关问题和普通执行/闲聊问题。
- 预期结果：档案相关问题可响应；非档案请求给出清晰的职责边界反馈。

### CHK-015: Prompt, Soul, Identity, And Agent Profile

- 关联需求点：The archive manager prompt/persona files should explicitly define role, work style, personality boundary, and output discipline.
- 验证方法：检查自动创建或维护后的 archive manager profile，包括 `agent.md`、identity、soul 和相关 prompt 文件。
- 预期结果：这些文件明确说明 `档案管理员` 是档案管理专用 AI，工作作风冷静、精确、重证据；不承担普通执行任务；遇到越界请求要明确拒绝或引导；维护输出必须结构化、稳定、可被 VO 识别处理和渲染。

### CHK-016: Structured Operational Output Contract

- 关联需求点：Archive manager work output must be strictly controllable and renderable by VO.
- 验证方法：触发当前项目手动整理或模拟 archive manager 维护输出。
- 预期结果：面向 VO 的维护结果使用稳定字段、标签或结构化块；VO 能识别并渲染状态、摘要、来源、错误或建议；不依赖不可控长篇自由文本解析关键动作。

### CHK-017: Not Assignable To Normal Project Tasks

- 关联需求点：The archive manager cannot be assigned normal project tasks.
- 验证方法：在项目任务执行人/审查人选择中尝试选择 `档案管理员`，并直接调用相关保存接口。
- 预期结果：UI 不可选或清楚标记不可用；服务端应拒绝普通任务分配或避免保存为执行/审查 AI。

### CHK-018: Cannot Delete From Archive Room

- 关联需求点：Users cannot delete archive manager from Archive Room, only pause/resume.
- 验证方法：检查 Archive Room 管理区可用操作。
- 预期结果：没有删除入口；只有暂停、恢复、当前项目手动整理等允许操作。

### CHK-019: Not A Normal Meeting Participant

- 关联需求点：Archive manager is a system archive role, not a normal meeting collaborator.
- 验证方法：打开普通会议创建页和会议请求确认页；同时直接调用会议创建/确认 API，尝试将 `archive-manager` 作为参与者或主持人。
- 预期结果：会议参与人/主持人 UI 不展示 `档案管理员`；服务端拒绝绕过 UI 的创建或确认请求，并返回 `archive_manager_not_meeting_participant`。

## Persistence, Compatibility, And Regression

### CHK-020: Lifecycle State Persistence

- 关联需求点：Archive manager lifecycle state should be durable.
- 验证方法：自动创建、暂停、恢复后重启服务。
- 预期结果：manager identity、paused 状态、auto-created marker、recent activity 仍可读取。

### CHK-021: Phase 1-3 Regression

- 关联需求点：Archive Room Phase 1-3 behavior must remain usable.
- 验证方法：打开项目总览、项目详情、AI 入场包、产物弹窗、按来源/按路径视图和媒体预览。
- 预期结果：Phase 1-3 已验收能力不回归。

### CHK-022: Existing Project/Chat/Meeting Regression

- 关联需求点：Archive manager must not replace existing project/task/chat/meeting flows.
- 验证方法：执行普通项目任务查看/创建、普通 Agent 聊天、会议入口基本流程。
- 预期结果：既有项目、聊天、会议功能仍可使用。

### CHK-023: Clear Future-Phase Boundary

- 关联需求点：Phase 5/6/7 features are out of scope.
- 验证方法：检查 UI 文案、行为和后台任务。
- 预期结果：不承诺事件触发整理、启动/每日巡检、AI context query、执行 AI 提醒、确认队列或治理审批；如出现提示，应标记为后续阶段。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-20T08:12:23+08:00
- 用户确认摘要：用户回复 `continue`，确认 Archive Room Phase 4 checklist 可以进入 todolist 生成。确认范围包含全局档案管理员自动创建、状态可见、暂停/恢复、当前项目手动整理、失败降级、办公室双重可见、角色边界、prompt/soul/identity/agent.md 输出纪律、Phase 1-3 回归和 Phase 5/6/7 边界。

## 实现与测试记录

- 实现时间：2026-06-20
- 实现摘要：已实现全局 `档案管理员` 自动创建、状态持久化、Archive Room 顶部状态条、暂停/恢复、当前项目手动整理、最近活动日志、失败降级、主办公室/agent 列表系统角色标记、普通任务分配保护、普通会议参与保护、删除保护、聊天越界守卫，以及 `IDENTITY.md`、`SOUL.md`、`AGENTS.md`、`agent.md`、`MEMORY.md`、`HEARTBEAT.md` profile 输出纪律。OpenClaw 对部分 profile 文件存在网关白名单限制，因此档案管理员 profile 统一直写到其 OpenClaw workspace。
- 自动化验证：
  - `.venv/bin/python -m py_compile app/server.py`：通过。
  - `.venv/bin/python tests/test_archive_room_phase_4.py`：通过，覆盖自动创建幂等、profile 文件、创建失败降级、暂停/恢复、当前项目手动整理、删除/分配保护、聊天边界。
  - `.venv/bin/python tests/test_archive_room_phase_1_3.py`：通过，覆盖 Phase 1-3 档案概览、产物关联、媒体/文件访问边界。
  - `.venv/bin/python tests/test_project_execution.py`：单独运行通过，覆盖既有 Project Execution 回归；测试日志包含预期的 Gateway 降级连接失败，最终结果为 `ok`。
- 真实服务冒烟：
  - 使用 `VO_PORT=8160 VO_WS_PORT=8161 ./start.sh` 启动通过，访问地址为 `http://localhost:8160`。
  - `GET /api/archive-room` 返回 `档案管理员 🗄️`，状态 `idle`，标签 `已接入`。
  - `GET /agents-list` 返回 `archive-manager`，包含 `systemRole: archive_manager`、`assignable: false`、`archiveManagerStatus: idle`。
  - `POST /api/archive-room/manager` 暂停/恢复通过，最终已恢复到 `idle/已接入`。
  - `/home/wo/.openclaw/workspace-archive-manager/AGENTS.md` 和 `agent.md` 已写入档案管理角色边界与 `vo-archive-manager` 结构化输出约定。
- 范围边界：未实现 Phase 5/6/7 的事件触发整理、启动/每日巡检、AI context query/onboarding API、执行 AI 主动提醒、确认队列或治理审批。
- 维护性调整：2026-06-20T09:55:07+08:00 已将档案管理员 `IDENTITY.md`、`SOUL.md`、`AGENTS.md`、`agent.md`、`MEMORY.md`、`HEARTBEAT.md` 的静态文本迁移到 `app/archive-manager-profile.md` 单文件模板；后端只负责加载模板、替换变量并写入 OpenClaw workspace，避免 persona/prompt 文本耦合在 `server.py` 中。
- Prompt/配置同步增强：2026-06-20T12:45:09+08:00 已将 `app/archive-manager-profile.md` 升级到 `2026-06-20.2`，补充手动整理操作规程、证据/置信度规则、稳定输出字段规则、update kind 语义和硬边界；VO 启动时会后台检查 `档案管理员` workspace 中的 profile 版本，缺失或版本不一致时自动重写配置，并在 manager activity 中记录 `profile_update`。
- 增强验证：
  - `.venv/bin/python -m py_compile app/server.py`：通过。
  - `.venv/bin/python tests/test_archive_room_phase_4.py`：通过，覆盖模板版本头、旧版本 profile 自动更新、结构化输出协议 prompt、已有 agent 修复。
  - `.venv/bin/python tests/test_archive_room_phase_1_3.py`：通过。
  - `.venv/bin/python tests/test_project_execution.py`：通过，测试日志包含预期 Gateway 降级连接失败，最终结果为 `ok`。
  - 使用 `VO_PORT=8160 VO_WS_PORT=8161 ./start.sh` 真实启动后，`GET /api/archive-room` 返回 `profileVersion: 2026-06-20.2`，`/home/wo/.openclaw/workspace-archive-manager/AGENTS.md` 和 `SOUL.md` 文件头均包含 `archive-manager-profile-version: 2026-06-20.2`。
- 会议边界修正：2026-06-20T13:22:07+08:00 已将 `档案管理员` 从普通会议创建与会议请求确认的参与人选择中过滤；服务端同时拒绝将 `archive-manager` 作为普通会议参与者或主持人，避免绕过 UI。
- 会议边界验证：
  - `.venv/bin/python -m py_compile app/server.py`：通过。
  - `.venv/bin/python tests/test_archive_room_phase_4.py`：通过。
  - `.venv/bin/python tests/test_meeting_for_ai_phase1.py`：通过，覆盖 executable meeting 直接创建时拒绝 `archive-manager` 参与者/主持人。
  - `.venv/bin/python tests/test_meeting_for_ai_phase4.py`：通过，覆盖 meeting request 创建/确认时拒绝 `archive-manager`。
  - 使用 `VO_PORT=8160 VO_WS_PORT=8161 ./start.sh` 真实启动后，`POST /api/meetings/executable/create` 携带 `participants: ["main", "archive-manager"]` 返回 400 和 `archive_manager_not_meeting_participant`；`GET /agents-list` 仍返回 `archive-manager`，并带有 `systemRole: archive_manager`、`assignable: false`，说明主办公室可见性保留。

## 最终验收记录

- 确认项：done
- 确认时间：2026-06-20T13:31:14+08:00
- 用户确认摘要：用户回复“可以了，这个子需求可以验收了”，确认 Archive Room Phase 4 子需求验收通过并可归档完成。验收范围包含全局档案管理员生命周期、状态与控制、当前项目手动整理、主办公室可见、角色边界、prompt/profile 同步、普通任务/会议边界、Phase 1-3 回归和真实服务冒烟结果。
