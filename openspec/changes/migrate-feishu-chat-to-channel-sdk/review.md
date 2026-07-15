# Technical Review

## 人工确认记录

- 2026-07-14：用户确认新增需求规格——恢复飞书消息到 VO 聊天窗口的实时同步；SSE 重连后以权威历史补齐，跨 `feishu-dm:*` 与当前 Provider 会话合并时仅包含当前代表 Agent 的可见飞书记录。
- 2026-07-14：用户确认技术设计——SSE 作为失效通知，统一历史服务端按当前代表 Agent 安全合并可见飞书记录，并在 `ready`、`message`、`delivery` 后从权威历史恢复。
- 2026-07-14：用户确认实现任务 5.5–5.8，并授权连续实现、完成后统一测试再 CR。
- 2026-07-14：用户确认聊天滚动规格——初始化默认到底部；处于底部时新事件自动跟随；查看旧消息时不得强制跳底。
- 2026-07-14：用户确认聊天滚动技术设计——ChatWindow 独立维护底部跟随状态，在异步渲染前保留意图，并由虚拟窗口与物理滚动协同完成。
- 2026-07-14：用户确认聊天滚动实现任务 5.9–5.10，并授权连续实现、完整测试及 8090 重启验收。
- 2026-07-16：用户确认当前工作区功能暂时无问题，并授权完成需求验收；真实租户直接观察与自动化/离线演练证据的边界已记录在 `evidence/task-7.4-real-tenant-acceptance.md`。

## 评审结论

**带条件通过。** 采用 `@larksuite/channel` 替换 Feishu Chat App transport 的方向成立，且 Node 子进程边界与现有 Python worker 隔离模型一致。方案只有在 design 中的 SDK 默认语义覆盖、持久化入站暂存、双向 IPC 认证、单 worker 所有权、依赖锁定和灰度回滚条件全部落实时才可进入默认启用阶段。

## 阻塞问题

当前无未解决的设计阻塞项。以下原本会阻塞上线的问题已经作为强制设计决策写入 `design.md`，实现与验收不得删除：

1. SDK 默认消息合批和 stale-drop 会改变一条消息一个 turn 的语义；采用零延迟、单消息批次，并由 VO 决定消息有效性。
2. SDK handler 失败后的 seen 行为不能提供业务可靠性；采用先原子暂存、后回调、收到持久化确认再删除的 transport spool。
3. Node/Python 双向调用存在伪造与路径攻击面；采用 loopback、每进程 token、严格 schema/body limit 和 worker-owned attachment path。
4. 新旧 worker 并存可能 split brain；采用单一 effective transport、owned-child handoff 和实例 token 轮换。

## 主要风险

### 稳定性

- 长 Agent turn 会占用 SDK per-chat pipeline 和 Python request thread；必须验证 15 分钟边界、worker 重连和 server restart。
- Node worker、Python callback 和 outbound command 三段部分失败可能产生重复请求；必须由 VO persistent idempotency 收敛。
- spool 满时继续消费会造成不可恢复丢失；硬限制时必须断开接收并优先恢复 pending entry。

### 数据一致性

- 同一 sourceMessageId 可能经 SDK retry、spool replay、legacy rollback 多次进入；所有路径必须复用同一业务 key。
- transport acknowledgement 不能早于 VO 必需记录的持久化完成。
- SDK batching 必须关闭，否则多个 source ID 合并后无法保持独立审计和回复关系。

### 安全

- App Secret、worker token、authorization header 和代理 URL 凭证需要 canary 测试覆盖日志、状态和异常。
- download command 不得接受任意目标路径；资源必须在 worker-owned root 内生成路径并受 50 MiB 限制。
- inbound/command body 必须限长，且无 token 时在任何外部效果前拒绝。

### 性能

