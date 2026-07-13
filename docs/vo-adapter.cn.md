> English version: [vo-adapter.md](vo-adapter.md)

# 虚拟办公提供商适配器指南

状态：针对新 CLI/运行时提供商的实现指南

## 目标

本指南说明了新的 CLI 工具或本地代理运行时应如何与“我的虚拟办公”集成，成为一流的提供商。

核心思想是：虚拟办公不应关心提供商底层是 CLI 进程、本地应用服务器、原生 HTTP API、WebSocket 网关还是外部桥接。提供商适配器负责这些细节，并向办公系统暴露标准化的契约。

## 心智模型

一个完整的集成包含三个层次：

1. 提供商运行时桥接

   这是提供商特定的执行层。

   示例：

   - Codex：本地 `codex app-server --stdio`，或通过 `VO_CODEX_BRIDGE_URL` 的外部 HTTP 桥接。
   - Claude Code：本地 `claude` CLI 工具，使用流式 JSON 输出。
   - Hermes：Hermes CLI 回退或原生 API run/event 路由。

2. 虚拟办公提供商适配器

   这是位于 `app/providers/` 下的 Python 适配器，以及 `app/server.py` 中的服务端处理函数。它将提供商特定的行为转换为标准化的办公代理发现、聊天/运行结果、状态、历史记录以及可选的事件流。

3. 虚拟办公通信接口

   这些是办公系统拥有的 API，例如：

   - `POST /api/agent-platform-communications/send`
   - `GET /api/agent-platform-communications/history`
   - 提供商特定的聊天/运行路由
   - 项目执行和可执行会议调用路径

如果适配器实现了标准化的契约，其他办公功能就可以将消息路由给它，而无需了解运行时内部细节。

## 集成级别

### 级别 1：可见代理与阻塞式聊天

这是最低限度的有用集成。

提供商必须支持：

- 作为一个或多个办公代理被发现
- 稳定的 `providerKind`
- 稳定的办公代理 ID
- 阻塞式消息执行
- 标准化的结果字段
- 办公系统拥有的请求/回复历史
- 调用运行期间的可见存在状态

达到此级别后，提供商可参与：

- 聊天窗口消息
- AgentPlatform 到 AgentPlatform 的通信
- 基本的 AI 会议轮次
- 基本的项目执行调用（如果工作区行为足够安全）

### 级别 2：后台运行与进度事件

当提供商调用需要时间或可以产生有用的中间状态时，添加此级别。

提供商应支持：

- 运行启动端点
- 服务端工作进程或异步任务
- 流式事件标准化
- 进度/历史消息
- 终止运行状态
- 取消

Codex、Claude Code 和 Hermes 后台运行统一由 `ProviderRunCoordinator` 协调，使用单一 run repository 和 event journal；UI 流式传输由只读的 `ProviderSSETransport` 提供。

### 级别 3：完整办公集成

添加此级别以实现与一流提供商的完全对等。

提供商应支持：

- 审批或人工输入
- 取消/停止
- 会话或线程持久化
- 上下文重置/压缩（如果运行时支持）
- 修改文件的证据
- 令牌/工具/推理元数据（如果可用）
- 工作区选择
- 项目执行证据
- 安全工件发现
- 确定性测试模式

## 提供商代理形状

发现应返回具有以下形状的办公代理字典：

```json
{
  "id": "provider-profile",
  "statusKey": "provider-profile",
  "providerKind": "example",
  "providerType": "cli",
  "providerAgentId": "profile",
  "profile": "profile",
  "name": "Example Agent",
  "emoji": "🤖",
  "role": "Example Provider Agent",
  "model": "optional-model",
  "workspace": "/path/to/workspace",
  "lastActiveAt": 0,
  "capabilities": ["chat", "runs", "status", "sessions"]
}
```

必填字段：

- `id`：稳定的办公 ID。使用提供商前缀，例如 `example-default`。
- `statusKey`：用于存在/状态渲染的键。通常与 `id` 相同。
- `providerKind`：小写提供商键，用于路由。
- `providerType`：实现类，如 `cli`、`api`、`gateway`、`app-server-bridge` 或 `harness`。
- `providerAgentId` 或 `profile`：原生提供商标识。
- `name`：显示名称。

