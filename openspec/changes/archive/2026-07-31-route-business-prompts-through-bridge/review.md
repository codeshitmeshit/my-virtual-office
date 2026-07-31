## 评审结论

带条件通过。方案方向成立：以 common business prompt bridge 作为业务 prompt 的统一入口，底层 XML formatter 退为 bridge 内部 primitive，可以解决业务线直接拼装/直接渲染 provider-visible prompt 的边界问题。

条件是 tasks 必须把迁移拆成可独立验证的 prompt family，并包含静态覆盖、输出解析失败分类、以及正式 Agent 验证/不可用记录。

## 阻塞问题

无当前阻塞问题。

## 主要风险

### 稳定性

- Prompt shape 变化可能影响 Agent 输出稳定性。
  - 建议：每个 prompt family 迁移时保留关键 domain root、section 名称、output schema 和现有测试断言。

### 数据一致性

- 业务输出解析从业务模块迁到 bridge 过程中可能产生“双解析”或错误分类不一致。
  - 建议：第一阶段仅让 bridge 统一 output contract 和 validation failure 分类，最终业务对象构造仍可留在业务模块；后续再收敛 parser。

### 安全

- 动态业务数据可能被误标为 trusted。
  - 建议：bridge API 默认 `data/history/attachments` 为 untrusted；trusted 只允许静态系统指令。

### 性能

- Prompt 构建是本地轻量操作，主链路性能风险较低。
  - 建议：避免迁移时引入文件扫描或 provider 调用前同步外部依赖。

### 兼容性

- legacy `server.py` 与拆分服务可能存在重复实现。
  - 建议：每次迁移同时处理 authoritative split service 与 legacy compatibility path，或证明 legacy hydrate 到 authoritative handler。

### 可回滚性

- 大批量迁移难以按 prompt family 回滚。
  - 建议：每个 family 保留 public wrapper，便于单点回滚为 documented exception。

### 可观测性

- Static coverage 可能只证明“没有直接 import”，但不能证明 provider reply 质量。
  - 建议：coverage 证据与正式 Agent 验证证据分开记录。

## 关键追问

### Q: 为什么不是继续让业务模块直接用 formatter？

A: formatter 只解决 XML 安全渲染，不负责业务输入规范、locale、输出 schema、provider policy、reply validation。继续直接调用会让这些职责仍散落在业务模块中。

### Q: 为什么不是把所有 prompt 统一成一个 `<business_prompt>`？

A: 已有 Agent 行为和 parser 依赖一些 domain-specific section。统一 root 会提高兼容风险。方案选择保留 domain shape，由 bridge adapters 统一边界和渲染。

### Q: 输出解析是否要一次性全部搬进 bridge？

A: 不建议。先让 bridge 统一 output contract 和 validation failure 分类；业务对象构造可以分阶段迁移，避免一次性耦合 HR/meeting/project/archive 模型。

### Q: 如何判断迁移完成？

A: 需要同时满足：业务 prompt 直接 formatter 调用清零或进入 exception inventory；prompt family regression 通过；formal/production-like Agent 验证完成或记录不可用；OpenSpec 验证通过。

## 测试与上线建议

- 新增 bridge facade 单元测试：locale、trusted/untrusted、JSON schema output、output 最后渲染、注入字符串转义。
- 新增 static coverage：业务 prompt 模块不得直接调用低层 formatter 生成 provider-visible prompt。
- HR 回归：daily report request、introduction request、assessment/summary、malformed output 分类。
- Meeting 回归：advisory/result/turn/targeted question JSON 输出 contract。
- Project/workflow 回归：project execution prompt、workflow review/rework、task final result、checklistUpdates output。
- Archive/MCP/skill 回归：archive refine、archive context、MCP guide、skill organization。
- Provider-like 验证：至少记录 Codex/Hermes/OpenClaw/Claude Code 可用性；不可用时列明缺口，不声明改进。
- 上线/回滚：每个 prompt family 独立迁移、独立验证、独立回滚为 documented exception。
