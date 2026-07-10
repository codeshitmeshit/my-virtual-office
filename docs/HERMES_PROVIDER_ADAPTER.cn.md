> English version: [HERMES_PROVIDER_ADAPTER.md](HERMES_PROVIDER_ADAPTER.md)

# Hermes 提供者适配器

状态：原生运行流式传输实现

## 目标

在不将 My Virtual Office 变成一堆平台特定条件语句的前提下，添加 Hermes Agent 支持。

OpenClaw 继续使用现有且经过验证的代码路径。Hermes 支持以独立的提供者适配器起步，后续可成为其他代理平台的模板。

## 当前适配器

路径：`app/providers/hermes.py`

该适配器暴露以下功能：

- `discover_agents()` — 将 Hermes 配置文件作为规范化的办公代理返回
- `discover_api_agents()` — 发现 API Server 支持的代理
- `discover_desktop_agents()` — 发现 Desktop Backend 支持的代理
- `test()` — 检查 CLI/主目录模式；服务器的 `/api/hermes/test` 会综合 API Server、Desktop Backend、Gateway Platform 和 CLI 结果
- `send_message(profile, message)` — 通过公共 CLI 发送一次性的 Hermes 消息并返回标准输出
- `send_chat_message(profile, message, session_id)` — 针对未安装原生 API 服务器的环境，提供 CLI 聊天回退方案
- `HermesApiClient` — 与 Hermes 的原生 API 服务器通信，处理运行、SSE 事件、审批和停止
- `HermesDesktopBackendClient` — 通过状态接口和 WebSocket JSON-RPC 与 Desktop 的 `hermes serve` 后端通信
- `create_agent(name, role, model, emoji, profile)` — 为 Virtual Office 代理创建 Hermes 配置文件
- `delete_agent(profile)` — 通过公共 CLI 删除 Hermes 配置文件

它仅使用安全的公共 Hermes 接口：

- `hermes profile list`
- `hermes profile show <profile>`
- `hermes profile create <profile> --clone --clone-from default --no-alias --description <role>`
- `hermes profile delete <profile> --yes`
- `hermes -z <message>`
- `hermes --profile <profile> -z <message>` 用于具名配置文件
- `POST /v1/runs`
- `GET /v1/runs/{run_id}/events`
- `POST /v1/runs/{run_id}/approval`
- `POST /v1/runs/{run_id}/stop`
- `GET /v1/capabilities`
- `GET /v1/models`
- `GET /api/status`
- WebSocket `/api/ws` TUI-gateway JSON-RPC

## 原生流式传输

聊天界面通过 `POST /api/hermes/runs` 启动原生运行，然后打开 `EventSource("/api/hermes/runs/{runId}/events")`。服务器在不向浏览器暴露凭证的情况下代理消息、思考、工具、审批和终止事件，并按 conversation 保存历史。

配置 Desktop Backend 时，同一套浏览器 run/SSE 契约会通过 `hermes serve` 的 TUI-gateway WebSocket 执行。同步 `/api/hermes/chat` 和 CLI 保留为兼容回退路径。

## Messaging Gateway 平台模式

`integrations/hermes-platform/my_virtual_office/` 中的插件允许 Hermes Gateway 轮询 Virtual Office 消息队列并回传回复。该模式独立于 API Server 和 Desktop Backend，详见 [HERMES_PLATFORM_ADAPTER.md](HERMES_PLATFORM_ADAPTER.md)。

## 配置

Hermes 集成通过 `vo-config.json` 或环境变量进行配置：

- `VO_HERMES_ENABLED` / `hermes.enabled`
- `VO_HERMES_HOME` / `hermes.homePath`
- `VO_HERMES_BIN` / `hermes.binary`
- `VO_HERMES_TIMEOUT_SEC` / `hermes.timeoutSec`
- `VO_HERMES_API_ENABLED` / `hermes.apiEnabled`
- `VO_HERMES_PREFER_API` / `hermes.preferApi`
- `VO_HERMES_API_URL` / `hermes.apiUrl`
- `VO_HERMES_API_KEY` / `hermes.apiKey`
- `VO_HERMES_DESKTOP_URL` / `hermes.desktopUrl`
- `VO_HERMES_DESKTOP_TOKEN` / `hermes.desktopToken`
- `VO_HERMES_DESKTOP_HOST_HEADER` / `hermes.desktopHostHeader`
- `VO_HERMES_DESKTOP_TCP_HOST` / `hermes.desktopTcpHost`
- `VO_HERMES_DESKTOP_TCP_PORT` / `hermes.desktopTcpPort`
- `VO_HERMES_DESKTOP_LOG_PATH` / `hermes.desktopLogPath`
- `VO_HERMES_PLATFORM_ENABLED` / `hermes.platformEnabled`
- `VO_HERMES_PLATFORM_TOKEN` / `hermes.platformToken`
- `VO_HERMES_PLATFORM_AGENT_ID` / `hermes.platformAgentId`

`preferApi` 因与参考实现兼容而被接受，并映射为与 `apiEnabled` 相同的运行时行为。

Desktop 自动发现可以使用已暴露的 readiness 日志、已有 URL 或可见的 loopback 监听端口。Docker 部署可通过 `host.docker.internal` 连接宿主机 Desktop，并通过 TCP host/port 与 Host header 配置显式覆盖路由。

它**不会**读取或暴露以下内容：

- `.env`
- `auth.json`
- 原始配置
- 原始记忆
- 原始日志
- 原始 SQLite 数据库内容

## 规范化的 Hermes 代理形态

示例：

```json
{
  "id": "hermes-default",
  "statusKey": "hermes-default",
  "providerKind": "hermes",
  "providerType": "runtime",
  "providerAgentId": "default",
  "profile": "default",
  "name": "Hermes",
  "emoji": "⚕️",
  "role": "Hermes Agent",
  "model": "gpt-5.5",
  "provider": "openai-codex",
  "capabilities": ["chat", "status", "sessions"]
}
```

## 服务器集成

`app/server.py` 仅将 Hermes 相关的行为路由到 Hermes 适配器：

- `/api/hermes/test`
- `/api/hermes/chat`
- `/api/hermes/runs`
- `/api/hermes/runs/{runId}/events`
- `/api/hermes/desktop/discover`
- `/api/hermes/platform/*`
- `/api/hermes/history`
- `/api/hermes/history/clear`
- `/api/agent/create` 配合 `platform: "hermes"`
- `/api/agent/delete` 针对 `hermes-<profile>` 代理

OpenClaw 的发现、聊天、模型信息、技能、转录和网关路径目前有意保持不变。

## 未来提供者形态

未来通用的提供者接口大致应如下所示：

```python
class AgentProvider:
    provider_kind: str
    provider_type: str

    def discover_agents(self) -> list[dict]: ...
    def test(self) -> dict: ...
    def send_message(self, native_agent_id: str, message: str, **opts) -> dict: ...
    def get_history(self, native_agent_id: str, **opts) -> dict: ...
    def get_status(self, native_agent_id: str, **opts) -> dict: ...
```

目前仅 Hermes 以此方式实现，以避免破坏现有的 OpenClaw 行为。