推荐字段：

- `emoji`
- `role`
- `model`
- `workspace`
- `lastActiveAt`
- `capabilities`

## 提供商标类契约

在 `app/providers/<provider>.py` 下创建适配器。

类应大致如下：

```python
class ExampleProvider:
    provider_kind = "example"
    provider_type = "cli"

    def __init__(self, enabled=False, binary=None, home_path=None, workspace=None, **opts):
        ...

    def is_available(self) -> bool:
        ...

    def discover_agents(self) -> list[dict]:
        ...

    def test(self) -> dict:
        ...

    def send_chat_message(
        self,
        message: str,
        conversation_id: str = "",
        session_id: str | None = None,
        timeout_sec: int | None = None,
        on_progress=None,
    ) -> dict:
        ...

    def cancel(self, session_id: str = "", run_id: str = "") -> dict:
        ...
```

仅 `discover_agents()`、`test()` 和 `send_chat_message()` 是级别 1 必需的。其他是可选的，但推荐用于完整集成。

## 标准化结果契约

每次提供商调用都应返回一个可传递给 `normalize_provider_result()` 的字典。

最小成功结果：

```json
{
  "ok": true,
  "status": "completed",
  "reply": "final answer",
  "conversationId": "office-conversation",
  "sessionId": "native-session-or-thread",
  "runId": "native-run-or-turn",
  "modifiedFiles": [],
  "tools": [],
  "thinking": "",
  "tokenUsage": {},
  "providerMetadata": {}
}
```

最小失败结果：

```json
{
  "ok": false,
  "status": "execution_failed",
  "error": "human readable error",
  "errorCode": "optional_machine_code",
  "reply": "",
  "needsHumanIntervention": false
}
```

常见终止状态：

- `completed`
- `cancelled`
- `timeout`
- `busy`
- `disabled`
- `provider_unavailable`
- `bridge_unavailable`
- `needs_human_intervention`
- `invalid_request`
- `execution_failed`

使用 `provider_execution.py` 中的 `provider_http_status()` 将提供商状态映射到 HTTP 状态。

## 服务器集成检查清单

### 1. 配置

在 `app/server.py` 的 `_load_vo_config()` 中添加配置加载。

优先使用环境变量加上可选的 `vo-config.json` 字段：

```text
VO_EXAMPLE_ENABLED=1
VO_EXAMPLE_HOME=~/.example
VO_EXAMPLE_BIN=example
VO_EXAMPLE_WORKSPACE=/path/to/workspace
VO_EXAMPLE_TIMEOUT_SEC=600
VO_EXAMPLE_REPLY_TEXT=fixture reply
```

强烈建议为确定性测试配置 `VO_EXAMPLE_REPLY_TEXT`。

### 2. 发现

在 `app/discovery.py` 中添加发现函数，或在 `server.py` 中扩展提供商特定的发现路径。

提供商应可在以下位置可见：

- `GET /agents-list`
- `GET /api/agent-platforms`
- 添加默认存在状态后的 `/status`

### 3. 提供商查找

在 `server.py` 中添加类似于现有提供商辅助函数的辅助函数：

- `_get_example_agent(agent_key)`
- `_example_provider_from_config()`
- `_handle_example_test(body=None)`

### 4. 聊天处理器

添加阻塞式聊天处理器：

```python
def _handle_example_chat(body):
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or "example-default"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    ...
    result = provider.send_chat_message(
        message,
        conversation_id=conversation_id,
        session_id=current_session_id,
        timeout_sec=timeout,
    )
    normalized = normalize_provider_result(
        "example",
        agent,
        result,
        conversation_id=conversation_id,
        session_id=result.get("sessionId", ""),
        run_id=result.get("runId", ""),
        modified_files=result.get("modifiedFiles") or [],
    )
    normalized["_status"] = provider_http_status(normalized)
    return normalized
```

处理器应：

- 验证 `message`
- 验证目标代理
- 如果相关，应用归档/防护逻辑
- 运行时将存在状态设为 `working`
- 如果提供商需要，持久化提供商可见的历史记录
- 标准化结果
- 将存在状态恢复为 `idle` 或 `offline`

