# 人工决策后的会议与项目原生续跑设计

日期：2026-08-03

## 目标

在现有聊天自动续跑能力之上，让 `source.type=meeting` 与 `source.type=task` 的人工决策也在用户提交后由 VO 后端自动恢复。恢复必须进入原会议或原项目任务的生命周期，携带最终决策上下文，只唤醒受影响分支，不把普通聊天续跑器当作会议或项目状态权威。

本设计延续以下既有约束：飞书与本地控制面板共享同一决策状态；首个有效终态不可覆盖；页面关闭不影响续跑；所有 Agent Prompt 使用共享 formatter 构造 XML 外层；动态内容只进入不可信数据边界。

## 已确认的产品行为

1. Agent 在调查后仍遇到多个会实质影响结果、风险、范围、成本或不可逆动作的合理方案，且没有授权代用户选择时，必须创建人工决策。
2. 创建成功后，当前会议步骤或项目任务分支停止继续产生副作用；其他会议、其他项目以及同一项目内没有依赖关系的安全任务继续执行。
3. 用户可从飞书或 VO 控制面板提交。后端读取统一权威终态，自动恢复原分支，不要求用户重新发送聊天消息。
4. 自定义输入非空时优先于 A-D；恢复流程只消费规范化后的 `resolution.answer`。
5. 重复回调、重复扫描或服务重启不得重复恢复同一分支。

## 方案选择

### 采用：按来源分派到原生生命周期

- `chat`：保留现有原 conversation 唤醒。
- `meeting`：调用现有会议 `continue_decision` 转移，并让会议运行器从暂停阶段继续。
- `task`：恢复原项目任务 attempt/session，只重新提交这一项工作，不调用整项目 `resume_paused_project`。

### 不采用：项目级 pause/resume

现有 `resume_paused_project` 会重新启动暂停的 stage，语义是运维级的整项目暂停恢复。人工决策只应阻塞受影响任务，因此直接复用该入口会错误停止同阶段的无关任务。

### 不采用：把会议和项目当普通聊天发送

仅向 Agent conversation 追加消息不能原子更新会议阶段、项目 attempt、审计和重试状态，容易出现 Agent 已继续而控制面板仍显示等待的双重权威。

## 统一续跑状态

`HumanDecisionStore` 继续是决策与续跑意图的持久化权威。现有私有 `_continuation` 从聊天专用绑定扩展为带 `kind` 的通用绑定，同时保留聊天 API 的兼容委托。

状态仍使用：

- `waiting`：决策未解决；
- `queued`：已解决，等待后端领取；
- `running`：带 claim token 和租约的执行者已领取；
- `retry_wait`：确定尚未恢复原生分支，可安全重试；
- `completed`：原生生命周期已确认接收本次恢复；
- `failed`：目标不存在、归属不匹配或生命周期已不允许恢复；
- `uncertain`：可能已经恢复但结果未知，为避免重复副作用不自动重试。

公开快照只暴露安全摘要，不暴露 conversation、attempt、claim token、租约或内部版本条件。

## 来源绑定与可信校验

### 会议

创建请求使用：

```json
{"source":{"type":"meeting","id":"<meetingId>","label":"<meeting topic>"}}
```

后端根据可信 `X-VO-Agent-Id` 验证该 Agent 是当前会议参与者或执行者，并保存 `meetingId`、创建时会议 version、暂停前 stage。客户端提供的 version 只作提示，不能替代仓库校验。

### 项目任务

创建请求使用：

```json
{"source":{"type":"task","id":"<taskId>","projectId":"<projectId>","label":"<task title>"}}
```

后端验证项目与任务存在、任务属于该项目、可信 Agent 是当前 executor，并绑定当前 `attemptId`、`stageRunId` 或 legacy workflow session key。`projectId` 纳入 source 规范化与安全投影；内部 attempt/session 标识不公开。

如果无法唯一定位活动会议或任务 attempt，创建决策仍可成功并投递给用户，但续跑绑定标记为不可自动恢复，避免猜测目标。

## 会议续跑流程

1. 会议 Agent 创建决策时，会议存储原子转为 `awaiting_user_decision`，保留 `decisionForStage` 和 decision ID。会议运行器结束当前 step，不把等待回复当成正常会议产出。
2. 用户提交后，统一工作流领取续跑任务，重新读取会议。
3. 若会议仍为相同 decision ID 的 `awaiting_user_decision`，通过现有 `MeetingLifecycleService.transition_command` 执行 `continue_decision`。幂等键固定为 `human-decision-resume:{decisionId}`。
4. 会议恢复 Prompt 在可信指令中要求从 `decisionForStage` 继续；`resolution.answer`、原情景和任务详情放入 XML 不可信数据区。
5. 原生 transition 与运行器唤醒均成功后，续跑状态才写为 `completed`。若 transition 已由同一幂等键完成，则按幂等成功处理。
6. 会议已终止或已被其他操作推进到不相容阶段时写 `failed`，不得倒退阶段。

会议详情与 Dashboard 继续使用现有 SSE 投影；无需新增前端实时通道。

## 项目任务续跑流程

### 等待标记

新增聚焦模块 `project_human_decision_continuation.py`，只负责项目任务等待与恢复的状态转换。它通过注入的 `ProjectRepository`、runner/dispatcher 和时钟工作，不导入 `app/server.py`。

