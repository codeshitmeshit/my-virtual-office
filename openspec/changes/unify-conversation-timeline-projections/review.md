# 技术方案评审

## 评审结论

**带条件通过。** 方案建立了唯一的只读 conversation timeline 权威，不改变 Provider 执行与持久化所有权，也不要求 UI 统一。进入实现前，必须把以下条件转为任务并逐项验证：四 Provider characterization、稳定身份与顺序夹具、live/durable 对账、敏感数据边界、性能基线、逐 Provider 回滚，以及旧投影逻辑最终删除。

## 阻塞问题

无阻塞设计问题。

条件项：当前 live 与 durable 记录并非所有 Provider 都具有同一种原生 ID，错误归并的风险高于重复显示。建议选项是“优先可信 ID、按完整 scope 约束、证据不足时保守不合并”，设计已采用该选项；tasks 必须包含无 ID、重复文本、相同时间戳和跨 attempt 的反例测试。

## 主要风险

- **稳定性**：共享投影故障可能同时影响两个入口。方案通过无状态服务、Provider source 隔离、兼容错误结果和逐 Provider 切换降低爆炸半径。
- **数据一致性**：live 与 durable 可能重复、错误合并或终态回退。方案使用 scope + trusted identity + lifecycle version，并禁止仅按文本合并。
- **安全**：OpenClaw transcript、工具参数和 Provider 错误可能包含凭据或绝对路径。方案要求在公共 DTO 和诊断前 allowlist、bound、redact。
- **性能**：若统一实现每次扫描完整 JSONL 或全部 activity，项目轮询会放大成本。方案保留 50/1,000、32-entry/64 MiB 上界和现有 scope 索引/cache，并要求前后基线。
- **兼容性**：项目旧字段、标准 history cursor 或 SSE payload 变化会破坏现有客户端。方案只做 additive canonical field，并保留 route、cursor、status 和旧字段映射。
- **可回滚性**：过早删除旧逻辑会使单 Provider 回滚困难。方案先建立只读 delegate/shadow comparison，分 Provider 切换，最终验收后再删除旧路径。
- **可观测性**：内容级 parity 日志可能泄露用户消息。方案只记录 scope digest、ID/version/order digest、数量、状态和耗时，并对错误限频。

## 关键追问

**Q：为什么不让 Project Execution 直接调用 `/api/chat/history`？**

A：HTTP handler 不是可复用业务边界，而且无法安全承担 project/task/attempt ownership。两个入口应调用同一 application service，而不是一个入口回调另一个 HTTP 接口。

**Q：为什么不把能力直接塞进 `ProviderConversationService`？**

A：该服务拥有 conversation mutation、generation 和 native continuation；timeline 是只读、多源 projection。混合后会扩大锁和职责，增加读操作影响写路径的风险。

**Q：如何避免“为了去重把两个相似回复合成一个”？**

A：可信 source ID 或 run/item correlation 优先；完整 Provider/Agent/conversation scope 必须相同；文本只参与 fallback fingerprint，不能单独作为 merge 依据。证据不足时宁可保留两项并暴露测试差异。

**Q：为什么标准聊天前端还需要改动？**

A：历史已经来自统一 endpoint，但 live canonicalization 仍在 `chat.js`。若不迁移它，运行中仍存在第二套 identity/status/reasoning 规则。改动只涉及数据消费，不要求改变 UI 样式。

**Q：Codex fast path 的 transient reasoning 是否会被强制持久化？**

A：不会。timeline 读取合并当前可见 transient snapshot，但保持既有“进程失败可丢失 transient、durable final 不丢失”的合同。

**Q：发现 bug 时怎样判断能否顺手修？**

A：必须可复现、位于迁移 slice、预期行为能从一致性/准确性/隔离/兼容规格推出，并先加入 failing-before test。需要新产品政策或属于无关模块时停止并回到规格确认。

**Q：回滚是否需要数据修复？**

A：不需要。本设计没有新 durable store 或双写。迁移阶段按 Provider 恢复旧 read delegate；旧逻辑删除后的回滚是代码版本回滚，原历史文件保持兼容。

## 测试与上线建议

- 冻结 `/api/chat/history`、workflow chat、Provider SSE、cursor 和 canonical field 的兼容夹具。
- 为 Codex、Claude Code、Hermes、OpenClaw 建立 active、terminal、refresh/restart、empty-reasoning、tool success/failure fixture matrix。
- 覆盖 delta/replace/boundary/replay、相同时间戳、缺 ID、重复文本、跨 conversation/attempt、stale progress、live-to-durable settlement。
- 覆盖 Claude Code 不落入 OpenClaw、Hermes completed 状态、OpenClaw structured blocks、Codex 单一 reasoning owner 的 failing-before regression。
- 覆盖 malformed JSON、history unavailable、oversized content、secret/path redaction，并证明一个 Provider 失败不影响其他 Provider。
- 固定 10/50/500/1,000 source-record 与 0/1/4,000 live-event fixture，记录候选数、normalized 数、dedupe 数、cache 命中、response bytes、median/p95。
- 上线顺序为纯 service、standard history、Project Execution 各 Provider、SSE canonical item、client reconciliation、legacy removal；每步均有 focused regression 和独立回滚点。
- 回滚演练验证旧代码仍能读取相同 Provider history/session metadata，且切换 projection 不触发 Provider 执行或历史写入。
- 最终静态检查确认新服务不导入 `server.py`，两个入口只有一个 canonical timeline owner，旧 Provider-specific project/client canonicalizer 已删除。
