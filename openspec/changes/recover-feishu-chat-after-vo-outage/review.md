## 评审结论

**带条件通过。** 方案在不新增第二套业务队列的前提下，将持久化 spool、VO 幂等状态和独立恢复协调器组合成闭环，能够覆盖已复现的“VO 恢复后旧消息不再重放”问题。进入实现的条件是任务清单必须完整覆盖终态 ACK、processing 所有权、同会话顺序、跨会话容量隔离、状态脱敏、灰度开关和故障注入验证。

## 阻塞问题

无。以下原阻塞点已在 design 中形成明确决策：

- `user_message/processing` 不再被当作可删除 spool 的终态 ACK。
- background replay 与 WebSocket connection recovery 解耦。
- live delivery 与 replay 进入同一 per-chat 有序执行通道。
- retry 无次数上限，但并发、间隔、spool 容量和日志均有界。

## 主要风险

- **稳定性：** VO 长 Agent turn 与回调故障难以区分；通过短 transport attempt、active-source 快速 202 和 single-flight 避免重复执行。
- **数据一致性：** VO 在 provider 接受后、终态落盘前崩溃可能造成重放；必须复用 source-message provider idempotency key，并验证所有 provider 路径。
- **安全：** spool 和状态包含敏感上下文；保持 0600 存储并对管理响应使用字段白名单，不公开路径、内容、URL 或原始异常。
- **性能：** 恢复积压可能形成流量尖峰；按 chat 分组、每 chat 串行、全局恢复并发默认 4，且复用总 callback 上限。
- **兼容性：** 新增 202 non-terminal ACK；采用 server-first、worker feature-off 的顺序，并验证旧 worker 回滚。
- **可回滚性：** 关闭恢复不能删除积压；spool 保留，正常即时处理继续。
- **可观测性：** 连接健康与处理健康必须分离；控制面板不得因 SDK connected 显示整体健康。

## 关键追问

### Q1：为什么不在 Python 侧新增 durable job queue 并立即返回 202？

A：现有 worker spool 已经是可靠传输边界，VO 又拥有业务记录和幂等索引。新增业务队列会形成第二套调度、恢复和状态权威，超出本次范围。方案改为只有 VO 终态可删除 spool，保留一个恢复权威。

### Q2：为什么不能继续使用 CallbackClient 内部五次长重试？

A：最长可占用约 50 分钟，无法提供一分钟内恢复尝试，也会耗尽 callback 并发。单次有界 transport attempt 配合持久化调度，才能让重试长期持续且容量可控。

### Q3：重试怎样避免重复 Agent turn？

A：source message ID 保持不变；VO 区分 completed 与 processing，当前进程 active source 返回 non-terminal 202，进程重启后才允许由 spool 重新认领，并继续使用 provider idempotency key。

### Q4：为什么同会话后续消息不能绕过一条卡住的旧消息？

A：用户已确认要求同会话保序。绕过会改变上下文顺序。方案允许其他会话独立推进，并通过状态栏明确展示被阻塞会话的最老积压。

### Q5：控制面板为什么使用轮询而不是新增 SSE？

A：管理状态频率低，现有配置 API 已承载 worker 状态。仅在设置面板可见时五秒轮询可保持协议增量最小，并避免把运行状态混入面向聊天历史的 Feishu SSE。

### Q6：关闭开关后会发生什么？

A：只停止后台 recovery wake-up；不删除 spool、不停止即时消息投递、不改变现有连接状态。重新开启或重启到支持版本后仍可恢复。

## 测试与上线建议

- 建立红灯回归：VO 首次失败、恢复后无新消息，spool 在一分钟内自动清空。
- 覆盖 callback timeout、connection refused、HTTP 5xx、invalid ACK、202 processing、terminal duplicate 和持续故障。
- 覆盖 VO 在 processing 后重启、provider 完成前后崩溃、同 source 并发重试和终态唯一性。
- 覆盖同 chat 多消息严格顺序、不同 chat 并行、16 callback 上限、恢复并发上限、20 条 chat pressure 和 1,000-entry spool 边界。
- 覆盖 corrupt spool entry、disk/full pressure、worker stop/restart、feature switch off/on 和旧 worker 回滚。
- 覆盖 status 字段状态转换、最老积压时间、lastAck、nextRetry、warning，以及凭据、路径、URL、消息内容的 canary 脱敏。
- 覆盖控制面板 healthy/degraded/recovering、legacy/missing processing、可见时轮询和隐藏后停止轮询。
- 上线从“server compatibility + recovery off”开始，再部署 worker/UI，最后在测试租户开启；任意消息丢失、重复、乱序、全局阻塞、敏感信息泄漏或无法回滚均停止放量。

## 最终验收记录（2026-07-16）

**功能验收通过。** 经需求方复核，本次变更已经解决飞书长连接保持正常但 VO 回调故障后消息无法自动恢复、且控制面缺少独立处理状态的问题。完整回归和离线发布演练均已通过，满足本次需求的核心验收目标。

最新 push 前双路代码评审发现 3 类边界问题。需求方判断它们不阻断本次功能验收，同意登记为已知延期项，后续单独安排修复：

1. 故障会话的持久化 backlog 没有完整纳入每会话 20 条内存 lane 上限，极端持续积压最终仍由全局 1,000 条/50 MiB spool 上限保护。
2. 数值环境变量为空字符串时会被约束到最小值，而不是回退到文档默认值；未配置变量不受影响。
3. 公开状态投影会折叠部分依赖不兼容状态并丢失原有安全修复提示，影响故障诊断体验，不影响消息恢复主链路。

风险接受仅代表本次功能验收结论，不表示双路 CR 已无问题，也不等同于授权执行 `git push`。详细证据和后续建议见 `evidence/task-7-acceptance-known-issues.md`。
