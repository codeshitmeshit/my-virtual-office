# 项目人工决策任务评论设计

日期：2026-08-08

## 目标

用户完成来源为项目任务的人工决策后，VO 必须在对应任务下写入一条可审计的特殊系统评论。评论记录最终决策，帮助后续执行者、审核者和用户理解任务为何按该方向继续，同时复用现有任务评论存储和项目详情界面。

本设计与会议人工决策讨论轮回写保持一致的内容语义，但项目任务评论是独立的领域投影，不依赖会议事件。

## 已确认的产品行为

1. 决策完成后，对应项目任务评论区新增一条“👤 人工决策”系统评论。
2. 评论只展示决策标题、最终结果和非空的自定义补充。
3. 评论提供“查看决策详情”入口，使用 `decisionId` 打开现有人工决策中枢。
4. 评论不是普通用户手工评论，不把作者保存为 `user`。
5. 飞书或 VO 控制面板提交均产生同一条评论；重复回调、恢复扫描和重试不得重复添加。
6. 评论在权威决策终态确认后写入。后续任务调度暂时失败时评论仍保留，因为用户决策本身已经成立。

## 方案选择

### 采用：复用任务 `comments`，增加结构化决策元数据

现有任务详情、项目仓库和 Markdown 物化已经支持任务评论。新增评论继续进入 `task.comments`，同时保存 `kind=human_decision`、`decisionId`、标题、答案和可选自定义补充。普通评论消费者仍可读取兼容的 `author` 与 `text`；新版 UI 根据 `kind` 呈现系统样式和详情入口。

### 不采用：写入普通纯文本评论

纯文本评论能快速展示，但无法可靠按 `decisionId` 去重、定位详情或进行稳定的 i18n 展示，因此不采用。

### 不采用：新增项目任务时间线存储

为一个现有评论语义新增第二套任务历史会造成重复存储、重复 API 和重复 UI。本需求没有独立时间线的必要，因此不采用。

## 评论模型

任务评论新增兼容字段：

```json
{
  "id": "comment-...",
  "kind": "human_decision",
  "author": "human_decision",
  "text": "最终采用分阶段发布；补充：先覆盖内部租户。",
  "createdAt": "2026-08-08T17:00:00+08:00",
  "decisionId": "decision-...",
  "decisionTitle": "确认发布策略",
  "decisionAnswer": "最终采用分阶段发布",
  "customAnswer": "先覆盖内部租户"
}
```

- `kind` 是 UI 和其他消费者识别特殊评论的稳定类型。
- `author` 保存稳定机器值 `human_decision`；显示名称由 i18n 决定。
- `text` 是向旧客户端和 Markdown 正文提供的可读降级内容。
- `decisionId` 是幂等键和详情跳转参数。
- `decisionAnswer` 是统一决策终态中的规范化 `resolution.answer`。
- `customAnswer` 仅在用户确实提供且不与最终答案重复时保存和显示。

项目 Markdown frontmatter 的 `comments_json` 继续保存完整结构化字段；正文的 Comments 区域继续输出可读 `author + text`，保证命令行和旧读取器可见。

## 组件边界与数据流

新增聚焦模块 `app/services/project_human_decision_comment.py`：

- 输入决策 claim、当前任务和时间/ID 生成器；
- 生成结构化评论；
- 按 `kind=human_decision + decisionId` 查重；
- 不导入 `app/server.py`，不负责调度任务或发送通知。

`ProjectHumanDecisionContinuation.dispatch` 在同一次项目仓库原子更新中：

1. 验证项目、任务、attempt 和 decision ID 仍匹配；
2. 将 attempt 从 `awaiting_user_decision` 更新为 `executing` 并保存 `decisionResume`；
3. 调用评论模块，在目标 task 下确保决策评论存在；
4. 提交仓库更新后，再调用现有 direct/stage dispatcher 恢复任务。

如果 dispatcher 拒绝本次提交，attempt 恢复为等待状态，但已经确认的决策评论不删除。下一次重试通过 `decisionId` 复用原评论。评论的存在不表示任务执行已完成，只表示用户决策已完成。

评论生成需要 ID。通过 `ProjectContinuationPorts` 注入 `new_id`，保持模块可测并复用项目现有 ID 生成能力；不在业务模块内创建新的全局 ID 权威。

## 前端与实时更新

项目详情沿用现有评论列表。`app/projects.js` 根据 `comment.kind` 渲染：

- 标题：`👤 人工决策`；
- 内容：决策标题、最终结果和可选自定义补充；
- 操作：`查看决策详情`；
- 时间：沿用 `createdAt`。

普通评论保持原有作者和 Markdown 展示。项目数据经既有 Dashboard/项目刷新链路更新时，新评论自然进入任务详情；本功能不新增专用 SSE 通道。若任务详情当前已打开，既有项目实时更新必须重新投影该任务评论，用户无需手动重新打开任务。

所有新增文案进入中英文 i18n 字典。评论持久化机器值不写入本地化文本，切换语言后显示名称和字段标签随当前语言变化。

## Prompt 消费

项目任务现有上下文会读取任务评论。结构化评论必须提供兼容 `text`，确保后续执行 Agent、审核 Agent 和工作流 Prompt 能看到最终决策。触及的 Prompt 必须继续通过共享 bridge formatter 构造 XML 外层；评论文本作为动态、不可信数据进入数据边界。

恢复 Prompt 仍以 `attempt.decisionResume.answer` 作为即时权威答案。任务评论用于持久历史和后续执行者参考，不成为第二个决策状态权威。

## 错误与幂等处理

- 项目、任务、attempt 或 decision ID 不匹配时，不写评论，也不恢复任务。
- 相同 `decisionId` 已存在评论时复用，不创建第二条。
- 评论写入与 attempt 恢复准备处于同一仓库原子更新；持久化失败时不调用 dispatcher。
- dispatcher 暂时拒绝不删除评论；重试只改变 attempt 调度状态。
- 旧评论没有 `kind` 时继续按普通评论渲染。
- 详情入口失败不影响评论文本显示。

## 测试策略

1. 单元测试：评论生成器输出结构化字段和兼容文本，空或重复自定义补充不重复展示。
2. 续跑测试：决策恢复准备在目标 task 下追加评论，并且兄弟任务不受影响。
3. 幂等测试：重复 dispatch、调度拒绝后的重试和同一 decision ID 已存在时都只有一条评论。
4. 失败测试：绑定漂移、attempt 被替换和项目持久化失败时不写评论、不调度。
5. Markdown 存储测试：结构化 comment 经保存和读取后保留 `kind`、`decisionId` 与决策字段。
6. UI 测试：特殊评论显示 i18n 标题、最终结果、可选补充和正确详情入口；普通评论无回归。
7. Prompt 测试：后续项目 Agent 上下文包含评论的最终结果，恶意文本不能突破 XML 数据边界。
8. 集成验证：创建真实项目任务，触发并提交人工决策，确认评论出现且任务从同一 attempt 携带该决定继续执行。

## 非目标

- 不新增项目评论 API 或独立评论存储。
- 不展开 ABCD 全部备选项与 VO 推荐。
- 不把任务评论作为任务完成状态或执行成功证明。
- 不向没有明确 `projectId + taskId` 绑定的决策猜测评论目标。
- 不回填历史项目决策。
