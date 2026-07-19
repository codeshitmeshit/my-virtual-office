> English version: [CODEX_PROVIDER_ADAPTER.md](CODEX_PROVIDER_ADAPTER.md)

# Codex 提供者适配器

状态：实时桥接和项目执行提供者

Codex 适配器将一个本地 Codex 协作者作为一流的 Virtual Office 代理暴露，无需 OpenClaw 或 Hermes。

## 启动标志

- `VO_CODEX_ENABLED=1` 启用 Codex 框架。
- `VO_CODEX_AGENT_ID=local` 设置稳定的提供者 ID。office ID 变为 `codex-local`。
- `VO_CODEX_AGENT_NAME=Codex` 设置显示名称。
- `VO_CODEX_WORKSPACE=/path/to/repo` 设置可读写的工作区。
- `VO_CODEX_MODEL=<model>` 可选地覆盖 Codex 模型。
- `VO_CODEX_BIN=codex` 选择默认桥接使用的本地 Codex CLI。
- `VO_CODEX_REPLY_TEXT=<text>` 启用确定性回归回复。
- `VO_CODEX_BRIDGE_URL=<url>` 用外部管理的 HTTP 桥接覆盖本地桥接。

## 实时桥接行为

- 发现返回一个规范化的 `providerKind: "codex"` 代理。
- Virtual Office 默认启动并重用本地 `codex app-server` 进程。
- `/api/agent-platform-communications/send` 支持人类和代理发送者。
- `/api/codex/chat` 是人类聊天窗口路由。
- `/api/codex/activity` 返回当前 office 对话的相关轮次、推理、工具/文件、交互和终端事件。
- Office 的 `conversationId` 值被持久映射到 `VO_STATUS_DIR` 下的 Codex 线程 ID。
- 同一 office 对话在刷新和服务重启后恢复同一 Codex 线程。
- 一次只能运行一个轮次或上下文压缩操作；后续请求返回 `busy` 而非排队。
- 审批和用户输入请求默认以 `needs_human_intervention` 关闭失败。
- 当某个轮次启用交互模式时，`/api/codex/interaction` 可以回答待处理的审批/用户输入请求并继续原始轮次。
- `/api/codex/cancel` 请求取消映射到的 Codex 线程的当前活动轮次。
- 结果包括终端状态、Codex 线程/轮次 ID、持续时间和修改的文件路径。
- `/api/codex/compact` 压缩当前线程而不清除可见的 office 历史。
- `/api/codex/reset` 使映射失效，以便下一条消息启动新线程。
- `/api/codex/history` 读取某个对话的 office 拥有的通信历史。

## 项目执行

Codex 提供者引用受到项目功能的支持。基于 Codex 的任务执行接收所选项目工作区，并记录规范化的证据以供下游审查和用户验收。

项目执行支持：

- 项目级和任务级启动
- 单个任务启动和连续项目执行
- 工作区验证和脏工作区确认
- 系统管理的自动工作区和用户管理的手动工作区
- 独立的审查者路由
- 明确允许时的审查者跳过确认
- 取消活动任务执行
- 审查开始、用户验收、驳回和阻塞结果
- 更改文件的证据以及项目工作区下的 Markdown 工件发现
- 安全的行内 Markdown 工件读取，包含路径约束和大小限制

工作区控制：

- `VO_AUTO_PROJECT_WORKSPACE_ROOT` 设置 Virtual Office 创建托管项目工作区时使用的根目录。
- `VO_PROJECT_ROOTS` 可以限制手动项目工作区为允许列表中的实际路径。
- 托管工作区可随其项目删除；用户管理工作区永远不会因项目删除而被删除。

相关路由：

- `POST /api/projects/<projectId>/project-execution/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/cancel`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/review/start`
- `POST /api/projects/<projectId>/tasks/<taskId>/project-execution/accept`
- `GET /api/projects/<projectId>/artifacts`
- `GET /api/projects/<projectId>/artifacts/read?path=<relativePath>`

## 安全边界

- `VO_CODEX_SANDBOX` 支持 `read-only`、`workspace-write` 和 `danger-full-access`；前两种模式默认关闭网络，`workspace-write` 仅把配置的 workspace 作为可写根目录。
- `VO_CODEX_APPROVAL_POLICY` 支持 `untrusted`、`on-request` 和 `never`。`never` 不会自动批准请求，而是指示 Codex 不发起审批；受 sandbox 阻止的操作会直接失败。
- `danger-full-access` 与 `never` 的组合只应在受信任的开发机环境使用，因为 Codex 可以访问 workspace 之外的文件和网络。
- 当且仅当使用 `danger-full-access`、`never` 且未启用 VO 审批路由时，本地 bridge 会以 `codex --dangerously-bypass-approvals-and-sandbox app-server --stdio` 启动，并继续在 thread/turn 请求中显式传递同等策略。
- 启用 `VO_CODEX_ROUTE_APPROVALS_THROUGH_VO=true` 时，审批策略强制为 `untrusted`，以便请求能够在 Virtual Office 中处理。
- 默认的应用服务器传输是本地 stdio。不要在没有身份验证的情况下在非回环接口上暴露监听器。

## 外部桥接合约

当设置了 `VO_CODEX_BRIDGE_URL` 时，Virtual Office 将 JSON 发送到 `<url>/execute` 和 `<url>/compact`。桥接返回规范化的字段 `ok`、`status`、`reply`、`threadId`、`turnId`、`modifiedFiles`、`needsHumanIntervention` 以及可选的错误/时间字段。

## 兼容性与范围

`VO_CODEX_REPLY_TEXT` 模拟一个稳定的演示线程，以便可以在没有 Codex 身份验证的情况下测试聊天、历史、重置和压缩。

当前已知限制：

- 适配器仅暴露一个本地 Codex 协作者。
- 提供者中立的浏览器操作路由与 Codex 桥接分开，不是 Codex 特有的能力。
- `VO_CODEX_REPLY_TEXT` 用于确定性回归/演示模式，不执行实时工具执行。
