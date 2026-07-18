# 技术方案评审

## 评审结论

**带条件通过。** “对话确认后直接创建真实项目”的方案可以成立，前提是接受并明确记录一个核心限制：当前 VO 后端无法以 provider-neutral 方式验证某条聊天确认确由用户签名。方案通过显式 skill 门禁、本机注册 Agent 边界、确认摘要 digest、原子幂等创建、项目 scoped grant，以及“创建绝不启动执行”把该限制约束在低风险项目创建范围内。

## 阻塞问题

无。

用户已经明确选择“项目方案在对话中确认，后台不保存草稿；有问题就不运行”。因此不再要求管理端草稿确认作为上线阻塞条件。

## 主要风险

### 安全

- `confirmation.confirmed=true` 是 Agent assertion，不是后端可验证的用户签名。必须限制为显式 skill、本机 loopback、无浏览器 Origin、已注册 Agent，并保留 proposal digest 审计。
- 直接创建不得扩展到自动执行、review、验收、取消或 protected maintenance。
- `projectGrantSecret` 只能首次返回，服务端只存哈希；管理 token 不得进入 Agent 路径。

### 数据一致性

- 项目、任务、角色、grant、template、recurrence 和 outbox intent 必须在一个 root CAS 中提交。
- `(Agent, idempotencyKey)` 重试必须返回同一项目；相同 key、不同 payload 必须冲突。
- workspace 准备或 root commit 失败不得留下半项目；uncommitted managed workspace 必须清理。

### 稳定性与兼容性

- 删除 active draft flow 时不得破坏已有 project actor、grant、template、recurrence 数据。
- 旧 authoring request collection 保留为 inert metadata，不自动创建、不进入健康队列、不在本次做破坏性迁移。
- legacy project、template v1、`projectWorkflow`/`projectTask` cron 和 Project Execution 行为必须保持不变。

### 可回滚性

- 直建和 recurrence 开关默认关闭；关闭后停止新写入，但保留普通项目读取。
- 回滚前暂停 recurrence 并处理 outbox；已直建项目仍是普通项目。
- 老版本不会展示新 direct-create API，但必须能忽略新增字段。

### 可观测性

- 指标从 draft submitted/confirmed/pending age 改为 direct-create success/failure/conflict/duration、grant failure、workspace cleanup、outbox age 和 occurrence outcome。
- 日志不得接收请求体、grant secret、Authorization 或 proposal 原文；只记录归一化 operation、status、code、duration 和安全标识。

## 关键追问

### Q1：为什么现在可以不用管理端确认？

A：产品风险边界已调整：用户在对话中先确认自然语言方案，创建后项目保持完全未运行；真正产生代码或外部动作的 Project Execution 仍有独立门禁。用户明确接受“项目有问题就不运行”。

### Q2：后端怎么知道用户真的确认了？

A：当前只能记录 Agent assertion 和 proposal digest，不能做 provider-neutral 的用户签名验证。这是已接受限制。若未来 VO 提供签名 message reference，可把它加入 confirmation evidence，而无需改变原子创建模型。

### Q3：为什么不直接开放现有 `/api/projects`？

A：现有路由需要高权限 management token，且兼容多种浏览器 CRUD。独立 Agent route 可以限制本机、Agent 身份、完整 payload、幂等和 no-auto-execution，不降低既有管理边界。

### Q4：第一次响应丢失时如何恢复 grant？

A：相同 idempotency key 返回原 project，但不会重复返回 secret。项目仍可见且不执行；用户通过管理端 rotate 获取新 grant。这优于持久化或重复暴露明文 secret。

### Q5：旧 pending draft 怎么处理？

A：保留为 inert compatibility metadata，不自动确认、不删除、不计入 active health。若确需恢复，应使用旧兼容版本或未来单独批准的迁移工具。

## 测试与上线建议

- 直建主流程：完整任务和角色一次创建，返回 project id，任务 backlog，execution flags false。
- 幂等：相同 key/相同 digest 返回同项目；相同 key/不同 payload 冲突；首次之外不返回 grant secret。
- 原子性：actor、workspace、template、recurrence、root commit 任一失败都没有半项目。
- 对话契约：skill 必须包含自然语言 proposal、显式确认、语义变化后重新确认、无确认不调用 API。
- 权限：non-loopback、Origin、错误 action/Agent、management token 泄漏、跨 Agent/project grant 全部失败。
- UI/API 清理：draft assets 和 active routes 不再暴露；正常 Projects UI 可读取新项目。
- 兼容：旧 project、actor projection、template v1、旧 cron、execution/review/acceptance 全量回归。
- recurrence：outbox drain/pause、重复 occurrence、claim recovery、invalid actor intervention 保持通过。
- 可观测性：direct-create counters/duration 和 outbox age 可见，legacy draft pending 不再使 health degraded。
- 灰度：flag-off 上线 → 本地直建 → 验证零自动执行 → autonomous allowlist → recurrence。
- 回滚：关闭 authoring → pause/drain outbox → 验证普通项目读取 → 回滚代码；不删除 root metadata。
