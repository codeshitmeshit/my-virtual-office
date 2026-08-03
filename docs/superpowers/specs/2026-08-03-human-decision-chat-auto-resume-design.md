# 人工决策后的聊天自动续跑设计

日期：2026-08-03

## 目标

当聊天 Agent 因重大未授权取舍创建人工决策后，当前 Provider turn 应正常结束，不通过长轮询占用聊天。用户在本地控制面板或飞书提交决策后，VO 后端应在页面关闭的情况下仍能自动唤醒原 Agent，将最终答案注入原 conversation/thread，并从暂停分支继续执行。

本期只实现 `source.type=chat` 的自动续跑。会议和项目继续使用各自的生命周期，不接入聊天续跑器。

## 行为契约

1. Chat Agent 创建决策时，必须使用当前聊天的真实 `conversationId` 作为 `source.id`。后端使用可信请求头中的 Agent ID，将 `agentId + conversationId` 保存为私有续跑元数据。
2. 决策创建成功后，当前聊天轮返回“已暂停等待决策”，不继续轮询。原 conversation/thread 不旋转、不删除。
3. 本地或飞书首次写入有效终态后，后端为该决策创建且只创建一个续跑任务。
4. 续跑输入包含决策 ID、最终答案、原情景、暂停原因和原下一步，并明确要求：从暂停分支继续、保留已完成工作、在产生可能影响修改的动作前调用 `execution-started`。
5. 续跑使用原 Agent 和原 `conversationId`，回复写入原聊天历史；VO 页面是否打开不影响执行。
6. 决策重复回调、重复终态投递或定时扫描不得产生第二次 Provider 续跑。

## 组件边界

### `human_decision_chat_continuation.py`

新增聚焦模块，负责：

- 规范化聊天续跑绑定；
- 构造 XML 外层的可信续跑 Prompt；
- 对续跑任务执行领取、投递结果分类和终态记录；
- 区分可安全重试的投递前失败与不可盲重试的未知投递结果。

模块依赖显式注入的状态端口、任务启动器和聊天投递回调，不导入 `app/server.py`。

### `HumanDecisionStore`

继续作为决策及续跑状态的唯一持久化权威。决策内部增加不公开的 `_continuation` 字段，安全快照必须移除该字段。

续跑状态使用以下有限状态：

- `waiting`：决策尚未解决；
- `queued`：决策已解决，等待后台领取；
- `running`：已有带租约的执行者领取；
- `retry_wait`：明确未调用 Provider 的临时失败，可再次领取；
- `completed`：Provider 续跑成功；
- `failed`：确定失败且不再自动重试；
- `uncertain`：进程或连接在可能已投递后失去结果，为避免重复副作用不自动重试。

状态转换、claim token 和租约更新均在 Store 锁内原子落盘。

### `HumanDecisionWorkflow`

工作流在首次有效 resolve 后请求后台续跑，但不阻塞本地或飞书回调响应。`process_due` 同时扫描可领取的 `queued`、到期 `retry_wait` 任务，并将过期 `running` 任务转为 `uncertain`。

### 聊天投递适配

服务器通过现有 VO Agent 通信服务向原 Agent 发送系统来源消息，复用原 `conversationId`。内部调用必须携带稳定的来源消息 ID `human-decision-resume:{decisionId}`，并标识来源为 `human-decision-resume`，使现有通信历史和 Provider 幂等能力可复用。

## 上下文与安全

- 普通本地聊天 Prompt 增加 XML `<conversation_context>`，包含当前 `agentId`、`providerKind` 和 `conversationId`；动态值由共享 formatter 转义。
- Agent API 只接受 loopback、无浏览器 Origin、`X-VO-Agent-Action: human-decision` 和非空 `X-VO-Agent-Id`。
- `source.type=chat` 的自动续跑只绑定请求头中的 Agent ID；客户端不能为其他 Agent 指定续跑目标。
- conversation、Provider 线程标识和 claim token 不出现在 Dashboard/飞书安全投影中。
- 决策答案、情景和任务上下文作为不可信数据放入 XML 数据边界，不能覆盖续跑指令。

## 失败与恢复

- 原 conversation 正忙或 Provider 在调用前明确不可用：进入 `retry_wait`，最多三次，使用有界退避。
- Provider 明确返回失败且确认未执行：按错误类型决定重试或 `failed`。
- 已调用 Provider 后连接中断、进程退出或租约过期：标记 `uncertain`，不自动重复调用。
- 服务启动及每分钟定时任务会继续领取 `queued/retry_wait`，因此页面关闭或服务在决策提交前重启不会丢失续跑。
- `uncertain/failed` 会保留在决策内部审计状态，并通过安全的公开续跑摘要暴露状态和错误类别，但不暴露线程标识或原始错误内容。

## 测试策略

- Store：私有绑定、安全投影、原子领取、重复领取、租约、重试和 uncertain 转换。
- Workflow：本地与飞书首次 resolve 均只调度一次；幂等回调不重复；定时扫描可恢复排队任务。
- Prompt：conversation context 和续跑 Prompt 都使用 XML formatter，动态内容无法闭合可信标签。
- 投递：复用相同 Agent/conversation，稳定来源消息 ID，成功写回原聊天历史。
- 集成：页面关闭等价的纯后端路径；服务重启后恢复 queued；busy 后重试；未知投递不重复。
- 回归：人工决策状态、飞书同步、聊天 Provider 路由和 Dashboard SSE 保持通过。

## 非目标

- 不自动恢复会议或项目执行生命周期。
- 不在本期提供人工点击“强制重试 uncertain”的 UI。
- 不保持原 Provider turn 长时间轮询。
- 不创建第二套聊天历史或新的前端 SSE 连接。
