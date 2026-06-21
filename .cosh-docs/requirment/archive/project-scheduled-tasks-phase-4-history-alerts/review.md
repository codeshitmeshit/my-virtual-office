# 项目定时任务 Phase 4 Review

## 产品评审

### 结论

产品目标清晰：Phase 4 不再扩展“怎么创建和触发项目定时任务”，而是补齐执行后的可见性、异常提示和排查能力。

### 产品边界

- 控制面板不是执行流水账，只提示需要处理的异常。
- 项目详情页才是执行历史的主承载位置。
- skipped 不一定是错误，必须区分正常跳过和异常失败。
- 历史记录要服务长期项目，不能无限堆满页面。

### 产品风险

- 如果所有运行都提示到控制面板，会形成噪音，违背父需求。
- 如果 skipped 原因只显示内部 code，用户无法理解。
- 如果失败只在日志里，不在控制面板，项目负责人可能无法发现。
- 如果历史记录没有上限，长期项目会出现性能和可读性问题。

## 技术评审

### 数据模型建议

建议在项目数据中新增项目定时执行历史，例如：

```json
{
  "scheduledCronHistory": [
    {
      "id": "uuid",
      "cronId": "cron-id",
      "cronName": "Daily project run",
      "projectId": "project-id",
      "targetType": "projectWorkflow",
      "taskId": null,
      "taskTitle": "",
      "status": "started",
      "reason": "",
      "message": "Started project workflow",
      "error": null,
      "startedAt": "iso",
      "finishedAt": "iso",
      "durationMs": 1200,
      "source": "manual|due",
      "createdAt": "iso"
    }
  ]
}
```

也可以将历史独立保存到 status 目录文件中，以减少项目 markdown frontmatter 压力。选择时需要遵守现有项目存储模式。

### 状态语义

建议标准化为：

- `started`：已启动项目 workflow 或任务。
- `completed`：如果现有流程能明确完成，可记录完成。
- `skipped`：正常跳过，不提示控制面板。
- `paused`：项目级暂停导致不派发，不提示控制面板。
- `failed`：派发失败或运行失败，提示控制面板。
- `intervention_required`：需要用户处理，提示控制面板。

### 原因映射

需要把内部 reason 映射为用户可读文案：

- `project_active` -> 项目已有 workflow 正在运行，本次跳过。
- `project_cron_paused` -> 项目定时任务已暂停。
- `task_missing` -> 指定任务不存在。
- `project_archived` -> 项目已归档。
- `task_completed_repeat_disabled` -> 任务已完成，且未开启允许重复触发。
- `project_not_eligible` -> 项目不再满足定时任务配置条件。
- `gateway_error` -> Cron 网关调用失败。

### 写入位置

历史写入点应靠近项目 cron 派发结果汇总处，避免 UI 或多个调用方重复拼装历史。`run-now` 和到期调度都应走同一条记录路径。

### 控制面板提示来源

优先复用已有控制面板项目/活动数据源。如果现有控制面板只消费 activity log，可以把 failed/intervention_required 写入一个可识别的 project activity 类型；如果已有独立告警机制，则应接入该机制。不要让普通 started/skipped 写入控制面板异常列表。

### 兼容性

- 旧项目没有 `scheduledCronHistory` 时应默认空数组。
- 历史字段缺失时 UI 不报错。
- 现有项目活动、任务评论和 cron 状态不能被破坏。
- 普通 Agent cron 不应进入项目执行历史。

### 性能

建议每个项目只保留最近 200 条历史，UI 默认展示最近 20-50 条。保存时截断，比前端加载后截断更稳。

### 测试可行性

可以通过现有 fake gateway 和项目存储测试覆盖：

- started 历史写入。
- skipped/paused 历史写入。
- failed 历史写入和控制面板异常源。
- repeat disabled 的 skipped 原因。
- 历史数量截断。
- 旧项目兼容。

### 阻塞问题

暂无阻塞问题。控制面板具体接入点需要实现前读代码确认，但不影响 checklist 生成；可以在 todolist 中作为技术任务拆分。

## 评审结论

可以进入 checklist 阶段。实现应保持 Phase 4 范围克制：先做项目历史、异常提示和诊断，不引入自动重试或复杂通知系统。
