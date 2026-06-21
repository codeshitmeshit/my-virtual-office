# 项目定时任务 Phase 2-3 方案评审

## 评审结论

该子需求可以进入 checklist 草案阶段。Phase 2 和 Phase 3 合并执行是可行的，但需要明确边界：本次只做 UI 可见性、配置体验和项目派发，不做完整执行历史与控制面板异常提示。

主要技术风险在 Phase 3：当前底层 cron 由 gateway/provider 执行，Virtual Office 是否能可靠收到 cron due 事件仍需实现时确认。如果不能直接订阅 cron 事件，就需要 VO 侧轻量协调器，按 `nextRunAt` 或 gateway cron 状态轮询项目绑定 cron 并派发。

## 已完成基础

- Phase 1 已新增项目绑定 cron 后端封装。
- Phase 1 已使用 VO 侧 `project-cron-bindings.json` 保存项目绑定元数据。
- Phase 1 已保持普通 Agent cron 兼容。
- Phase 1 已通过自动化测试和 8090 live 复测。

## 产品评审

### 明确点

- 全局定时任务页必须展示项目绑定 cron。
- 项目详情页负责当前项目的创建和管理。
- 全局定时任务页负责系统级总览、过滤和排查。
- 项目 cron 必须显示项目名、目标类型和目标任务。
- 到期执行要真正驱动项目 workflow 或项目任务。

### 产品风险

- 如果全局页和项目页都能创建项目定时任务，用户可能困惑从哪里配置。建议本期可以允许项目页创建，全局页先以总览和管理为主；是否全局创建可作为实现时的低优先选项。
- 如果 Phase 3 派发成功但没有完整历史，用户仍可能不知道执行细节。可以先显示基础 lastStatus/lastRun，完整历史留到 Phase 4。
- 如果项目 cron 在 `/cron.html` 中看起来和普通 Agent cron 一样，会产生风险。需要明显类型标识。

## 技术评审

### UI 方向

项目详情页：

- 使用 Phase 1 API 管理当前项目的 scheduled cron。
- 复用现有项目任务列表作为 `projectTask` 目标选择来源。
- 提供 whole-project 和 project-task 两种目标。
- 提供 schedule、enabled、message、agent 等必要字段。

全局 `/cron.html`：

- 继续通过 gateway `cron.list` 加载普通 cron。
- 额外加载项目列表和每个项目的 scheduled cron，或新增聚合 API。
- 合并渲染普通 Agent cron 和项目绑定 cron。
- 项目绑定 cron 显示项目名、目标类型、目标任务。
- 支持过滤：
  - 全部
  - Agent cron
  - Project cron
  - 指定项目

### 派发方向

优先选择可靠的实现路径：

1. 如果 gateway 能发 cron event 且 VO WebSocket proxy/observer 能识别 project-bound cron，直接在事件中派发。
2. 如果 gateway 只执行普通 prompt，不提供 due event，VO 增加轻量调度协调器：
   - 周期性读取项目绑定 cron 和 gateway cron 状态。
   - 判断 due 或 lastRun 变化。
   - 对 project-bound cron 执行项目派发。

派发行为：

- `projectWorkflow`：
  - 项目 workflow 空闲：调用现有 workflow start。
  - 项目 workflow 已运行：跳过并记录 `skipped`。
- `projectTask`：
  - 调用现有任务项目执行 start。
- 保护条件：
  - 项目暂停。
  - 项目删除。
  - 项目归档。
  - 任务缺失。
  - 项目不再满足 owner/bound agent 条件。

### 状态更新

Phase 3 至少要维护：

- `lastRunAt`
- `lastStatus`
- `lastError`
- `nextRunAt` 或等价展示字段

完整执行历史和控制面板异常提示留到 Phase 4。

## 风险与缓解

- 风险：无法可靠判断 gateway cron due。
  - 缓解：实现 VO 侧协调器时可在 Phase 3 只负责 project-bound cron，普通 Agent cron 继续由 gateway 处理。
- 风险：项目 workflow start 和 project execution start 语义不同。
  - 缓解：whole-project 使用现有 workflow start；specific-task 使用现有 task project-execution start。
- 风险：全局页数据多次加载造成慢。
  - 缓解：可以新增聚合 API，或先批量加载项目 summaries 后按绑定表关联。
- 风险：新增 UI 影响普通 Cron Manager。
  - 缓解：普通 Agent cron 保持原卡片信息，项目 cron 只添加额外 badge/filter，不改原流程。

## 非阻塞技术澄清

- 全局 `/cron.html` 是否允许创建项目 cron？建议本子需求必做总览/过滤/管理，项目页必做创建；全局创建可选。
- 项目级暂停字段目前是否已有？如果没有，本期可新增轻量项目字段。
- `nextRunAt` 是否来自 gateway state 还是 VO 侧计算？实现时以可稳定展示为准。

## 评审结论

可以生成 checklist 草案。Checklist 确认后再生成 todolist 并进入实现。