### 5. 路由注册

在 `OfficeHandler` 中添加 HTTP 路由：

- `POST /api/example/chat`
- `POST /api/example/runs`（如果支持后台运行）
- `GET /api/example/runs/<runId>/events`（如果支持 SSE）
- `POST /api/example/runs/<runId>/stop` 或 `POST /api/example/cancel`
- `POST /api/example/reset`（如果会话可重置）
- `GET /api/example/history`（如果暴露办公系统拥有的历史记录）
- `POST /api/example/test`

### 6. AgentPlatform 通信路由

在 `_handle_agent_platform_comm_send()` 中添加分支：

```python
elif str(to_ref.get("providerKind") or "").lower() == "example":
    provider_result = _handle_example_chat({
        "agentId": to_ref["id"],
        "message": target_prompt,
        "timeoutSec": timeout,
        "conversationId": conversation_id,
        "fromType": "human" if is_human_source else "agent",
    })
    reply = provider_result.get("reply") or provider_result.get("error") or ""
    ok = bool(provider_result.get("ok"))
```
这就是其他提供商通过以下方式与新提供商通信的机制：

```text
POST /api/agent-platform-communications/send
```

### 7. 项目执行路由

如果 provider 可以在项目工作区中安全运行，则将其添加到项目执行（Project Execution）provider 调用路径中。

provider 必须支持：

- 每个任务的工作区覆盖
- 超时
- 尽可能收集修改过的文件
- 尽可能取消
- 清除终端状态
- 除非显式设计，否则不在所选工作区之外写入

Project Execution 应调用相同的标准化 chat/run 处理器，而不是单独的私有实现。

### 8. 会议路由

将 provider 添加到 `_meeting_call_provider()`，以便 Executable Meeting 可以将其作为参与者调用。

会议调用路径需要：

- `agentId`
- `message`
- `conversationId = meeting:<id>:participant:<agent>`
- 超时
- 标准化的 `reply`

### 9. 在线状态

使用现有的在线状态辅助函数，以便办公用户可以看到活动。

最低要求：

- 通话进行时设为“工作中”
- 成功后返回“空闲”
- 失败后返回“离线”或“空闲”并附带错误元数据

如果运行时发出原生生命周期事件，将其映射到 provider 事件：

- `run.started`
- `message.delta`
- `reasoning.available`
- `tool.started`
- `tool.completed`
- `approval.request`
- `run.completed`
- `run.failed`
- `run.cancelled`

### 10. 历史记录

有两个历史范围：

1. 办公通信历史

   存储在：

   ```text
   VO_STATUS_DIR/agent-platform-communications.jsonl
   ```

   这由 Virtual Office 拥有，并为可见的跨提供商消息提供支持。

2. Provider 原生历史

   可选。仅存储 provider 适配器恢复会话所需的内容。除非 provider 的公共 API 明确支持，否则避免读取或暴露私有的原始 provider 数据。

## 后台运行与 SSE 契约

如果 provider 支持流式输出，请注册 capability adapter，并通过 `ProviderRunCoordinator` 和 `ProviderSSETransport` 接入；不要创建第二套 run/event authority。

推荐的事件名称：

- `run.started`
- `message.delta`
- `reasoning.available`
- `tool.started`
- `tool.completed`
- `tool.failed`
- `approval.request`
- `run.completed`
- `run.failed`
- `run.cancelled`

推荐的运行开始响应：

```json
{
  "ok": true,
  "runId": "example-...",
  "providerPath": "example-cli",
  "agent": {
    "id": "example-default",
    "name": "Example",
    "providerKind": "example",
    "profile": "default"
  }
}
```

推荐的 SSE 负载字段：

```json
{
  "runId": "example-...",
  "agentId": "example-default",
  "conversationId": "thread",
  "sessionId": "native-session",
  "runNativeId": "native-run",
  "status": "running",
  "text": "delta",
  "reply": "final reply",
  "error": "",
  "modifiedFiles": [],
  "needsHumanIntervention": false,
  "providerPath": "example-cli"
}
```

