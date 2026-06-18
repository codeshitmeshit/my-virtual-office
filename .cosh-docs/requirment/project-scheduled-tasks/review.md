# 项目定时任务方案评审

## 评审结论

产品需求已经足够清楚，可以进入 checklist 确认阶段。该需求影响持久化、项目 UI、调度执行、项目 workflow/任务执行状态、控制面板提示和回归测试，因此需要拆成 5 个 phase 实施。

当前没有阻塞性的产品澄清问题。

## 当前系统观察

- 现有 Cron Manager 是 Agent 级能力，`app/cron.html` 通过 `cron.*` WebSocket RPC 管理定时任务。
- 现有 Cron Manager 的 payload 主要是 Agent 或 system prompt，没有项目绑定字段。
- `app/server.py` 已经有项目 CRUD、workflow start/stop/status、项目执行、任务执行、artifact/status 等项目相关接口。
- `app/projects.js` 已经有项目 workflow 和项目执行相关前端操作。
- 项目持久化主要由 `app/project_store.py` 负责，通过 markdown/frontmatter 保存项目数据。
- 现有文档中已经出现过带 `projectId` 的 `OfficeAutomation` 方向，但本需求应保持在“项目定时任务”范围内，不提前扩展成通用自动化平台。

## 产品评审

### 已明确

- 该能力归属于项目，不是给 Agent 发 prompt 的普通 cron。
- 主要使用者是项目负责人。
- 项目必须有负责人或绑定 Agent 才能配置。
- 第一版支持整个项目 workflow 和指定项目任务两类目标。
- workflow 已运行时应跳过并记录，不重复启动。
- 项目详情页展示完整执行历史。
- 控制面板只显示异常状态。
- 需要项目级暂停/恢复总开关。

### 产品风险

- 最大风险是范围膨胀成通用自动化平台。
- 指定任务重复执行可能和普通一次性任务混淆。
- 如果正常执行也频繁进入控制面板，会造成提醒噪音。
- 如果自动执行没有清晰历史记录，用户会不知道系统到底做了什么。

### 产品边界建议

- 功能名称和入口保持“项目定时任务”。
- 正常执行记录只放在项目详情页。
- 控制面板只展示失败和需要人工介入。
- 长期项目只推荐创建，不自动启用。
- provider-neutral automation 作为未来方向，不纳入本次核心范围。

## 技术评审

### 架构方向

架构上应把现有 Cron 视为底层调度器，而不是重新实现一套定时系统。项目定时任务应优先扩展现有 cron job 的元数据和 payload 语义，让同一个 cron 基础能力可以表达项目绑定、项目目标和后续项目执行动作。

现有 Cron Manager 可以继续保持 Agent 级能力。项目定时任务不应要求用户把项目名称写进普通 Agent prompt，而应显式保存 `projectId`、`targetType` 和可选 `taskId`。到 Phase 3 再让到期 cron job 派发到项目 workflow 或指定项目任务。

### 持久化建议

建议在现有 cron job 结构上增加项目绑定元数据：

- `id`
- `projectId`
- `name`
- `enabled`
- `schedule`
- `scope` 或等价字段：普通 Agent cron / 项目定时任务
- `targetType`：`projectWorkflow` 或 `projectTask`
- `taskId`：目标为 `projectTask` 时使用
- `agentId`：如 UI/执行策略需要，可作为可选覆盖
- `message`：可选执行说明
- `lastRunAt`
- `nextRunAt`
- `lastStatus`
- `createdAt`
- `updatedAt`

Phase 1 不要求新增独立 scheduler，也不要求真实启动项目 workflow。它的核心是让现有 cron job 能稳定保存、查询、更新项目绑定信息，并且不破坏已有 Agent 级 cron。

建议保存项目定时执行记录：

- `id`
- `scheduledTaskId`
- `projectId`
- `taskId`：可选
- `status`：`triggered`、`started`、`skipped`、`failed`、`completed`、`intervention_required`
- `reason`
- `startedAt`
- `finishedAt`
- `error`
- `linkedAttemptId` 或 workflow run 关联信息

具体存储位置应遵循现有项目 markdown 存储风格，但必须保证记录归属于项目，并且服务重启后仍可恢复。

### 状态流

- 创建、更新、删除带项目绑定元数据的 cron job。
- 复用现有 Cron 能力计算下一次到期时间。
- 如果项目级定时任务被暂停，到期任务不得启动。
- 到期时：
  - 校验项目存在。
  - 校验项目仍满足负责人或绑定 Agent 条件。
  - 如果目标是指定任务，校验任务存在且属于当前项目。
  - 如果目标是整个项目：
    - 检查 workflow 是否已运行。
    - 空闲时启动 workflow。
    - 已运行时跳过并记录。
  - 如果目标是任务：
    - 复用现有任务执行流程启动该任务。
  - 记录执行结果。
  - 更新 last/next run 字段。
  - 只有失败或需要人工介入时写入控制面板提示。

### 兼容性

- 现有 Agent 级 Cron Manager 必须继续可用。
- 没有定时任务字段的旧项目必须正常加载。
- 现有项目 workflow 和项目执行行为不能因为新增定时任务而改变，除非是被定时任务显式触发。
- 项目存储迁移必须是增量式的，并能容忍字段缺失。

### 权限与控制

- 配置项目定时任务应等同于编辑项目的权限。
- 调度器不得执行已删除项目、已删除任务、暂停项目、归档项目或不再满足条件的项目。
- 控制面板提示不应泄露超出现有权限可见范围的项目详情。

### 可观测性

每一次调度决策都应留下足够信息：

- 到期并触发。
- 因 workflow 已运行而跳过。
- 失败及失败原因。
- 需要人工介入。
- 如果能可靠检测完成，则记录完成。

服务端日志也应保留简洁诊断信息，便于定位调度问题。

### 可测试性

该需求可以分阶段测试：

- 扩展现有 Cron 元数据的 CRUD 和持久化测试。
- UI 表单和状态展示测试。
- 可控时间下的调度到期测试。
- workflow 已运行时的跳过测试。
- 指定任务派发测试。
- 项目历史和控制面板异常提示测试。
- 现有 Cron Manager 与项目执行回归测试。

## Phase 评审

### Phase 1 评审

先扩展现有 Cron 的元数据和校验能力，降低后续 UI 与调度派发的不确定性。该阶段不启动真实项目执行，也不另起一套 scheduler。

### Phase 2 评审

现有 Cron 扩展稳定后再做项目详情页。UI 必须保持项目场景，不引入通用自动化平台心智。

### Phase 3 评审

调度派发会启动真实项目工作，必须在数据模型和 UI 已清楚后实现。重点防止重复启动 workflow。

### Phase 4 评审

执行历史和控制面板提示是用户信任基础。应在调度能真实运行后实现，但必须早于最终打磨。

### Phase 5 评审

长期项目推荐、本地化、兼容和回归加固放在最后，避免在核心语义未稳定时过早打磨。

## 非阻塞技术澄清

- 如果当前项目模型没有明确 owner 字段，第一版可以先使用绑定 Agent 作为可配置条件。
- 项目暂停后，到期任务是记录为 `skipped` 还是完全不记录，可以在实现时选择低噪音方案，但必须保证不会执行。
- 整个项目 workflow 的完成状态如果早期无法可靠检测，可以先记录触发、启动、跳过、失败，等可观测状态稳定后再补 completed。

## 评审结论

可以进入 checklist 确认。该需求较大，但按 5 个 phase 拆分后可以降低实现风险。Checklist 确认前不生成 todolist。
