# 技术方案评审

## 评审结论

**带条件通过。** 范围已收窄为唯一业务链路：主会话的长耗时任务触发 AI 通知 → 通知由应用级机器人单聊投递 → 用户在该通知下的单聊话题继续 → 每个话题激活一个独立 Agent 会话。

方案复用现有通知 App `FeishuLongConnectionReceiver`、通知/通信审计、source-message index、ProviderConversationService、Provider handlers 和通知 App 的 token/HTTP 请求能力，不增加飞书接收器、外部队列、数据库、缓存或 Agent 路由基建。Chat App Channel SDK worker 与通知 App 身份不同，不应成为本功能的入站权威。

## 修改面评估

- **总体：中等。** 预计 5–7 个生产文件、6–10 组聚焦测试，约 600–1,000 行新增/调整代码，其中大部分应位于新的聚焦服务和测试。
- **新增核心文件：** `app/services/feishu_notification_topics.py`，承担根验证、绑定、上下文、有界调度和恢复 DTO。
- **小幅修改：** `app/feishu_long_connection.py` 补齐话题元数据；`app/feishu_notifications.py` 增加复用通知 App 凭证的话题 reply helper 和有界审计关联；`app/server.py` 只做 message handler 与 ports 注入。
- **可能不需修改：** `integrations/feishu-channel-worker/`、群聊 admission、Provider adapters 和 `ProviderConversationService` 主体；它们以现有接口被复用。
- **生产环境不确定项：** 本机没有“长耗时分流 / Agent 详细结果”真实数据。实现通过版本化 `NotificationRootLookup` DTO 和脱敏 fixture 隔离该差异；上线时先在开关关闭状态做只读字段存在性/分类预检，如有差异只增加聚焦兼容 adapter。这是生产验收门禁，不再阻塞主体实现。

上线前证据门禁：

1. 真实租户确认应用级机器人单聊通知下的话题回复以 `chatType=p2p` 到达现有 worker，且无需 `@`。
2. 通知审计记录能稳定关联原主会话、原请求/回复与 Agent；缺失时按方案降级，不伪造上下文。
3. 交互式审批卡可留在来源单聊话题；不支持时受保护动作保持未批准并明示失败。
4. 旧长耗时通知首次激活的兼容查找延迟低于现有 callback 告警阈值。

## 范围与权限边界

- 仅 `p2p` 单聊话题可候选激活，根消息还必须被验证为长耗时 AI 通知。
- 单聊话题沿用现有单聊消息权限，无需 `@`，不需新增飞书权限。
- 群聊、群话题、全部群消息权限、SDK mention filter 调整均不在本次范围。现有 `requireMention=true` 保持不变。
- 普通机器人单聊消息、普通应用通知及无法验证来源的话题不会激活新会话。

## 主要风险

### 稳定性与一致性

- 首条回复并发投递可能重复建立绑定。必须在现有原子 source index 锁下 create-if-absent，激活提示最多一次。
- live/recovery 的 lane key 必须统一基于稳定 topic scope，避免重启后重排。
- 同一 Agent 的 Provider 可继续保留单活限制；本功能不绕过 Provider 安全锁。

### 安全与隐私

- 不能只信任入站 `rootId/threadId`；根消息必须命中经认证的长耗时通知投递/审计证据。
- 原会话文本和通知内容是不可信数据；必须放入单根 XML prompt 的 JSON 编码 `<untrusted_data>` 边界。
- topic hash 纳入应用、tenant、chat 和 topic 维度，防止跨域碰撞。

### 性能与可回滚性

- 旧通知的兼容查找仅允许首次、范围有界，并在命中后 read-repair；稳态路径必须 O(1) 命中 source index。
- 回滚仅关闭功能开关；不涉及飞书权限、mention filter 或数据回滚。已有绑定保持惰性。

## 关键追问

### Q1：为什么不直接 fork Codex 原线程？

**A：** 需求是 Provider 无关的飞书单聊话题能力，且只继承少量上下文。Codex fork 会继承更完整的 Provider-native 状态，其他 Provider 也未必有同等语义。

### Q2：为什么还需要 topic binding？

**A：** 确定性 conversation ID 可以计算，但原主会话与 Agent 选择必须在首次激活时固定。持久绑定保证配置改变或进程重启后不会隐式切换 Agent。

### Q3：是否需要修改群消息权限或 mention filter？

**A：** 不需要。本次仅处理 `chatType=p2p` 的长耗时通知话题，并在 Python 路由层明确拒绝非 `p2p` 事件。现有群聊配置保持不变。

### Q4：为什么不建立 topic 专用队列？

**A：** 现有 worker 已有持久 spool、重复检测、全局/恢复并发和有界 execution lanes。只需将 lane key 调整为 topic-aware scope。

## 后续测试与上线要求

1. topic/root 选择、`p2p` 限定、长耗时通知分类验证、hash 隔离。
2. 首次/重复/并发激活、重启恢复、原主会话和 Agent 固定。
3. 完整/部分/不可用上下文、长度上界、XML 注入和特殊字符。
4. 单聊话题无 `@`、普通 DM 不误激活、普通应用消息不误激活、全部群路径不变。
5. 同话题顺序、不同话题独立 lane、live/recovery 同 key、duplicate、queue full、spool replay。
6. Hermes、Codex、Claude Code、OpenClaw 都使用派生 conversation scope，新话题创建新 native session，后续复用。
7. 激活提示仅一次，文本/markdown/审批/错误留在单聊话题。
8. 图片、文件、多资源、超大、非法路径、不支持 MIME、下载失败和清理。
9. 本地脱敏 fixture → 开关关闭的生产只读预检 → 单条指定通知的 bot DM 话题验证 → 小范围启用 → 指标门槛后放量。
10. 关闭开关后新激活停止，普通 DM 和全部群行为不变，已有记录无需清理。
