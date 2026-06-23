# Meeting Request Blocks Task Review

## 产品评审

产品语义已经足够明确：AI 会议申请是任务执行中的阻塞型协作机制，而不是提醒。核心目标是防止任务在未统一前继续推进。

关键产品判断：

- 会议申请创建代表当前任务存在无法单独推进的问题。
- 等待会议时任务仍属于 In Progress，而不是 Review 或 Done。
- 会议完成不等于可继续；必须有明确“已达成一致，可以继续执行”的结果。
- 会议拒绝、超时、无共识都不能自动放行任务。
- 用户必须有人工接管入口，避免任务永久卡死。

无剩余阻塞性产品歧义。

## 当前系统观察

相关现状：

- `app/server.py` 已有会议申请创建、确认、拒绝和会议创建逻辑。
- `app/server.py` 的 Project Execution 状态机已有 `executing`、`reviewing`、`reworking`、`awaiting_user_acceptance`、`blocked` 等状态。
- 会议申请当前仅写入 `meeting-requests.json`，不更新任务 `executionState`。
- 会议申请确认会创建 executable meeting，但不会把会议结果同步回项目任务。
- 项目执行 pipeline 当前没有 `awaiting_meeting_resolution` 或等价分支。
- 前端任务详情会展示 AI 会议申请，但没有阻塞状态说明和用户接管操作。

## 建议方案

建议引入产品语义明确的任务等待状态：

- `executionState: awaiting_meeting_resolution`
- 任务仍位于 In Progress 列。
- `workflowPhase` 同步为 `awaiting_meeting_resolution`。
- 任务记录当前阻塞会议申请或会议引用，例如 `meetingBlocker`。

会议申请创建规则：

- 创建项目任务会议申请时，若任务已有未解决阻塞型会议申请，则拒绝创建或返回现有申请。
- 创建成功后，任务转入 `awaiting_meeting_resolution`。
- 项目 workflow 保持 active 但暂停推进，或 active=false 并带明确 stop reason；产品上必须显示“等待会议结论”。

会议结果回写规则：

- 会议明确结果为 `resolved_continue` 或同等语义时，任务恢复执行。
- 会议结果为 `no_consensus` 时，任务转为 `blocked`。
- 会议结果为 `needs_user_decision` 时，任务保持等待用户处理。
- 会议申请被拒绝时，任务保持等待用户处理，并显示拒绝原因。
- 会议准备超时或确认超时，不自动继续，显示等待用户处理。

用户接管入口：

- 继续执行：用户明确覆盖会议阻塞，任务回到可执行状态并记录 override。
- 标记阻塞：任务进入 Blocked，并记录原因。
- 重新申请会议：清理或替换旧的未解决申请，创建新的阻塞会议申请。

## 技术评审

需要关注的实现点：

- 状态机：`_project_execution_transition`、active task 判断、可启动判断、workflow pipeline 都需要识别 `awaiting_meeting_resolution`。
- 数据一致性：会议申请 store 与项目 store 是两个文件，需要确保更新顺序和失败回滚策略。
- 会议结果判定：不能依赖任意 summary 文本；需要会议结果里有可枚举 outcome。
- UI：任务详情、任务卡、执行状态 badge、会议申请区都需要展示等待状态和可操作入口。
- 并发：同一任务只能有一个 unresolved blocking meeting request。
- 回归：不要影响普通会议、非项目会议、非会议阻塞的任务执行流程。
- 本地化：新增状态和操作文案需要中英文。

## 风险

- 如果会议结果没有结构化 outcome，系统可能误判是否恢复执行。
- 如果创建会议申请和更新任务状态中途失败，可能出现会议申请存在但任务未暂停。
- 如果用户接管入口过弱，任务可能长期卡在等待状态。
- 如果 pipeline 不把等待会议视作 active task，可能继续拉取 backlog 任务。

## 评审结论

方案可行，暂无阻塞性技术问题。需要在 checklist 中重点验证状态联动、会议结果回写、拒绝/超时场景、用户接管和回归路径。

## 追加评审：会议申请队列 UI

用户后续验收中补充了会议申请队列的交互要求，这些要求与“会议申请阻塞任务”的同一产品语义相关，属于同一需求的 UI 完善，不单独拆需求。

补充判断：

- 会议申请的处理状态比时间更重要：待处理申请必须优先展示，避免被较新的已处理申请压下去。
- 申请详情包含目标、期望产物、原因、参与人、主持人、上下文候选和确认/拒绝操作，不适合全部铺在列表里。
- 列表应作为扫描入口，只保留摘要；详情和处理动作应放入 VO 风格弹窗。
- 状态颜色应在会议申请队列和项目任务详情中保持一致，降低误判风险。
- 侧边栏待处理数量是提醒信息，应压缩到同一行右侧气泡，避免增加列表高度。

补充技术结论：

- 排序应以后端 `/api/meetings/requests` 为主，前端列表做兜底排序，确保会议队列和项目详情一致。
- 弹窗可以复用会议详情 modal 风格，不改变会议申请确认/拒绝 API。
- 状态颜色通过稳定 class 映射到 `pending`、`confirmed`、`rejected`，不改变数据结构。
- 侧边栏数量仅是展示改动，不影响 pendingCount 语义。
