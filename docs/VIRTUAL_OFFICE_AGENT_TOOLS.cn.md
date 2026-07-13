> English version: [VIRTUAL_OFFICE_AGENT_TOOLS.md](VIRTUAL_OFFICE_AGENT_TOOLS.md)

# 虚拟办公室代理工具

状态：标准代理可用工具索引  
范围：我的虚拟办公室产品

## 目的

本文档是代理可通过我的虚拟办公室使用的工具的组织索引。它避免了重复零散的指令，并引导所有平台指向相同的办公室自有界面。

配套架构文档为 `docs/UNIVERSAL-AGENT-HARNESS-SPEC.md`。

有关包含示例、参数和安全规则的详细代理操作手册，请参阅 `docs/VO_AGENT_USAGE_GUIDE.md`。

## 内置技能

虚拟办公室将这些技能播种到技能库中，使代理无需自定义平台代码即可学习如何使用办公室工具：

- `AgentPlatform-to-AgentPlatform_Communications`
- `VirtualOffice-Presence-and-Status`
- `VirtualOffice-Browser-Control`
- `VirtualOffice-Meetings`
- `VirtualOffice-Projects-and-Tasks`

技能库端点：

- `GET /api/skills-library`
- `POST /api/skills-library/apply`

跨平台通信的原始技能也暴露在：

- `GET /api/agent-platform-communications/skill`

## 工具界面

### 代理平台

当办公室需要在已连接的平台上创建或移除代理时使用。

- `GET /api/agent-platforms`
- `POST /api/agent/create`
- `DELETE /api/agent/delete`

`POST /api/agent/create` 接受 `platform: "openclaw"`、`platform: "hermes"`、`platform: "codex"` 或 `platform: "claude-code"`。OpenClaw 创建通过 Gateway `agents.create` / `agents.files.set` 进行，以便代理立即可运行，且文件归 OpenClaw 用户所有。Hermes 创建将一个办公室代理映射到一个 Hermes 配置文件，并使用 `hermes profile create/delete`。Codex 创建将一个办公室代理映射到一个 Codex 工作区，写入 `AGENTS.md` 以及 `.codex/agents/<profile>.toml`，并通过 Codex 的原生应用服务器 JSON-RPC 协议进行聊天。Claude Code 创建将一个办公室代理映射到一个 Claude Code 工作区，写入 `AGENTS.md`、`CLAUDE.md` 和 `.claude/agents/<profile>.md`，并通过 Claude Code 的原生 `stream-json` CLI 协议进行聊天。

Codex 创建支持两种位置模式：

- `codexCreationMode: "standard"`：在已配置的 `codex.workspaceRoot` 下创建，并在启用原生注册时注册 `$CODEX_HOME/agents/<profile>.toml`。
- `codexCreationMode: "custom"` 搭配 `codexCustomDirectory`：在 `<codexCustomDirectory>/<profile>` 下创建，并写入项目本地 `.codex/agents/<profile>.toml`。虚拟办公室在 `codex.workspaceRoot` 下存储注册条目，以便自定义代理保持可发现。

Codex 发现还会读取标准的 `$CODEX_HOME/agents/*.toml` 自定义代理目录，并为 Codex 的默认主代理包含一个合成的 `codex-main` 条目。

Codex 应用服务器审批请求会在回合运行期间通过聊天历史呈现。Web 聊天会渲染待处理的命令、文件更改和权限审批卡片，并带有批准/取消控件。集成还可以轮询 `GET /api/codex/approval/pending?agentId=<id>`，并使用 `POST /api/codex/approval/respond` 响应活动的回调，传入 `approval_id` 和 `choice: "approve"` 或 `"cancel"`。

Claude Code 创建支持两种位置模式：

- `claudeCodeCreationMode: "standard"`：在已配置的 `claudeCode.workspaceRoot` 下创建，并在启用原生注册时注册 `$CLAUDE_CONFIG_DIR/agents/<profile>.md`。
- `claudeCodeCreationMode: "custom"` 搭配 `claudeCodeCustomDirectory`：在 `<claudeCodeCustomDirectory>/<profile>` 下创建，并写入项目本地 `.claude/agents/<profile>.md`。虚拟办公室在 `claudeCode.workspaceRoot` 下存储注册条目，以便自定义代理保持可发现。

