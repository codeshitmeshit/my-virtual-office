> English version: [HERMES_PROVIDER_ADAPTER.md](HERMES_PROVIDER_ADAPTER.md)

# Hermes 提供者适配器

状态：原生 API 客户端加上可选的服务器端运行/事件集成

## 目标

在不将 My Virtual Office 变成一堆平台特定条件语句的前提下，添加 Hermes Agent 支持。

OpenClaw 继续使用现有且经过验证的代码路径。Hermes 支持以独立的提供者适配器起步，后续可成为其他代理平台的模板。

## 当前适配器

路径：`app/providers/hermes.py`

该适配器暴露以下功能：

- `discover_agents()` — 将 Hermes 配置文件作为规范化的办公代理返回
- `test()` — 检查配置的 Hermes CLI/主目录并返回检测到的配置文件
- `send_message(profile, message)` — 通过公共 CLI 发送一次性的 Hermes 消息并返回标准输出
- `send_chat_message(profile, message, session_id)` — 针对未安装原生 API 服务器的环境，提供 CLI 聊天回退方案
- `HermesApiClient` — 与 Hermes 的原生 API 服务器通信，处理运行、SSE 事件、审批和停止
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

## 原生 API 路由

Hermes 原生 API 的使用是可选启用的。当 `hermes.apiEnabled` 或兼容的别名 `hermes.preferApi` 启用，且 API 服务器报告支持运行提交和 SSE 事件时，`/api/hermes/chat` 会启动一个 Hermes API 运行，在服务器端消费原生事件，将结果规范化为现有的 Virtual Office 聊天/历史记录格式，并记录回复、思考内容、工具卡片、运行/会话 ID、审批状态和错误。

如果原生 API 服务器被禁用、不可用或无法启动运行，`/api/hermes/chat` 会保持现有的 CLI 回退路径。来自原生 API 的审批事件会存入与聊天界面其他部分相同的待审批队列中。

参考分支描述了浏览器 `EventSource` 代理路由，例如 `/api/hermes/runs/{runId}/events`。本次本地迁移并未用那些浏览器 SSE 路由替换聊天传输方式；它有意保持当前的聊天/项目/会议契约，并在服务器请求路径内部消费原生运行事件。

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

`preferApi` 因与参考实现兼容而被接受，并映射为与 `apiEnabled` 相同的运行时行为。

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
