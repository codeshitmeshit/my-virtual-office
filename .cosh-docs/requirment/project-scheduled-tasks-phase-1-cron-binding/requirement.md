# 项目定时任务 Phase 1：扩展现有 Cron 支持项目绑定

## 父需求

- 父需求：`project-scheduled-tasks`
- 父需求阶段：Phase 1：扩展现有 Cron 支持项目绑定
- 父需求关联 TODO：TODO-001 至 TODO-006
- 父需求关联 checklist：CHK-001 至 CHK-006

## 背景

项目定时任务整体需求已经拆成 5 个 phase。Phase 1 的目标不是重新实现一套 scheduler，而是在现有 Cron 能力上增加项目绑定语义，让 cron job 可以保存并校验 `projectId`、`targetType` 和可选 `taskId`。

当前代码中，`app/cron.html` 已经通过 WebSocket gateway 调用 `cron.list`、`cron.add`、`cron.update`、`cron.remove`、`cron.run`。但在本仓库内没有直接找到这些 `cron.*` 方法的后端实现，说明它们很可能由 OpenClaw gateway/provider 处理，Virtual Office 只是通过 WebSocket 代理连接。

因此 Phase 1 的第一步必须先确认现有 Cron 的真实所有权和存储位置，然后再选择最小改动方案：

- 如果 gateway/provider 原生支持扩展字段，应直接在现有 cron job 上保存项目绑定 metadata。
- 如果 gateway/provider 不支持项目元数据或不可靠保留未知字段，则 Virtual Office 需要增加兼容映射层，保存 `cronJobId -> project binding metadata`。
- 无论采用哪种方式，都不能破坏现有 Agent 级 Cron Manager。

## 目标

- 复用现有 Cron 作为底层调度器，不重做 scheduler。
- 支持保存项目绑定元数据：
  - `projectId`
  - `targetType`: `projectWorkflow` 或 `projectTask`
  - `taskId`: 仅 `projectTask` 需要
  - 可选 `scope` 或等价字段，用于区分普通 Agent cron 和项目定时任务
- 支持创建、查询、更新、启用/禁用、删除带项目绑定的 cron job。
- 保证项目绑定元数据在服务重启或 cron 存储重载后仍可恢复。
- 校验项目存在且满足“有负责人或绑定 Agent”的配置条件。
- 校验指定任务存在且属于当前项目。
- 复用现有 schedule 校验，不重新定义 cron、循环间隔或一次性时间规则。
- 保证普通 Agent 级 cron 行为不受影响。

## 范围

### 本期包含

- 梳理现有 Cron RPC、存储、运行状态字段和 gateway 所有权。
- 定义项目绑定元数据保存位置：
  - 优先保存在现有 cron job metadata/payload 中。
  - 如果不可行，则在 VO 侧保存兼容绑定表。
- 扩展创建/更新/列表/删除/启停项目绑定 cron 的后端能力。
- 增加项目资格校验。
- 增加目标类型和 `taskId` 校验。
- 增加持久化兼容读取逻辑。
- 增加 Phase 1 自动化测试。

### 本期不包含

- 不实现到期后启动项目 workflow。
- 不实现到期后启动指定项目任务。
- 不实现项目详情页 UI。
- 不实现执行历史。
- 不实现控制面板异常提示。
- 不实现长期项目推荐。
- 不重命名 Cron Manager，不改造成通用自动化平台。

## 关键约束

- 必须兼容现有 `/cron.html` 普通 Agent 级 cron。
- 不带 `projectId` 的旧 cron job 必须正常工作。
- 带项目绑定的 cron job 在 Phase 1 只要求可保存和管理，不要求真实派发项目执行。
- 如果 gateway 不保留未知字段，需要明确记录并采用 VO 侧绑定表方案。
- 所有校验失败都应返回清晰错误，不能保存半成品绑定记录。

## 验收标准

- 能定位并记录现有 Cron 的存储/RPC 所有权。
- 能创建带项目绑定元数据的 cron job。
- 能查询并区分普通 Agent cron 和项目绑定 cron。
- 能更新、启用/禁用、删除项目绑定 cron。
- 项目绑定元数据可持久化。
- 不满足配置条件的项目无法创建项目绑定 cron。
- 非法 `targetType`、不存在任务、其他项目任务会被拒绝。
- 普通 Agent 级 cron 不受影响。