Claude Code 发现还会读取原生的 `$CLAUDE_CONFIG_DIR/agents/*.md` 子代理，并为 Claude Code 的默认主代理包含一个合成的 `claude-code-main` 条目。

Claude Code 聊天使用 `claude -p --output-format stream-json --include-partial-messages`，并在可用时使用 `--resume <session_id>`。适配器将助手增量、`tool_use` 块、`tool_result` 块、使用量元数据、运行完成和中断转换为与 Hermes 和 Codex 相同的虚拟办公室聊天/事件形状。

Codex 配置是与产品无关的：

- `VO_CODEX_BIN`：Codex CLI 可执行文件，默认为 `PATH` 上的 `codex`
- `VO_CODEX_HOME`：此部署的 Codex 认证/配置主目录，Docker 中默认为 `VO_STATUS_DIR/codex-home`
- `VO_CODEX_WORKSPACE_ROOT`：办公室创建的 Codex 代理工作区
- `VO_CODEX_MAIN_WORKSPACE`：`codex-main` 和原生自定义代理使用的工作区
- `VO_CODEX_INCLUDE_MAIN`：包含 Codex 的默认主代理，默认启用
- `VO_CODEX_INCLUDE_NATIVE_AGENTS`：读取 `$CODEX_HOME/agents/*.toml`，默认启用
- `VO_CODEX_REGISTER_NATIVE_AGENTS`：创建 VO Codex 代理时写入 `$CODEX_HOME/agents/<profile>.toml`，默认启用
- `VO_CODEX_PREFER_APP_SERVER`：默认启用原生应用服务器集成
- `VO_CODEX_SANDBOX`：Codex 沙箱模式，Docker 示例默认为 `danger-full-access`，因为 bubblewrap 沙箱通常需要额外的容器权限
- `VO_CODEX_APPROVAL_POLICY`：Codex 审批策略，默认 `never`，以便无人值守的办公室运行不会因审批提示而挂起

Claude Code 配置是与产品无关的：

- `VO_CLAUDE_CODE_BIN`：Claude Code CLI 可执行文件，默认为 `PATH` 上的 `claude`
- `VO_CLAUDE_CODE_HOME`：此部署的 Claude 配置/认证目录
- `VO_CLAUDE_CODE_WORKSPACE_ROOT`：办公室创建的 Claude Code 代理工作区
- `VO_CLAUDE_CODE_MAIN_WORKSPACE`：`claude-code-main` 和原生子代理使用的工作区
- `VO_CLAUDE_CODE_MODEL`：可选的默认 Claude Code 模型
- `VO_CLAUDE_CODE_PERMISSION_MODE`：Claude Code 权限模式，默认为 `acceptEdits`
- `VO_CLAUDE_CODE_INCLUDE_MAIN`：包含 Claude Code 的默认主代理，默认启用
- `VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS`：读取 `$CLAUDE_CONFIG_DIR/agents/*.md`，默认启用
- `VO_CLAUDE_CODE_REGISTER_NATIVE_AGENTS`：创建标准 VO Claude Code 代理时写入 `$CLAUDE_CONFIG_DIR/agents/<profile>.md`，默认启用

切勿将主机用户名、个人认证路径或开发者的本地容器布局硬编码到 Codex 或 Claude Code 产品支持中。

Codex 是一种可选择加入的协作工具，而非创建的代理类型。在启动时使用 `VO_CODEX_ENABLED=1` 启用它；它会显示为一个可见的办公室代理，并通过相同的通信层接收消息。`VO_CODEX_REPLY_TEXT=<text>` 可用于确定性本地回归测试，直到配置了实时 Codex 桥接。

### AgentPlatform-to-AgentPlatform 通信

当代理需要跨提供商通信且该交换应在虚拟办公室中可见时使用。

