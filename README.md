# My Virtual Office 二开版

> 中文为主文档。英文辅助文档见 [README.en.md](README.en.md)。

My Virtual Office 二开版是一个本地优先的 AI Agent 可视化工作台。它基于原开源项目 [eliautobot/my-virtual-office](https://github.com/eliautobot/my-virtual-office) 二次开发，保留像素风办公室、Agent 状态可视化和浏览器内运行体验，并扩展为一个可以连接 OpenClaw、Hermes、Codex、Claude Code 等本地 Agent/CLI 的统一控制台。

感谢原项目作者和社区提供的基础实现。本仓库是在原项目之上的二次开发版本，不代表原项目官方发行版；原项目的商业授权、部署方式和功能说明不一定适用于当前二开版本。

![My Virtual Office](screenshot.png)

## 当前定位

这个项目现在更接近一个「本地 AI 团队控制台」：

- 用像素办公室展示 Agent 的在线、空闲、工作、会议等状态
- 在同一个界面里和 OpenClaw、Hermes、Codex、Claude Code 等 Agent 对话
- 让不同平台的 Agent 通过 Virtual Office 中转通信
- 把项目、任务、评审、验收和产物沉淀到项目看板
- 观察 Codex / Hermes / Claude Code 任务执行、推理、工具调用、审批、取消和上下文压缩
- 管理 Agent 工作区、技能库、会议、浏览器、飞书通知、短信和本机监控等能力

## 主要功能

### 像素办公室

- 浏览器中的实时像素风办公室画布
- Agent 行走、坐下、工作、空闲、会议和休息状态
- A* 路径寻路、碰撞规避、墙体遮挡
- 可编辑办公室布局、家具、地板、墙体、分区和标签
- Agent 外观、姓名、表情、部门、工位和角色配置
- 办公室宠物、动态天气、昼夜变化、电视和时钟等环境元素

### 多 Provider Agent

当前二开版将 Virtual Office 从 OpenClaw 单一可视化界面扩展为多 Provider 工作台：

- OpenClaw：保留原有网关、会话、模型、技能和状态路径
- Hermes：通过本地 Hermes CLI 发现 profile、发送消息、读取本地历史；可选走 Hermes native API run / SSE / approval 路径
- Codex：通过本地 Codex app-server harness 暴露为办公室 Agent，支持 native agent 发现和创建
- Claude Code：通过 `claude -p --output-format stream-json` 暴露为办公室 Agent，支持 native subagent 发现和创建
- 跨平台通信：`/api/agent-platform-communications/send`
- 统一 Agent 列表、状态、聊天气泡和可视化事件
- Provider-neutral services：用单一 run repository、event journal、coordinator、approval/conversation service 和只读 SSE transport 归一 Hermes、Codex、Claude Code 的后台行为

### Codex Live Bridge

启用 `VO_CODEX_ENABLED=1` 后，Virtual Office 会把本地 Codex 暴露为 `codex-local` Agent。

已支持：

- 本地 `codex app-server` live bridge
- 可选外部 bridge：`VO_CODEX_BRIDGE_URL`
- 聊天窗口调用：`POST /api/codex/chat`
- 活动流：`GET /api/codex/activity`
- 历史：`GET /api/codex/history`
- run 事件流：`GET /api/codex/runs/<runId>/events`
- 上下文压缩：`POST /api/codex/compact`
- 会话重置：`POST /api/codex/reset`
- 执行取消：`POST /api/codex/cancel`
- 审批/用户输入交互：`POST /api/codex/interaction`
- Codex app-server approval：命令执行、文件变更和权限请求会在聊天窗口显示 Approve / Cancel 卡片，也可通过 `/api/codex/approval/pending` 和 `/api/codex/approval/respond` 处理
- native agent 支持：可发现 `$CODEX_HOME/agents/*.toml`，也可从 Virtual Office 创建标准或自定义目录 agent
- 线程映射持久化，刷新和重启后可继续同一 office conversation

`VO_CODEX_REPLY_TEXT` 可用于确定性回归测试，不会触发真实 Codex 工具执行。

### Claude Code Provider

启用 `VO_CLAUDE_CODE_ENABLED=1` 后，Virtual Office 会把本地 Claude Code 暴露为 `claude-code-local` Agent。

已支持：

- 本地 `claude` CLI stream-json 协议
- 聊天窗口调用：`POST /api/claude-code/chat`
- run 事件流：`GET /api/claude-code/runs/<runId>/events`
- 历史：`GET /api/claude-code/history`
- 执行取消：`POST /api/claude-code/cancel`
- `--resume <session_id>` 会话续接
- tool_use、tool_result、assistant delta、usage 和完成状态归一为 Virtual Office 的聊天/事件形态
- 可发现 `$CLAUDE_CONFIG_DIR/agents/*.md` native subagents，并可从 Virtual Office 创建标准或自定义目录 agent

`VO_CLAUDE_CODE_REPLY_TEXT` 可用于确定性回归测试。

### 项目与任务执行

项目功能已经从普通看板扩展为可执行工作流：

- 项目、列、任务、评论、清单、标签、模板
- 自动创建或绑定项目工作区
- `VO_AUTO_PROJECT_WORKSPACE_ROOT` 可配置系统托管项目工作区根目录
- `VO_PROJECT_ROOTS` 可限制手动绑定工作区的允许根路径
- 工作区路径校验和 dirty workspace 确认
- 项目级启动和任务级启动
- 单任务执行和连续项目执行模式
- OpenClaw、Hermes、Codex、Claude Code provider ref 路由
- 执行 Agent 与独立 Reviewer 分离
- 缺少 Reviewer 时的显式跳过确认
- 执行取消、失败证据、阻塞状态
- Reviewer 评审、自动返工、最多返工次数控制
- 用户验收、拒绝、标记阻塞
- Markdown / text artifact 扫描、安全读取、源路径树形展示和删除
- 执行前 workspace 校验、执行中状态锁定、失败证据和 modified files 归档
- 任务执行时可发起阻塞型会议申请；会议完成前任务保持 blocked / needs meeting 状态
- 飞书卡片可处理关键验收动作：接受任务、要求返工、确认/拒绝会议申请

核心接口见 [docs/VIRTUAL_OFFICE_AGENT_TOOLS.md](docs/VIRTUAL_OFFICE_AGENT_TOOLS.md)。

服务端业务逻辑的渐进式拆分约定见 [docs/SERVICE_BOUNDARIES.md](docs/SERVICE_BOUNDARIES.md)。

### 会议系统

- 传统会议：创建、结束、历史记录
- 可执行 AI 会议：Agent 参与、轮次推进、暂停、恢复、取消
- 信息收集、讨论决策、任务协作三类会议
- 用户发起会议，选择参会 Agent、主持人、轮次上限、上下文传递模式和关联项目
- AI 发起会议申请，但必须由用户确认、编辑或拒绝后才能开始
- 会前上下文候选来自当前项目、当前任务、同项目相关任务和历史会议，只有用户选中的内容会进入会议快照
- 用户介入、补充上下文、议程调整、定向提问、仲裁、暂停/恢复、提前结束和主持人接管
- 忙碌 Agent 冲突检测、advisory 建议、等待、更换、强制加入二次确认和轻量稍后再试
- 参会前记录原工作快照，会议结束/取消/失败后尝试幂等恢复
- 任务协作会议可生成行动项草稿，用户确认后再创建项目任务
- 会议请求、质量门禁、紧急程度自动确认
- 高优先级项目会议可按规则自动确认
- 会议记录会写回项目任务，保留决策、风险、行动项、来源会议和应用时间
- 会议状态投影到办公室画布

Meeting for AI 的安全边界：

- 未确认的 AI 会议申请不会占用 Agent，也不会调用参会 Agent provider
- Advisory turn 只给建议，不会自动暂停任务、替换参会者或强制开会
- 同一个 Agent 同一时间只能参加一场可执行会议
- 会议行动项不会自动执行，转成项目任务前必须由用户确认

### 技能库和 Agent 工作区

- Skills Library：集中管理可复用 `SKILL.md`
- 将技能复制到指定 Agent 工作区
- Agent workspace 面板：概览、公告、任务、文件、技能、笔记、设置
- 本地文件和技能以 `VO_STATUS_DIR` / Agent workspace 为持久化来源

### 辅助面板

- Chat：支持 Markdown、附件、图片预览、语音输入入口、Provider 运行状态、Codex 推理摘要和 approval 卡片
- Chat history：切换 Agent 时隔离历史和 session 状态，避免不同 provider 的消息串线
- Browser Panel：显示共享浏览器/VNC 视图和当前 URL
- SMS Panel：Twilio 短信收发和人工接管
- PC Metrics：CPU、内存等本机性能监控
- API Usage：API 用量统计
- Models Panel：模型、Provider、Hermes native API、Codex approval policy、Claude Code 等配置
- Cron 页面：Agent 定时任务与项目定时任务管理入口

### 飞书通知和卡片动作

Virtual Office 支持通过飞书向人类协作者推送关键工作流通知，并接收卡片按钮操作：

- 支持飞书机器人 webhook 或应用凭证发送卡片
- 设置向导可配置 App ID、App Secret、Receive ID 类型和 Receive ID
- 后端可通过飞书长连接接收卡片 action callback
- 支持测试卡片发送和配置脱敏展示
- 项目任务需要人工验收、需要介入、执行完成、会议失败等关键状态会发送通知
- 飞书卡片动作会写入 `feishu-card-actions.jsonl`，并保持幂等处理
- 会议申请卡片支持同意并启动会议、拒绝会议
- 项目执行验收卡片支持接受任务或要求返工

### 项目定时任务

定时任务页面和项目详情页已经支持把全局 Cron 调度绑定到项目：

- 支持项目工作流定时启动和指定任务定时启动
- 支持 `cron`、`every`、`at` 三种 schedule
- Cron job 由 OpenClaw Gateway 管理，项目绑定关系保存在 Virtual Office
- 项目归档、项目暂停定时任务、已有任务运行中、目标任务缺失等情况会跳过派发并记录历史
- 已完成任务默认不会重复执行，除非任务开启 scheduled repeat
- 当所有目标任务都已完成且未开启 scheduled repeat 时，会自动停用对应项目 Cron，避免重复触发同一批已完成任务
- 派发历史和需要人工介入的告警会显示在项目面板

## 快速启动

> **部署边界：Virtual Office 主应用不支持 Docker 或 Docker Compose 部署，只支持在宿主机本地启动。仓库中唯一保留的 Docker 用途是可选的 Agent Browser 镜像。**

建议直接使用仓库内的 `start.sh` 启动。该脚本会加载本地配置并进入真实本地运行路径，避免误用回归测试或 demo 模式。

```bash
git clone https://github.com/eliautobot/my-virtual-office.git
cd my-virtual-office
chmod +x start.sh
./start.sh
```

启动后打开：

```text
http://localhost:8090/setup
```

常用入口：

- 主界面：`http://localhost:8090/`
- 设置向导：`http://localhost:8090/setup`
- 模型管理：`http://localhost:8090/models`
- 定时任务：`http://localhost:8090/cron.html`
- 健康检查：`http://localhost:8090/health`

查看启动脚本参数：

```bash
./start.sh --help
```

### 可选 Agent Browser 镜像

需要共享浏览器的 CDP 控制和实时画面时，可以单独启动 Agent Browser：

```bash
./start.sh --browser
```

它使用 [docker-compose.browser.yml](docker-compose.browser.yml)，只构建和运行 `agent-browser`，不会把 Virtual Office 主应用放进容器，也不代表 VO 支持 Docker 部署。默认入口：

- CDP：`http://127.0.0.1:9224`
- Viewer：`https://localhost:6901`
- 停止：`./start.sh --browser-stop`
- 日志：`./start.sh --browser-logs`

也可以不使用该镜像，直接把 `VO_CDP_URL` 和 `VO_VIEWER_URL` 指向已有的浏览器服务。

## 配置

推荐使用 `.env` 或 `vo-config.json` 配置。`start.sh` 会加载本地配置并使用仓库内 `data` 目录作为默认状态目录。

常用环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VO_PORT` | `8090` | HTTP 服务端口 |
| `VO_WS_PORT` | `8091` | WebSocket 代理端口 |
| `VO_WS_PATH` | `/ws` | 反向代理下的同源 WebSocket 路径 |
| `VO_STATUS_DIR` | `./data` | 本地状态、项目、技能、历史数据目录 |
| `VO_OFFICE_NAME` | `Virtual Office` | 办公室显示名称 |
| `VO_OPENCLAW_PATH` | `~/.openclaw` | OpenClaw home 路径 |
| `VO_GATEWAY_URL` | 自动探测 | OpenClaw Gateway WebSocket 地址 |
| `VO_GATEWAY_HTTP` | 自动探测 | OpenClaw Gateway HTTP 地址 |
| `VO_HERMES_ENABLED` | `true` | 是否发现 Hermes profiles |
| `VO_HERMES_HOME` | `~/.hermes` | Hermes home/profile 根目录 |
| `VO_HERMES_BIN` | `~/.local/bin/hermes` | Hermes CLI 路径 |
| `VO_HERMES_API_ENABLED` / `VO_HERMES_PREFER_API` | `false` | 是否优先使用 Hermes native API run / SSE / approval |
| `VO_HERMES_API_URL` | `http://127.0.0.1:8642` | Hermes native API 地址 |
| `VO_HERMES_API_KEY` | 空 | Hermes native API key |
| `VO_CODEX_ENABLED` | 未启用 | 是否启用 Codex harness |
| `VO_CODEX_HOME` | `~/.codex` | Codex 配置和 native agents 根目录 |
| `VO_CODEX_BIN` | `codex` | Codex CLI 路径 |
| `VO_CODEX_WORKSPACE` | 当前工作目录 | Codex 可读写 workspace |
| `VO_CODEX_WORKSPACE_ROOT` | `VO_STATUS_DIR/codex-agents` | Virtual Office 创建 Codex agent 的根目录 |
| `VO_CODEX_MAIN_WORKSPACE` | `VO_CODEX_WORKSPACE` | `codex-main` 和 native agents 使用的主 workspace |
| `VO_CODEX_MODEL` | 空 | Codex 模型覆盖 |
| `VO_CODEX_SANDBOX` | `workspace-write` | Codex sandbox 模式 |
| `VO_CODEX_APPROVAL_POLICY` | `on-request` | Codex approval policy |
| `VO_CODEX_ROUTE_APPROVALS_THROUGH_VO` | `false` | 是否强制使用 `untrusted` 并把 Codex 审批路由到 VO |
| `VO_CODEX_INCLUDE_MAIN` | `true` | 是否显示 `codex-main` |
| `VO_CODEX_INCLUDE_NATIVE_AGENTS` | `true` | 是否发现 `$CODEX_HOME/agents/*.toml` |
| `VO_CODEX_REGISTER_NATIVE_AGENTS` | `true` | 创建 VO Codex agent 时是否写入 native agent 配置 |
| `VO_CODEX_BRIDGE_URL` | 空 | 外部 Codex bridge 地址 |
| `VO_CODEX_REASONING_SUMMARY` | `concise` | Codex 推理摘要模式 |
| `VO_CLAUDE_CODE_ENABLED` | 未启用 | 是否启用 Claude Code provider |
| `VO_CLAUDE_CODE_HOME` | `~/.claude` | Claude Code 配置目录 |
| `VO_CLAUDE_CODE_BIN` | `claude` | Claude Code CLI 路径 |
| `VO_CLAUDE_CODE_WORKSPACE` | 当前工作目录 | Claude Code 可读写 workspace |
| `VO_CLAUDE_CODE_WORKSPACE_ROOT` | `VO_STATUS_DIR/claude-code-agents` | Virtual Office 创建 Claude Code agent 的根目录 |
| `VO_CLAUDE_CODE_MAIN_WORKSPACE` | `VO_CLAUDE_CODE_WORKSPACE` | `claude-code-main` 和 native subagents 使用的主 workspace |
| `VO_CLAUDE_CODE_MODEL` | 空 | Claude Code 模型覆盖 |
| `VO_CLAUDE_CODE_PERMISSION_MODE` | `acceptEdits` | Claude Code permission mode |
| `VO_CLAUDE_CODE_INCLUDE_MAIN` | `true` | 是否显示 `claude-code-main` |
| `VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS` | `true` | 是否发现 `$CLAUDE_CONFIG_DIR/agents/*.md` |
| `VO_CLAUDE_CODE_REGISTER_NATIVE_AGENTS` | `true` | 创建 VO Claude Code agent 时是否写入 native subagent 配置 |
| `VO_FEISHU_NOTIFICATION_ENABLED` | `true` | 是否启用飞书通知 |
| `VO_FEISHU_NOTIFICATION_WEBHOOK` | 空 | 飞书机器人 webhook，兼容旧配置 |
| `VO_FEISHU_APP_ID` | 空 | 飞书应用 App ID |
| `VO_FEISHU_APP_SECRET` | 空 | 飞书应用 App Secret |
| `VO_FEISHU_RECEIVE_ID_TYPE` | `chat_id` | 飞书消息接收 ID 类型 |
| `VO_FEISHU_RECEIVE_ID` | 空 | 飞书消息接收 ID |
| `VO_CODEX_FEISHU_APPROVAL_CARDS_ENABLED` | `true` | 是否把飞书来源的 Codex 安全审批发送为交互卡片 |
| `VO_CODEX_FEISHU_APPROVAL_WORKERS` | `2` | Codex 飞书审批后台投递并发 |
| `VO_CODEX_FEISHU_APPROVAL_QUEUE` | `16` | Codex 飞书审批有界投递队列容量 |
| `VO_CODEX_FEISHU_APPROVAL_DEADLINE_SEC` | `12` | Codex 飞书审批投递总 deadline（秒） |
| `VO_CHAT_SLASH_COMMANDS_ENABLED` | `false` | 启用 VO 聊天中的精确 `/new`、`/compact` 命令 |
| `VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED` | `false` | 在全局开关启用后，再启用飞书私聊和提及门禁群聊命令 |
| `VO_FEISHU_AUDIT_MAX_BYTES` | `5242880` | 飞书通知/卡片动作 JSONL 轮转阈值 |
| `VO_FEISHU_AUDIT_BACKUPS` | `3` | 飞书通知/卡片动作审计备份数 |
| `VO_BROWSER_PANEL` | `true` | 是否显示 Browser Panel |
| `VO_CDP_URL` | `http://127.0.0.1:9224` | 浏览器 CDP 地址 |
| `VO_VIEWER_URL` | `https://localhost:6901` | 浏览器可视化/VNC 地址 |
| `VO_AUTO_PROJECT_WORKSPACE_ROOT` | 空 | 自动创建项目工作区的根目录 |
| `VO_PROJECT_ROOTS` | 空 | 允许手动绑定的项目工作区根目录列表，按系统路径分隔符分隔 |
| `VO_MEETING_DECISION_WINDOW_SEC` | `20` | AI 会议冲突/紧急程度决策窗口 |
| `VO_MEETING_ADVISORY_TIMEOUT_SEC` | `45` | 会议 busy advisory 超时时间 |
| `VO_MEETING_PROVIDER_TIMEOUT_SEC` | `300` | 会议 provider 调用超时时间 |
| `VO_PC_METRICS_ENABLED` | `true` | 是否启用本机性能面板 |
| `VO_PC_METRICS_URL` | `http://127.0.0.1:8099` | 性能监控服务地址 |
| `VO_API_USAGE` | `false` | 是否启用 API usage 面板 |
| `VO_WEATHER_LOCATION` | 空 | 天气位置 |

更多示例见 [.env.example](.env.example)。

聊天命令的精确语法、Provider 能力、灰度与回滚说明见 [聊天斜杠命令运维指南](docs/CHAT_SLASH_COMMANDS.md)。

### Codex 权限配置

Virtual Office 会把下面两个配置同时传给 `codex app-server` 的 thread 和 turn；修改 `.env` 后需要重启 Virtual Office 才会作用于新启动的 Codex bridge。

- `VO_CODEX_SANDBOX=read-only`：只读文件系统，网络默认关闭。
- `VO_CODEX_SANDBOX=workspace-write`：允许写入当前 Codex workspace，网络默认关闭，是推荐的常规配置。
- `VO_CODEX_SANDBOX=danger-full-access`：不启用 Codex 文件系统和网络沙箱，适用于受信任的开发机环境；Codex 可访问 workspace 之外的文件并执行联网操作。
- `VO_CODEX_APPROVAL_POLICY=untrusted`：对不受信任的命令请求审批。
- `VO_CODEX_APPROVAL_POLICY=on-request`：Codex 判断需要越过当前限制时请求审批。
- `VO_CODEX_APPROVAL_POLICY=never`：Codex 不发起权限审批；若 sandbox 仍有限制，越界操作会直接失败。

需要在受信任开发机上完全放开时，可以组合使用：

```env
VO_CODEX_SANDBOX=danger-full-access
VO_CODEX_APPROVAL_POLICY=never
```

这个组合会让本地 bridge 使用 Codex 原生完整权限启动方式：

```bash
codex --dangerously-bypass-approvals-and-sandbox app-server --stdio
```

原生 flag 位于 `app-server` 子命令之前，同时 thread/turn 仍会收到 `danger-full-access` 和 `never`，确保新线程与恢复线程使用一致的权限策略。

如果同时启用 `VO_CODEX_ROUTE_APPROVALS_THROUGH_VO=true`，审批策略会强制设为 `untrusted`，以保证审批卡片能够路由到 Virtual Office；这时 `never` 不生效。未知配置值会安全回退为 `workspace-write` 和 `on-request`。

## 本地数据

主要持久化数据位于 `VO_STATUS_DIR`：

- 项目 Markdown 数据：`projects-md/`
- 旧项目 JSON：`projects.json`
- 技能库：`skills-library/`
- 跨平台通信历史：`agent-platform-communications.jsonl`
- Codex conversation/thread 映射和活动记录
- Claude Code / Hermes / provider run 历史和活动记录
- 项目定时任务绑定：`project-cron-bindings.json`
- 飞书卡片动作：`feishu-card-actions.jsonl`
- 会议、presence、workflow、workspace 相关状态

不要把包含密钥、聊天记录或工作区内容的本地数据公开发布。

## 安全边界

这是一个高权限本地控制台。它可能连接本机 CLI、读写项目工作区、控制 Agent、展示浏览器、发送短信和触发模型调用。

建议：

- 默认只在本机、局域网或 Tailscale 等私有网络中使用
- 不要直接暴露 `8090`、`8091`、OpenClaw Gateway 或浏览器 CDP 到公网
- 给可访问该服务的机器和账号配置强认证
- 谨慎选择 `VO_CODEX_WORKSPACE`、`VO_CLAUDE_CODE_WORKSPACE` 和项目 workspace
- 对 dirty workspace、跳过 reviewer、用户验收等确认保持人工判断
- 不要在公开日志或截图中泄露 `.env`、token、短信号码、飞书 App Secret、Receive ID 或私有聊天内容

## 测试

项目包含 Python 和 JavaScript 测试，覆盖 provider runtime、Codex bridge、Claude Code provider、Hermes native API、项目执行、会议、飞书通知、项目定时任务、国际化、浏览器 URL、前端小模块等。

常用测试示例：

```bash
npm test
.venv/bin/python tests/test_project_execution.py
.venv/bin/python tests/test_provider_app_server_runtime.py
.venv/bin/python tests/test_provider_execution_contract.py
.venv/bin/python tests/test_codex_bridge.py
.venv/bin/python tests/test_codex_runs_sse.py
.venv/bin/python tests/test_claude_code_provider.py
.venv/bin/python tests/test_claude_code_runs_sse.py
.venv/bin/python tests/test_hermes_server_native_api.py
.venv/bin/python tests/test_feishu_notifications.py
.venv/bin/python tests/test_meeting_for_ai_phase1.py
.venv/bin/python tests/test_meeting_for_ai_phase4.py
.venv/bin/python tests/test_meeting_for_ai_phase5.py
.venv/bin/python tests/test_meeting_for_ai_phase6.py
.venv/bin/python tests/test_meeting_request_blocks_task.py
.venv/bin/python tests/test_project_scheduled_cron_phase1.py
.venv/bin/python tests/test_project_scheduled_cron_phase2_3.py
.venv/bin/python tests/test_project_scheduled_cron_phase4.py
.venv/bin/python tests/test_project_cron_idempotent_defect.py
```

实际可用命令取决于你的本地虚拟环境和依赖安装方式。

## 文档索引

- Agent 工具索引：[docs/VIRTUAL_OFFICE_AGENT_TOOLS.md](docs/VIRTUAL_OFFICE_AGENT_TOOLS.md)
- VO 内 Agent 使用手册：[docs/VO_AGENT_USAGE_GUIDE.md](docs/VO_AGENT_USAGE_GUIDE.md)
- 跨平台通信：[docs/AGENT_PLATFORM_COMMUNICATIONS.md](docs/AGENT_PLATFORM_COMMUNICATIONS.md)
- Codex Provider：[docs/CODEX_PROVIDER_ADAPTER.md](docs/CODEX_PROVIDER_ADAPTER.md)
- Codex 飞书审批卡片运维：[docs/CODEX_FEISHU_APPROVALS.md](docs/CODEX_FEISHU_APPROVALS.md)
- Hermes Provider：[docs/HERMES_PROVIDER_ADAPTER.md](docs/HERMES_PROVIDER_ADAPTER.md)
- 多 Provider 架构草案：[docs/UNIVERSAL-AGENT-HARNESS-SPEC.md](docs/UNIVERSAL-AGENT-HARNESS-SPEC.md)
- Provider 服务架构与运维：[docs/PROVIDER_SERVICE_ARCHITECTURE.md](docs/PROVIDER_SERVICE_ARCHITECTURE.md)
- Project Service 边界与开发约束：[docs/SERVICE_BOUNDARIES.md](docs/SERVICE_BOUNDARIES.md)
- 技能库：[docs/SKILLS-LIBRARY-SPEC.md](docs/SKILLS-LIBRARY-SPEC.md)
- 多聊天窗口架构：[docs/MULTI-CHAT-ARCHITECTURE.md](docs/MULTI-CHAT-ARCHITECTURE.md)
- 历史设计记录：[docs/design-history/](docs/design-history/)

## 更新

```bash
git pull
./start.sh
```

如果已有服务在运行，先停止旧进程再启动。数据默认保存在 `VO_STATUS_DIR`，通常不会因为代码更新而丢失。

## 致谢与版权说明

本项目是基于原开源项目 [eliautobot/my-virtual-office](https://github.com/eliautobot/my-virtual-office) 的二次开发版本。感谢原作者提供的像素办公室、Agent 可视化和 Web 应用基础。

请注意：

- 本仓库不是原项目官方发行版
- 本仓库中的新增功能、文档和本地集成由二开版本维护
- 上游项目的商业授权和线上产品说明不自动适用于本仓库
- 原项目和本项目的授权信息请以仓库中的 [LICENSE](LICENSE) 以及各依赖/资源文件为准

## License

GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`).

Virtual Office remains open source. You may use, modify, host, and
redistribute it under the AGPL. If you modify the app and make it available
to users over a network, you must offer those users the corresponding source
code for your modified version.

Paid license keys unlock the hosted/product feature set and support the
official distribution. Commercial licensing is available separately for
organizations that need terms outside the AGPL.
