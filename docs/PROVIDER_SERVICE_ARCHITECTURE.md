# Provider 服务架构与运维

本文描述 Virtual Office 当前的 Provider 后台边界、容量和发布操作。它适用于 OpenClaw、Codex、Claude Code、Hermes API/Desktop/Gateway Platform，以及调用这些 Provider 的 Project Execution、Meeting 和 Feishu 通知流程。

## 1. 权威状态与调用方向

HTTP 路由只负责鉴权、输入解析和兼容响应组装。后台运行统一按以下方向调用：

```text
HTTP route
  -> provider-specific adapter
  -> ProviderRunCoordinator
       -> ProviderRunRepository       (run/idempotency/generation/terminal/cancel)
       -> ProviderEventJournal        (event cursor/index/replay/retention)
       -> ProviderAdapter             (native Provider I/O)

ProviderSSETransport
  <- repository snapshot + event journal replay/wait + recovery readers
```

其他状态各有一个独立权威：

- `ProviderConversationService`：按 `(providerKind, agentId, profile, conversationId)` 协调 history、native ID、reset 和 continuation。
- `ProviderApprovalService`：管理 pending approval、顺序、decision claim/token、重放结果和通知意图。
- Provider adapter：只负责 Provider 原生协议、CLI/API/WebSocket 解析、能力声明和真实取消/继续调用，不直接修改 repository/journal 内部结构。
- OpenClaw Gateway Platform：保持 queued delivery 能力，不合成 background run 或 SSE。

运行状态和事件仍是单进程内存语义，重启后不恢复 active run。对话历史和 Provider native session/thread/run ID 继续使用原有 JSON/Provider 存储格式，不双写、不要求数据迁移。

## 2. Adapter capability

Adapter 用 `AdapterCapabilities` 明确声明 `background_run`、`streaming_events`、`cancel`、`conversation_continuation`、`approval_continuation`、`attachments` 和 `queued_delivery`。调用方必须先检查能力；不支持的操作返回既有 unavailable/unsupported 行为，不能用最低公共接口伪造 Provider 能力。

Codex、Claude Code 和 Hermes API/Desktop 支持后台 run 与规范化事件。Hermes Gateway Platform 和 OpenClaw 使用各自已有的排队消息路径。各 Hermes 路径的优先级和 fallback/error 语义保持不变。

## 3. 并发、一致性与幂等

- run 在启动 worker 前原子 reserve。幂等 scope 是 `providerKind + agentId + conversationId + idempotencyKey`，key 最长 256 字符，保留窗口与 run 相同。
- 每个 run 有 generation/version token。完成、取消、超时、清理和迟到 callback 使用 compare-and-set；旧 generation 不能覆盖或重建新 run。
- terminal event 需要 repository terminal claim 和 journal terminal 去重，同一 run 最多发布一次 `run.completed`、`run.failed` 或 `run.cancelled`。
- approval 用可信服务端 context 绑定 Provider、Agent、profile、session、run 和 conversation；decision token/lease 防止重复、伪造或跨 run 决策。支持 `once`、`session`、`always`、`deny`。
- conversation reset/continuation 使用 generation/version token；过期写入返回 stale，不覆盖 reset 后状态。
- 慢 Provider、通知、序列化和 socket I/O 均在状态锁外执行。一个 Provider 的异常、超时、通知失败或断开的 SSE 连接不能终止其他 Provider 的工作。

## 4. 容量与保留

| 状态 | 上限/保留 |
|---|---:|
| run 与 idempotency | terminal 后 10 分钟，增量有界清理 |
| event journal | 全局最近 4,000 条，run/conversation eviction-consistent 索引 |
| event payload | 字符串 8,192；列表 200；字段 100；深度 6 |
| conversation history | 每 scope 500 条；上下文 120,000 字符 |
| conversation attachment | 每次 20 个；单个 descriptor 最大声明 50 MiB |
| conversation scope owners | 4,096 个非活动 scope，LRU 回收 |
| approval | pending 1,000；每 scope 100；resolved 2,000；24 小时保留 |
| Codex app-server pending approval | 100 |
| generic app-server pending request | 1,000 |

达到容量时必须拒绝或有界淘汰，不能创建第二套未跟踪状态。任何容量调整都要同步固定性能 fixture、边界测试和本文。

## 5. SSE 与恢复

`ProviderSSETransport` 是唯一 SSE framing owner。它负责响应头、`Last-Event-ID`/`after` 取最大合法 cursor、`id/event/data` frame、初始 Provider snapshot、pending approval/history/progress recovery、10 秒 heartbeat/keepalive、terminal replay 和断连处理。

Transport 只读 repository/journal 和 recovery reader。连接建立、重连或断开不会启动、完成、清理或取消 run。可选的 history/approval recovery 失败会单独降级，live indexed replay 仍继续。所有 frame 在写出前再次经过 allowlist、长度限制和敏感信息清理。

最终允许的 transport delegate 只有：

- `OfficeHandler.do_GET`：鉴权、route/query/cursor 解析及 HTTP status/header。
- `OfficeHandler.do_POST`：请求解析/校验和兼容响应组装。
- `ProviderSSETransport.stream_run`、`stream_conversation`：SSE transport 行为。
- `_handle_codex_run_events`、`_handle_claude_code_run_events`、`_handle_hermes_run_events`：仅转发到 transport。

生成的权威清单位于 OpenSpec change 的 `evidence/current/provider-transport-delegate-candidates.json`，`mustMove` 必须保持为空。

## 6. 敏感数据和可观测性

事件、approval、通知、诊断和日志禁止保存 credential、Authorization/Cookie、password、API key/token、raw request/response、完整 prompt/transcript、私钥、绝对路径或不受限 Provider metadata。DTO 进入 journal/notification 前按字段 allowlist、深度、数量和字符串长度进行裁剪及 redaction。

排障时记录 operation、provider kind/path、scope 摘要、run ID、generation/version、terminal/cancel/approval claim 结果、event cursor/retained count、adapter call count 和 duration；不要记录原始 Provider 输出或本机路径。重点区分：未 reserve、已 reserve 未 launch、active、terminal、stale callback、duplicate idempotency、capacity rejected 和 notification degraded。

## 7. 启动、验收与回滚

候选验收和回滚后重启只能使用仓库启动脚本：

```bash
./start.sh
./start.sh --browser   # 需要 CDP/UI 验收时
```

不要用 `python app/server.py` 作为验收启动方式。发布前：停止接收新 run，等待或取消 active work，记录 pending approval、idempotency、event cursor、conversation/native-ID/history 摘要和外部 Provider/Feishu 效果。一次只能运行一个候选进程。

回滚时停止候选，恢复上一版本代码和配置，通过 `start.sh` 重启，然后验证历史/native mapping 可读、旧 API/status/event 名称不变，并对已经发生的 Provider/Feishu 外部效果做人工对账。active run/event 是非持久状态，不能把“重启后仍 active”作为成功条件。

外部凭据不可用时使用 fake/local adapter 验证状态机、SSE、approval、cancel 和故障隔离，并把真实 Provider/Feishu 路径记录为 manual-only，不得把未执行项描述为已通过。