- `POST /api/agent-platform-communications/send`
- `GET /api/agent-platform-communications/history`

事件存储在：

- `VO_STATUS_DIR/agent-platform-communications.jsonl`

这些事件会合并到 `/agent-chat` 中，因此聊天气泡可以显示跨平台交互。

当前支持的路由目标：

- OpenClaw 代理
- Hermes 配置文件
- Codex 协作代理（当 `VO_CODEX_ENABLED=1` 时）

### 状态与在线状态

虚拟办公室从网关/会话活动推导实时在线状态。当外部适配器或代理需要设置无法自动推断的显式可见状态时，可使用以下端点。

- `GET /api/presence`
- `GET /status`
- `POST /api/presence/<agentId>`

允许的常见状态：

- `working`
- `idle`
- `break`
- `meeting`

### 浏览器控制

当前安全的只读/状态端点：

- `GET /browser-status`
- `GET /browser-tabs`
- `GET /browser-controller`

重要提示：代理不应直接使用原始 Kasm/CDP 凭据。在向非 OpenClaw 代理授予直接浏览器控制权之前，应添加一个与提供者无关的浏览器操作 API。

### 会议

- `GET /api/meetings/active`
- `GET /api/meetings/history`
- `POST /api/meetings/create`
- `POST /api/meetings/end`
- `POST /api/meetings/end-all`

会议应始终以总结/决议/行动项结束。

AI 可执行会议路由：

- `POST /api/meetings/executable/create`
- `GET /api/meetings/executable/<meetingId>`
- `GET /api/meetings/executable/<meetingId>/events?afterSeq=<seq>`
- `POST /api/meetings/executable/<meetingId>/run`
- `POST /api/meetings/executable/<meetingId>/transition`
- `POST /api/meetings/executable/<meetingId>/intervention`
- `POST /api/meetings/executable/<meetingId>/agenda-change`
- `POST /api/meetings/executable/<meetingId>/targeted-question`
- `POST /api/meetings/executable/<meetingId>/arbitration`
- `POST /api/meetings/executable/<meetingId>/moderator-takeover`
- `POST /api/meetings/executable/<meetingId>/conflict`
- `POST /api/meetings/executable/<meetingId>/action-items/<actionItemId>`
- `GET /api/meetings/executable/reconcile`
支持的会议类型包括信息收集、决策讨论和任务协作。可执行的会议将参与者、阶段、轮次状态、转录事件、选定的上下文快照、结构化结果、冲突状态以及行动项草稿持久化存储在办公会议存储中。

AI 发起的会议请求路由：

- `GET /api/meetings/requests`
- `GET /api/meetings/requests/<requestId>`
- `POST /api/meetings/requests/<requestId>/confirm`
- `POST /api/meetings/requests/<requestId>/reject`
- `GET /api/projects/<projectId>/tasks/<taskId>/meeting-requests`
- `POST /api/projects/<projectId>/tasks/<taskId>/meeting-requests`

会议请求用于解决项目-任务协作障碍。有效的请求必须说明会议目标、预期结果、请求者无法独立完成的原因、建议的参与者以及建议的会议类型。待处理的请求不会预留参与者或调用会议提供者；只有用户确认的请求才会成为可执行的会议。

冲突处理使用 `POST /api/meetings/executable/<meetingId>/conflict`，支持的操作包括 `wait`、`reserve`、`replace`、`force_join`、`cancel_conflict` 和 `refresh`。中/高风险冲突可能包含忙碌代理的建议推荐、预计可用时间、中断风险以及恢复备注。建议输出为只读；用户或调用者仍需选择解决方案。

任务协作会议结果可以暴露行动项草稿。`POST /api/meetings/executable/<meetingId>/action-items/<actionItemId>` 支持用户控制的草稿更新、拒绝、仅会议保留以及挂载到已有项目任务。已绑定会议默认使用其来源任务；未绑定会议必须提供已有项目/任务目标。确认具有幂等性，不会新建看板任务，而是在目标任务上保存一条去重的 `meetingActionItems` 记录及来源会议/行动项元数据。