- 并发上限为 16 chats、单 chat 队列 20、spool 1,000 entries/50 MiB；需要压力测试确认慢 Agent 不导致无界堆积。
- 状态文件、spool 和日志写入不得扫描全部历史；热路径按单消息 O(1) 文件操作和已有持久化索引执行。

### 兼容性

- 当前 UI 消费的 status 字段和已有 inbound-test/records/config routes 必须保持。
- provider body 中 source metadata 和 attachment shape 不能因 SDK normalized model 改名而丢失。
- notification/card-action app 必须继续走独立 Python runtime。

### 可回滚性

- 默认选择新 worker，但上线时通过环境 override 从 legacy 开始；切换必须先停旧再启新。
- rollback 不做历史数据逆迁移；spool replay 依赖 VO idempotency。
- legacy worker 本次不删除，删除需后续独立 change。

### 可观测性

- 必须区分未启动、依赖缺失、连接中、已连接、重连、callback retry、command failure、spool pressure/full、认证失败和 orphan exit。
- 重复错误需要日志限频，同时保留累计计数和 last error/time。

## 关键追问

### Q: 为什么不直接把整个 Feishu 对话逻辑迁到 Node？

A: Node SDK 解决 transport 和 protocol normalization；VO 的 Agent/provider routing、conversation ledger、binding 和 persistent idempotency 已在 Python 中稳定存在。整体迁移会扩大数据一致性和回滚风险，偏离本需求。

### Q: 为什么保留 Python 业务幂等，SDK 不是自带 dedup 吗？

A: SDK 默认 cache 是内存级，且 handler settle 后即可 seen；它不能证明 Agent outcome 或 VO record 已持久化，也不能覆盖进程重启和 legacy rollback。

### Q: 为什么不异步返回 202，避免长回调？

A: 那需要新增 durable job queue、结果回送和恢复状态机。当前同步 callback 加 transport spool 能保持既有语义，并在 timeout/restart 时通过 sourceMessageId 安全重放。

### Q: 为什么使用 loopback HTTP 而不是 Unix socket？

A: 项目当前已经使用 HTTP worker callback，loopback HTTP 易于双向命令、健康检查、超时和测试，并保留跨平台开发能力。安全由随机 token、绑定地址和严格协议保证。

### Q: 为什么固定 0.4.0？

A: 这是当前评审的 SDK 版本。精确 pin 和 lockfile 防止安装时漂移；未来版本必须重新审查默认 safety、normalization、errors 和 outbound contract。

### Q: 如果新 worker 失败，通知是否受影响？

A: 不受影响。notification/card-action app 不在本次迁移范围，保留独立配置和 Python runtime；Chat worker status 与 rollback 不写通知配置。

## 测试与上线建议

后续 tasks/checklist 必须包含：

1. Node fake-channel contract：normalization、identity、thread/reply、reject、zero-batch、status、command schemas 和 stable error mapping。
2. Python compatibility：现有 config/routes/UI fields、representative Agent、bindings、all providers、history/ledger and source metadata。
3. Persistence/fault injection：callback before/after durable ack crash、spool replay、duplicate after restart、worker/server death、atomic status corruption resistance。
4. Concurrency/capacity：same-chat order, 16-chat cap, per-chat 20 queue, spool 80%/100%, no unbounded memory or thread growth。
5. Security：invalid token, oversized/malformed body, unknown operation, path/symlink attack, 50 MiB resource boundary, secret canaries and log rate limit。
6. Outbound：send/reply/reaction/remove/recall/download success plus rate limit, permission, revoked target, timeout and partial-file cleanup。
7. Isolation：notification/card action continues during Chat worker startup failure, reconnect and rollback。
8. Rollout rehearsal：code deployed with legacy override, single-consumer switch to Node, real-tenant text/resource E2E, reconnect, rollback to legacy, pending spool reconciliation。
9. Activation gates：zero unexplained loss/duplicate, no secret leak, no sustained spool pressure, acceptable delivery/reconnect error rate, status/UI compatibility, and successful rollback rehearsal。
