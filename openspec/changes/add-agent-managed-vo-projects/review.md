# 技术方案评审

## 评审结论

**带条件通过。** 方案可以进入技术方案确认，前提是实现严格遵守已写入 `design.md` 和 `tasks.md` 的原子根提交、scoped grant、受保护字段边界、durable outbox、容量限制、默认关闭开关与可观测性要求。当前没有需要用户先补充才能成立的阻塞问题。

本轮评审已修正两项原设计阻塞缺口：

1. 将项目草案、确认状态、模板、recurrence 和项目本体统一纳入 project-store root 原子边界，避免跨文件提交无法保证“确认一次、完整创建一次”。
2. 将 autonomous 直接维护从“信任请求体 Agent ID”改为“用户确认后激活、仅绑定单项目和单 Agent 的哈希 scoped grant”，避免身份冒用扩大写权限。

## 阻塞问题

无。

以下开放项不阻塞后台契约：本地用户最终展示标识、草案入口放在 Projects 页面还是侧边栏、丢失 scoped grant 后的 UI 交互样式。设计已经给出安全默认值，后续只能改变展示或恢复体验，不能放宽权限边界。

## 主要风险

### 稳定性

- workspace 创建、项目根提交和 Gateway 注册不能形成真正的分布式事务。方案通过提交前 workspace 准备/失败清理，以及提交后 durable outbox/reconcile 隔离外部调用；实现必须覆盖清理失败和重启恢复。
- recurrence callback 可能重复、并发或在处理中重启。必须使用 `(recurrenceId, occurrenceId)` 去重、带 owner token 的过期 claim 和 compare-and-set commit。

### 数据一致性

- 单独的 request store 会破坏项目与确认状态的原子性，因此禁止恢复为第二套独立状态文件。
- 模板必须使用不可变版本；dispatch 时读取“最新模板”会改变已批准的未来工作定义。
- request edit/confirm 必须携带 revision，重复确认必须返回同一 project id。

### 安全

- Agent 不得获得 management token。低权限 draft submission 只能创建 pending request。
- autonomous mutation 必须同时满足 scoped grant 有效、Agent 与项目绑定、Agent 与任务绑定、字段在 allowlist 内。
- request secret 只能首次返回，服务端仅存哈希；日志、审计、错误和管理页面不得输出 secret/header。
- Agent routes 必须限制 loopback、拒绝浏览器 Origin、关闭宽松 CORS，并具备 body、pending 和速率限制。

### 性能与容量

- VO 是本地低并发系统，但 root metadata 仍会进入 project-store load/save 路径。authoring collections 必须有上限、终态压缩和 bounded history，列表接口不得扫描所有 task 文件。
- outbox worker 必须限制 batch、并发、重试次数和退避；队列满时拒绝新 authoring/recurrence，而不是拖慢现有项目读取和执行。

### 兼容性

- 新 actor references 必须保留 `assignee`、`executorAgentId`、`reviewerAgentId` 投影，旧项目读取不得强制迁移。
- 旧模板按 implicit v1 读取；旧 `projectWorkflow`/`projectTask` cron target 不得转换成新实例生成模式。
- 新 API 必须使用 additive routes，不得降低现有 `/api/projects` management-token 保护。

### 可回滚性

- 两个功能开关默认关闭；关闭后停止新 draft/autonomous mutation 和新 recurrence 注册/dispatch，但保留管理端修复能力。
- 代码回滚前必须暂停 reconciler，并确认 outbox 已清空或明确接受其成为 inert data。
- 已创建项目保持普通旧接口可读；新增 root collections 对旧行为必须是可忽略的附加数据。

### 可观测性

- 必须区分 disabled、idle、queued、processing、failed、reconciled，不能只记录单一 success/failure。
- 需要观测 draft pending 数、confirm conflict、grant failure、outbox depth/age/retry、claim duplicate/expiry、instance create failure、workspace cleanup failure和端到端 materialization latency。
- 同一 request/occurrence 的高频失败日志必须限频，完整细节保留在 bounded audit/intervention record。

## 关键追问

### Q1：为什么不能让 skill 直接调用现有 `/api/projects`？

A：现有项目写接口需要 browser management token，且项目与任务分多次写入。把 token 交给 Agent 会扩大权限并泄露高权限凭据，多次写入也会产生半成品。pending request + management confirm + root atomic commit 同时解决授权和一致性问题。

### Q2：为什么要新增 skill，而不是扩展 `vo-project-workflow`？

A：现有 skill 的职责是执行、review、验收和 artifact；项目 authoring 是控制面写入，具有不同身份、确认和幂等边界。拆分后，authoring 不能绕过 execution gate，执行 skill 也不持有项目管理能力。

### Q3：autonomous 模式为什么仍不能改负责人或删除任务？

A：这些操作会改变授权范围或不可逆地改变项目结构，超出“日常维护”的隐含授权。autonomous 只放行状态、描述、checklist、evidence、due date，并且仍要求项目 scoped grant 和任务绑定。

### Q4：为什么 recurrence 不直接复用现有 project cron callback？

A：现有 callback 的语义是启动或重启同一个项目/任务；新需求要求每次产生独立项目。新增 target kind 可以复用 schedule/Gateway 基础设施，同时保持旧 target 的协议和状态机不变。

### Q5：Gateway 注册失败时如何避免确认流程丢状态？

A：确认事务只提交本地 recurrence intent 和 outbox，不同步声称 Gateway 已注册。reconciler 在事务外幂等注册，并把 pending、retry、failed 和 intervention 状态写回。这样外部失败不会丢失已确认意图，也不会阻塞项目根锁。

### Q6：为什么 scoped grant 不在 Agent 请求体中直接使用 Agent ID 替代？

A：Agent ID 是公开标识，不是凭据。request secret 在用户确认前没有项目写权限，确认后才被绑定到单项目、单 Agent、单 mode 的有限权限；服务端仅存哈希，并支持撤销和轮换。

## 测试与上线建议

- 原子性：workspace 准备失败、root commit 失败、重复 confirm、并发 edit/confirm、重复 idempotency key 均不得产生半项目或重复项目。
- 权限：无 management token 的 confirm/edit/reject、跨 Origin draft、错误 request secret、撤销 grant、跨项目 grant、未分配 Agent、越权字段全部失败且无写入。
- 兼容：旧项目、旧模板、旧 cron、旧 execution/review/acceptance 回归必须保持通过。
- recurrence：重复 callback、并发 callback、claim 过期、重启恢复、Gateway 超时/失败、invalid actor、workspace cleanup failure均需可恢复证据。
- 容量：body/task/pending/audit/history 上限、outbox 满、worker 并发和退避要有确定错误与主链路不受影响的验证。
- 可观测性：每个关键状态必须有计数、耗时或队列年龄证据，并验证 secret/header 被日志和审计脱敏。
- 灰度：代码上线时两个开关关闭；先开启本地 draft/confirm，观察冲突、grant 和延迟；再开启 autonomous allowlist；最后开启 recurrence reconciler/dispatch。
- 回滚：依次关闭 recurrence、暂停并处理 outbox、关闭 authoring、撤销 grants、验证旧项目路径，再决定是否回滚代码。
