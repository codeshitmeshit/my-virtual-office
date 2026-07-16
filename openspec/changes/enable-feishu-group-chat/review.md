# Feishu Agent Group Chat Technical Review

## 评审结论

**通过。** 方案利用已锁定 SDK 的原生 mention policy，在 VO 层增加独立的业务校验、会话命名空间和投影隔离，不引入新外部依赖或数据库迁移。设计已处理当前实现中最危险的两个缺口：成员参与会导致私聊公式分裂群上下文，以及通用 Feishu ledger/SSE 合并会把群内容带入 VO 聊天框。

## 阻塞问题

无。需求中的信任边界、触发方式、共享上下文、支持内容和 UI 可见性均已确认；SDK 0.4.0 的本地锁定文档与实现能够提供可靠的 bot mention identity。

## 主要风险

- **稳定性**：单个活跃群可能占用长时间 Agent callback。沿用全局 16、单群 20 的有界控制，并以队列/存储压力作为停止放量门槛。
- **数据一致性**：崩溃发生在 Provider 外部效果之后、完成记录之前时存在重复风险。`sourceMessageId` 必须贯穿 worker spool、audit、ledger 和 provider idempotency；重启场景必须用测试证明。
- **安全**：加群即授权意味着群内每个真人成员都继承代表 Agent 的能力边界。必须默认关闭群聊、明确展示风险、保留成员审计，并保持 Provider 原有审批与沙箱策略。
- **性能**：不得为每个入站消息完整扫描不断增长的 JSONL。若现有有界查询无法满足跨重启去重，使用紧凑持久索引，不得改为 O(N) 热路径。
- **兼容性**：严格 v1 envelope 不接受未知字段。方案复用现有 `mentions[].isBot`，避免协议升级和 spool 回滚不兼容；legacy transport 保持私聊。
- **可回滚性**：关闭开关只阻止新群 turn，已执行中的 turn 会完成并留审计。旧版本能够忽略新增配置，群 ledger 的 `visibleInOffice=false` 防止渲染泄漏。
- **可观测性**：普通群流量可能造成拒绝日志风暴。SDK/VO 只累计分类计数并对摘要限频，不记录消息正文或完整成员表。

## 关键追问

### Q: 为什么空 `groupAllowlist` 不会破坏“可信群”边界？

A: 产品确认的信任动作就是管理员主动把 bot 加入群，而不是 VO 二次维护名单。Feishu 只向 bot 所在群投递事件；SDK 再要求显式 @，VO 还会复验身份化 mention 和真人发送方。代价是群成员拥有相同调用资格，因此开关默认关闭并由管理员明确启用。

### Q: 为什么不只在前端过滤群消息？

A: 群记录会经过 normalized history、旧 agent-chat、SSE 实时发布和断线 replay。只改前端无法保护其他消费者或未来客户端。服务端以 `feishu-group` 和 `visibleInOffice=false` 建立不可见性不变量，并在 publish/replay/history 三处验证。

### Q: 为什么群会话 ID 不能沿用现有私聊 ID？

A: 私聊 ID 由 VO user 与 chat ID 共同派生；同群不同成员会得到不同上下文。群 ID 必须只依赖 chat ID，并使用单独命名空间，才能同时满足共享上下文和跨群/私聊隔离。

### Q: 为什么不新增 `mentionedBot` 字段？

A: 现有 envelope 已包含 SDK 生成的结构化 mentions，其中目标 bot 被标为 `isBot=true`。严格 v1 新增字段会让旧 server 无法读取新 worker 已落盘的 spool。复用现有字段能够实现相同判定并保持回滚兼容。

### Q: 群聊为什么只支持 Node transport？

A: Node SDK 已在握手时解析 bot identity，并在 normalization/policy 阶段给出可靠 mention 证据。legacy Python receiver没有同等的已验证身份化语义；同时支持会扩大安全与验收矩阵。回滚到 legacy 时保留私聊是更清晰的降级。

### Q: 如何证明群聊不会影响私聊？

A: 配置开关、conversation namespace、source surface、visibility、reply destination 和 SSE policy 都按 chat type 分支；验收必须让私聊与多个群并发交错，并验证 private history/SSE 与原行为一致。

## 测试与上线建议

- Worker contract：SDK policy、真实 bot mention、非 bot mention、`@all`、bot/system/unknown sender、normalization 与 v1 spool replay。
- Server admission：开关开/关、Node/legacy transport、任意未绑定真人成员、文本、rich-post 图片、裸图片、文件和空 prompt。
- Conversation：同群跨成员连续、跨群隔离、群与私聊隔离、代表 Agent 切换、四类 Provider conversation mapping。
- Consistency：重复 callback、进程重启、callback 失败重放、同群并发顺序、跨群并发、Provider 成功后 delivery 失败。
- Projection：audit/ledger 可查，normalized history 初始页/分页/缓存/旧接口不可见，SSE publish/replay/reconnect 不包含群事件，私聊 delivery invalidation 仍生效。
- Security：伪造 worker token、伪造文本 @、缺少 `isBot`、bot sender、超大附件、路径逃逸、显示名 prompt 注入与敏感日志脱敏。
- Capacity：单群队列 20、全局 callback 16、spool 满、拒绝计数和日志限频；热路径不得全量扫描历史。
- 上线从“代码部署、开关关闭”开始；只在测试群开启，通过真实租户矩阵并观察队列、spool、Agent 延迟和 delivery failure 后再扩大使用。
- 回滚门禁：关闭开关后无新 group dispatch；在途 turn 完成可对账；私聊继续；代码回滚后 group ledger 不显示在 VO 聊天框。