## 审批与人工输入

审批和人工输入请求必须默认为失败关闭，除非用户明确响应。

推荐行为：

- 将待审批标准化为 `needsHumanIntervention: true`。
- 提供足够的元数据供 UI 显示：标题、描述、选项、操作 ID、交互 ID。
- 提供响应端点，例如：

  ```text
  POST /api/example/interaction
  POST /api/example/approval/respond
  ```

- 决不要自动批准文件写入、shell 命令、外部网络访问或凭据使用。

## 取消

如果 provider 有长时间运行的调用，请实现取消功能。

推荐行为：

- 按 `agentId + conversationId` 存储活动操作。
- 当第二个操作会冲突时返回 `busy`。
- 提供停止/取消路由。
- 当 provider 确认取消后，将终端状态标记为 `cancelled`。
- 如果取消是尽力而为的，在标准化结果中明确报告这一点。

## 工作区与文件安全

对于可以编辑文件的 provider：

- 接受每个调用的工作区覆盖
- 使用 `realpath` 解析工作区路径
- 限制写入所选工作区
- 从不隐式删除用户管理的工作区
- 尽可能收集修改过的文件路径
- 返回修改过的文件路径为相对路径或显示安全的路径
- 避免暴露秘密、原始认证文件、provider 内存数据库或私有日志

Project Execution 依赖此边界。

## 确定性测试模式

每个 provider 都应支持确定性回复夹具。

示例：

```text
VO_EXAMPLE_REPLY_TEXT="fixture response"
```

设置后，适配器应：

- 跳过真正的运行时调用
- 返回 `ok: true`
- 返回稳定的 `sessionId`/`runId`
- 不发出任何真实工具
- 不修改任何文件

这使得聊天、路由、历史和 UI 测试不依赖于 provider 身份验证。

## 测试检查清单

为以下行为添加测试：

- provider 禁用时返回明确错误
- provider 测试端点报告安装/认证状态
- 发现返回标准化的 agent 形状
- 阻塞聊天验证消息和 agent id
- 成功聊天返回标准化结果
- 失败映射到 provider HTTP 状态
- AgentPlatform 发送路由到 provider
- 请求和回复附加到通信历史
- 在线状态切换到“工作中”然后“空闲/离线”
- 确定性回复模式无需 provider 认证即可工作
- 运行/SSE 发出开始、进度和终止事件（如果支持）
- 取消返回终止状态（如果支持）
- 当工作区有效时 Project Execution 可以调用 provider
- 当工作区/角色失败时 Project Execution 阻止或报告干预
- Executable Meeting 可以调用 provider 作为参与者

## 最小实现顺序

1. 添加 `app/providers/example.py`。
2. 在 `_load_vo_config()` 中添加配置字段。
3. 在名册聚合中添加发现。
4. 添加 `_handle_example_test()` 和 `_handle_example_chat()`。
5. 添加 HTTP 路由。
6. 添加 `_handle_agent_platform_comm_send()` 路由分支。
7. 添加确定性回复测试。
8. 如果 provider 应参与，添加 Project Execution 和 Meeting 路由。
9. 添加后台运行/SSE、审批、取消和文件证据。

## 设计原则

- 将 provider 特定的代码保留在适配器和精简服务器路由中。
- 不要让通用办公功能直接调用 provider CLI。
- 当存在公共 API 或 CLI 接口时，不要读取私有的 provider 内部数据。
- 在将结果返回给办公功能之前进行标准化。
- 优先使用可见的办公通信，而不是屏幕外的私有 CLI 消息。
- 将工作区写入、shell 执行、浏览器访问和凭据视为明确的安全边界。

## 当前参考

- `app/providers/codex.py`
- `app/providers/codex_app_server.py`
- `app/providers/claude_code.py`
- `app/providers/hermes.py`
- `app/provider_execution.py`
- `docs/AGENT_PLATFORM_COMMUNICATIONS.md`
- `docs/CODEX_PROVIDER_ADAPTER.md`
- `docs/HERMES_PROVIDER_ADAPTER.md`
- `docs/VIRTUAL_OFFICE_AGENT_TOOLS.md`
