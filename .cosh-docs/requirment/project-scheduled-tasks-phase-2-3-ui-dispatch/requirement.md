# 项目定时任务 Phase 2-3：UI 可见性与项目派发

## 父需求

- 父需求：`project-scheduled-tasks`
- 覆盖阶段：
  - Phase 2：项目详情页配置体验与全局定时任务总览
  - Phase 3：调度派发与项目执行绑定
- 依赖子需求：`project-scheduled-tasks-phase-1-cron-binding`
- 父需求关联 checklist：
  - Phase 2：CHK-007 至 CHK-012、CHK-031 至 CHK-033
  - Phase 3：CHK-013 至 CHK-018

## 背景

Phase 1 已完成后端基础能力：Virtual Office 通过 gateway `cron.*` 复用现有 Cron，并在 VO 侧保存项目绑定元数据。现在项目绑定 cron 可以通过后端 API 创建、查询、更新、删除和 run-now。

当前缺口有两个：

1. 用户在 UI 中看不到项目绑定 cron。尤其是全局定时任务页 `/cron.html` 仍只展示普通 Agent cron，会让用户误以为系统没有项目定时任务。
2. 到期的项目绑定 cron 目前仍只是普通 cron job，没有真正派发到项目 workflow 或指定项目任务。

本子需求把 Phase 2 和 Phase 3 合并执行，目标是让用户能在页面上创建和看到项目定时任务，并让到期 cron 真正驱动项目执行。

## 目标

- 项目详情页可以创建、查看、编辑、启用/禁用、删除、立即运行项目定时任务。
- 全局定时任务页 `/cron.html` 能总览普通 Agent cron 和项目绑定 cron。
- 全局定时任务页能展示项目上下文，包括项目名、目标类型、目标任务名。
- 全局定时任务页支持按任务类型和项目过滤。
- 到期的 `projectWorkflow` cron 能启动项目 workflow。
- 到期的 `projectTask` cron 能启动指定项目任务。
- workflow 已运行时不重复启动，而是跳过并记录状态。
- 项目暂停、删除、归档、任务缺失或项目不再满足条件时，不派发执行。
- 调度后正确维护 last/next run 和状态字段。

## 范围

### 本期包含

- 项目详情页的项目定时任务 UI。
- 全局 `/cron.html` 的项目定时任务可见性和过滤。
- 项目绑定 cron 到期后的派发逻辑。
- whole-project 目标派发到项目 workflow。
- project-task 目标派发到指定任务执行。
- active workflow skip 处理。
- paused/deleted/archived/missing target 保护。
- last/next run 状态更新。
- 中英文文案补充。
- Phase 2+3 自动化测试和 live 验收。

### 本期不包含

- 项目详情页完整执行历史展示。
- 控制面板失败/人工介入提示。
- 长期项目推荐创建定时任务。
- 自动重试策略。
- 把全局 Cron Manager 改名为 Automations。
- 完整 provider-neutral automation 架构。

这些内容留给 Phase 4 和 Phase 5。

## 关键产品要求

- 全局定时任务页是系统级总览，必须展示所有定时任务，包括普通 Agent cron 和项目绑定 cron。
- 项目详情页是项目上下文配置入口，适合创建和管理当前项目的定时任务。
- 项目绑定 cron 必须明显区别于普通 Agent cron，避免用户不知道某个定时任务会影响项目。
- 项目派发必须保守：不能重复启动运行中的 workflow，不能对无效项目或任务执行。

## 关键技术约束

- 继续复用 Phase 1 的 VO 侧项目绑定表。
- 继续复用 gateway `cron.*` 作为底层 Cron 能力。
- 如果无法直接拦截 provider cron 到期事件，需要在 VO 侧实现一个轻量轮询/协调器来识别项目绑定 cron 的 due 状态并执行派发。
- Phase 3 不要求完成 Phase 4 的完整执行历史，但必须留下基本状态用于 UI 和后续历史扩展。
- 普通 Agent cron 行为不能退化。

## 验收标准

- 项目详情页能配置项目定时任务。
- `/cron.html` 能看到项目绑定 cron，并显示项目上下文。
- `/cron.html` 能按类型/项目过滤。
- 到期 whole-project cron 在项目空闲时启动 workflow。
- 到期 whole-project cron 在 workflow 已运行时跳过。
- 到期 project-task cron 启动指定任务。
- 暂停/删除/归档/缺失目标不会派发。
- last/next run 和 lastStatus 更新正确。
- 普通 Agent cron 仍可创建、查看、编辑、运行、删除。