当项目 executor 创建决策时：

1. 当前 attempt 写入 `status=awaiting_user_decision`、decision ID、等待时间和原执行模式；
2. task 保留 `activeAttemptId`，因此 stage reconciliation 不会把该 task 视为 accepted terminal；
3. 当前 Provider call 返回后，execution runner 检查该 attempt 的等待标记并退出，不进入 review、done 或失败处理；
4. 同 stage 的其他 dispatcher item 不受影响。

Legacy workflow 同样在调用 Agent 后检查等待标记：保留任务在 In Progress，持久化 `workflowPhase=awaiting_user_decision`，结束当前后台线程，不移动到 Review。

### 恢复执行

用户提交后：

1. 续跑器重新读取 project/task/attempt，并验证 decision ID、Agent、run ID 和 active attempt 仍匹配；
2. 对 stage/direct execution，复用原 attempt 的 conversation ID 与 workspace，向现有 execution runner 提交一个 `decision_resume` 工作项；不新建项目 stage，也不重新提交兄弟 task；
3. 对 legacy workflow，复用原 task session key，从保存的 phase 进入 task 执行后的既有 review 流程；
4. 恢复 Prompt 使用共享 formatter 构造 XML，包含规范化答案、原情景、已完成工作边界与“继续原 task、不要重做已完成副作用”的可信规则；
5. runner 接收恢复后清除等待标记并继续原有 checklist/review/reconciliation；
6. 决策重复投递通过 `decisionId + attemptId` 幂等；活动 attempt 已有恢复 worker 时不再提交。

项目任务等待是非终态。阶段推进、项目完成报告和成功通知都必须等待该 task 完成原有验收流程。

## 组件边界

### `human_decision_continuation_dispatch.py`

新增通用分派器：根据 binding kind 调用 chat、meeting 或 task adapter；负责 claim、重试分类和安全摘要，不包含会议/项目业务状态转换。

### `human_decision_meeting_continuation.py`

新增会议适配器：校验会议绑定、执行原生 `continue_decision`、构造 XML 恢复上下文并触发会议 runner。

### `project_human_decision_continuation.py`

新增项目适配器：标记 attempt/session 等待、恢复单 task、处理绑定漂移与幂等。项目 dispatcher 与 execution lifecycle 仍是唯一执行引擎。

### 现有大文件

`app/server.py` 只增加依赖装配、薄路由委托和 callback wiring。会议、项目和续跑状态机逻辑不进入该文件。

## 并发、失败与恢复

- resolve 与原 Agent 返回并发：等待标记和 resolve 均落盘；续跑 worker 只有在原 Provider call 已退出或确认可接管后才恢复，否则进入短暂 `retry_wait`。
- 服务在 resolve 后重启：启动扫描领取 `queued/retry_wait`；持久化 meeting/task marker 用于重建上下文。
- Provider 调用前失败：可有界重试三次。
- Provider 调用后结果未知：写 `uncertain`，不自动再次产生副作用。
- 用户手动推进会议或任务：适配器重新读取权威状态；相同决策已应用视为成功，不相容推进视为 `failed`。
- 项目 attempt 被取消、替换或 stage run 改变：拒绝恢复旧 attempt，不创建新 attempt 猜测用户意图。
- 超时按决策本身既有三次提醒与最终策略 resolve；进入终态后走同一续跑路径。

## Prompt 与 Skill 调整

1. `vo-human-decision` 不再要求会议/任务轮询；三种来源创建成功后都结束当前受影响 turn，由后端恢复。
2. 会议 Prompt 明确真实 `meetingId`；项目执行与 workflow Prompt 明确 `projectId`、`taskId`、`attemptId/session scope`，供 Skill 填写来源，但内部不可伪造的绑定仍由后端校验。
3. 恢复 Prompt 全部通过 `services.bridge_input_output_formatting` 组装。最终答案作为 untrusted text/JSON，不与系统规则拼接。

## 测试策略

- Store：三种 binding、私有字段过滤、原子 claim、租约、重启恢复、重复 resolve。
- Meeting：创建即进入等待；resolve 只调用一次 `continue_decision`；保留 `decisionForStage`；已终止/版本漂移不倒退；SSE 投影更新。
- Stage project：一个 task 等待时兄弟 task 继续；reconciliation 不提前推进；resolve 只恢复原 attempt；重复回调不重复提交。
- Direct project：非 stage task 保留 active attempt 并从原 conversation 恢复。
- Legacy workflow：等待后不进入 Review；resolve 复用原 session，从正确 phase 继续。
- Prompt security：meeting/project 动态答案无法闭合 XML 可信标签。
- 集成：飞书与本地 resolve 等价；页面关闭与服务重启可恢复；未知投递不重复。
- 回归：聊天自动续跑、项目 pause/resume、会议生命周期、项目 checklist/review、Dashboard SSE 全部保持通过。

## 非目标

- 不把人工决策替换为飞书审批流。
- 不为该能力新增第二条 SSE 或第二个项目 dispatcher。
- 不自动恢复已被用户取消、替换或推进到其他阶段的旧分支。
- 不允许 Agent 自己 resolve、reopen 或伪造用户答案。
- 不改变整项目运维 pause/resume 的既有语义。