### 项目与任务

- `GET /api/projects`
- `GET /api/projects/<projectId>`
- `POST /api/projects`
- `POST /api/projects/<projectId>/tasks`
- `PUT /api/projects/<projectId>/tasks/<taskId>`
- `GET /api/projects/<projectId>/workflow/status`
- `POST /api/projects/<projectId>/workflow/start`
- `POST /api/projects/<projectId>/workflow/stop`
- `GET /api/projects/scores`

使用这些端点来处理属于看板的持久性工作。

项目执行端点可用于将看板工作分配给支持提供者的代理，并跟踪审查/接受状态：

- `POST /api/projects/<projectId>/project-execution/workspace/validate`
- `POST /api/projects/<projectId>/project-execution/start`
- `GET /api/projects/<projectId>/project-execution/status`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/cancel`
- `GET /api/projects/<projectId>/tasks/<taskId>/project-execution/status`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/review/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/accept`
- `GET /api/projects/<projectId>/artifacts`
- `GET /api/projects/<projectId>/artifacts/read?path=<relativePath>`

项目执行目前支持 OpenClaw、Hermes 和 Codex 提供者引用、独立的审查者路由、脏工作区确认、跳过审查者确认、取消、接受/拒绝/阻止以及 Markdown 制品发现。

项目绑定的定时 cron 端点将 Gateway cron 调度器连接到项目执行：

- `GET /api/projects/scheduled-cron`
- `GET /api/projects/<projectId>/scheduled-cron`
- `POST /api/projects/<projectId>/scheduled-cron`
- `PUT /api/projects/<projectId>/scheduled-cron/<cronId>`
- `DELETE /api/projects/<projectId>/scheduled-cron/<cronId>`
- `POST /api/projects/<projectId>/scheduled-cron/<cronId>/run`

Virtual Office 拥有 `VO_STATUS_DIR/project-cron-bindings.json` 中的项目绑定元数据；OpenClaw Gateway 拥有底层 cron 作业。支持的目标是 `projectWorkflow` 和 `projectTask`。支持的调度方式是 `cron`、`every` 和一次性 `at`。

当项目已归档、项目 cron 已暂停、另一个任务处于活动状态、目标任务缺失、已完成的任务未启用定时重复，或者需要脏工作区/缺少审查者确认时，调度可能跳过执行而不启动。这些结果记录在项目定时 cron 历史中，并在需要人工干预时作为项目警报显示。

### Codex 管理工具

当 `VO_CODEX_ENABLED=1` 时，Codex 管理工具作为办公代理暴露，可以通过聊天和项目执行两种方式使用。

- `GET /api/codex/test`
- `POST /api/codex/chat`
- `GET /api/codex/activity`
- `GET /api/codex/history`
- `POST /api/codex/interaction`
- `POST /api/codex/cancel`
- `POST /api/codex/compact`
- `POST /api/codex/reset`

实时桥接默认使用本地的 `codex app-server`，当配置了 `VO_CODEX_BRIDGE_URL` 时，则使用外部桥接。`VO_CODEX_REPLY_TEXT=<text>` 仍可用于确定性的本地回归测试。

## 组织规则

- 将此文件作为规范索引。
- 使用技能文件作为简洁的代理指令。
- 使用提供者适配器文档获取实现细节。
- 不要将通用的浏览器自动化技能复制为 Virtual Office 浏览器技能。`agent-browser` 是通用的；`VirtualOffice-Browser-Control` 专门用于办公拥有的浏览器界面。
- 未来的工具应在此处添加一个章节，并且仅当代理需要直接指令时才添加一个内置技能。

## 当前缺口

- 提供者无关的浏览器操作端点尚未实现。
- 文件/上传工具技能尚未添加；仅在预期的面向代理的文件端点最终确定后再添加。
- 日历/调度器技能尚未添加；仅当 Virtual Office 拥有这些端点而不是委托给 OpenClaw/提供者工具时，才添加。
