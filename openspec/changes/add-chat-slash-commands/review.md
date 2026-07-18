# 技术方案评审

## 评审结论

通过。方案将命令识别和状态编排收敛到独立服务，复用现有 Provider conversation、Feishu 作用域和持久化幂等设施；当前没有阻塞设计成立或验收判断的问题。非 Codex Provider 缺少真实 compaction 能力，已按已确认规格设计为明确 `unsupported`，不伪造成功。

## 阻塞问题

无。

## 主要风险

### 稳定性

- 命令与长时间 Agent turn 竞争可能阻塞 Feishu worker。方案要求命令非阻塞抢占现有 conversation owner，忙时立即失败。
- Provider reset 的旧 native session 清理失败可能产生残留。新 generation 先成为权威，清理仅 best-effort，不触发状态变更重试。

### 数据一致性

- Codex compaction 无跨进程幂等 token，崩溃窗口内自动重试会造成重复 side effect。必须先持久化 `started`，恢复时标为 `indeterminate` 而不是再次执行。
- VO `/new` 若先 reset 旧 conversation 再切 ID，会破坏旧会话续接。设计改为只创建新逻辑 ID，不修改旧会话。

### 安全

- 群成员可影响群共享上下文。必须继续要求可信群事件、human sender 和显式 `@机器人`，并记录操作者身份。
- Web 请求不得自行声明 Provider 或跨 Agent session key。服务端必须从 roster 解析 Provider，并验证 conversation/session identity 属于目标 Agent。

### 性能

- 普通消息仅增加 O(1) 精确字符串判断，不扫描历史。
- 指标标签限定为 surface/provider/command/status，禁止把用户、群 ID 或 conversation ID 作为无界标签。

### 兼容性

- 未知、带参数、大小写不同或带附件的 slash 文本继续走普通消息路径。
- 现有按钮、Provider route、Feishu admission、历史展示和 ordinary message contract 不变。

### 可回滚性

- 全局和 Feishu 子开关均关闭时恢复旧处理路径；无 schema/data migration。
- 已成功执行的 reset/compact 不逆向恢复，回滚只阻止后续命令。

### 可观测性

- 必须区分 recognized、success、busy、unsupported、failed、indeterminate、duplicate 和 feedback failure。
- Feishu command started/completed 使用现有轮转审计；日志不得包含完整上下文或 raw provider output。

## 关键追问

### Q: 为什么不直接在 `sendMessage` 和飞书 handler 中各写一套分支？

A: 两端共享解析、Provider 能力、幂等和结果语义。独立服务可避免 transport drift，并满足仓库模块化约束；transport 只负责可信 scope 构造和反馈投递。

### Q: 为什么 VO `/new` 与飞书 `/new` 的 identity 行为不同？

A: VO 能创建并切换显式 conversation，必须保留旧会话可续接；飞书 chat ID 是稳定外部边界，只能在同一逻辑 identity 内推进新的 context generation。

### Q: 为什么不为其他 Provider 用摘要 prompt 模拟 compact？

A: prompt 摘要无法可靠覆盖工具状态、附件、审批和隐藏 native context，会产生第二上下文权威。明确 unsupported 比伪造压缩成功安全且可验收。

### Q: 为什么崩溃恢复不自动重试 compact？

A: Provider 没有幂等 token，无法判断 side effect 是否已完成。at-most-once + indeterminate 能避免重复压缩；用户可以看到明确状态后重新发起新的命令。

### Q: 关闭开关是否能完全回滚？

A: 能停止新命令识别并恢复旧 ordinary-message 路径，但不会撤销已提交的 reset/compact；这些本来就是用户明确触发的会话操作。

## 测试与上线建议

- 纯单测覆盖精确匹配、空白、大小写、参数、附件、unknown slash 和有界 DTO。
- Provider matrix 覆盖四类 Provider 的 `/new`，Codex compact success/busy/not-found/failure，以及其他 Provider unsupported/no mutation。
- 并发测试覆盖 active turn、双命令、reset 与迟到 commit、不同 conversation 并行。
- Feishu 测试覆盖私聊、群聊 mention、无 mention、同群共享、跨群隔离、source redelivery、started recovery、feedback failure 和 actor attribution。
- Browser 测试覆盖命令不生成 optimistic ordinary prompt、`/new` 切换新 ID、旧历史可重开、失败保持原选择、stale history/SSE 不串线。
- 安全测试覆盖伪造 provider、跨 Agent session key、超长 idempotency key、敏感错误脱敏和指标低基数。
- 上线顺序为代码+双开关关闭、VO 小流量、飞书私聊、飞书群聊；每步以错误率、busy/indeterminate、重复执行、反馈失败和普通消息回归为继续门槛。
- 回滚演练验证依次关闭 Feishu 子开关和全局开关后不再产生 command operation，同时普通消息、既有会话和已提交结果保持可用。
