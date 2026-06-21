# 项目定时任务 Phase 4 Checklist

确认状态：已确认

## 执行历史

- [x] CHK-001 项目定时任务每次派发决策都会写入项目执行历史。
  - 验证方法：分别触发 whole-project cron 和 project-task cron 的立即运行或 due dispatch。
  - 预期结果：项目详情可查询到对应历史记录，包含 cronId、定时任务名称、项目、目标类型、目标任务、时间和状态。
  - 关联需求点：项目详情页展示定时执行历史。

- [x] CHK-002 started 状态历史记录展示清晰。
  - 验证方法：触发项目空闲时的 whole-project cron 和可执行任务 cron。
  - 预期结果：历史记录显示为已启动，并能看出启动的是整个项目 workflow 还是指定任务。
  - 关联需求点：用户能知道定时任务真实推进了项目。

- [x] CHK-003 skipped 状态记录用户可理解的原因。
  - 验证方法：构造 project_active、task_completed_repeat_disabled、target missing 等跳过场景。
  - 预期结果：项目历史展示中文可理解原因，不只展示内部 code。
  - 关联需求点：用户知道为什么没执行。

- [x] CHK-004 paused 状态进入项目历史但不算失败。
  - 验证方法：暂停项目定时任务后触发 run-now 或 due dispatch。
  - 预期结果：项目历史记录 paused 或 skipped-paused，控制面板不出现失败提示。
  - 关联需求点：项目级暂停是正常控制行为。

- [x] CHK-005 failed 状态进入项目历史并保留错误上下文。
  - 验证方法：模拟 gateway 失败、项目缺失或派发异常。
  - 预期结果：历史记录展示 failed、错误摘要、失败时间和关联定时任务。
  - 关联需求点：失败可排查。

- [x] CHK-006 intervention_required 状态进入项目历史。
  - 验证方法：模拟需要用户确认或人工处理的定时任务结果。
  - 预期结果：历史记录显示需要人工介入，并说明需要处理的上下文。
  - 关联需求点：人工介入可见。

## 控制面板异常提示

- [x] CHK-007 正常 started/completed 不出现在控制面板异常提示中。
  - 验证方法：触发成功启动和完成流程后查看控制面板。
  - 预期结果：项目历史有记录，控制面板没有异常提示。
  - 关联需求点：避免控制面板噪音。

- [x] CHK-008 正常 skipped/paused 不出现在控制面板异常提示中。
  - 验证方法：触发 project_active、paused、repeat disabled 等正常跳过场景。
  - 预期结果：项目历史有记录，控制面板没有异常提示。
  - 关联需求点：控制面板只提示需要处理的问题。

- [x] CHK-009 failed 会出现在控制面板异常提示中。
  - 验证方法：制造一次项目定时任务失败后打开控制面板。
  - 预期结果：控制面板显示项目定时任务失败，包含项目名、定时任务名、目标、原因和时间。
  - 关联需求点：失败需要负责人可见。

- [x] CHK-010 intervention_required 会出现在控制面板异常提示中。
  - 验证方法：模拟人工介入状态后查看控制面板。
  - 预期结果：控制面板显示需要人工介入，并可定位到项目。
  - 关联需求点：人工介入提示。

- [x] CHK-011 控制面板异常提示可定位回项目。
  - 验证方法：点击或使用提示中的项目定位入口。
  - 预期结果：能进入对应项目详情，用户能继续查看历史和定时任务。
  - 关联需求点：异常可处理。

## 历史列表体验

- [x] CHK-012 项目详情页展示最近执行历史。
  - 验证方法：打开有多个项目定时任务历史的项目详情页。
  - 预期结果：历史按时间倒序展示，信息密度可读，不遮挡现有定时任务列表和看板。
  - 关联需求点：项目级执行历史 UI。

- [x] CHK-013 历史列表支持基本过滤或状态区分。
  - 验证方法：查看包含 started、skipped、failed、intervention_required 的历史列表。
  - 预期结果：用户可以通过标签、颜色、状态文案或过滤控件区分不同状态。
  - 关联需求点：长期历史可读性。

- [x] CHK-014 历史记录数量有上限或截断策略。
  - 验证方法：构造超过保留上限的历史记录。
  - 预期结果：项目存储或 UI 只保留/展示最近记录，页面加载正常。
  - 关联需求点：长期项目性能和可读性。

- [x] CHK-015 旧项目没有历史字段时正常加载。
  - 验证方法：打开没有 `scheduledCronHistory` 或等价字段的旧项目。
  - 预期结果：项目详情无报错，历史区域显示空状态或不展示。
  - 关联需求点：兼容旧数据。

## 诊断与回归

- [x] CHK-016 服务端诊断信息覆盖关键上下文。
  - 验证方法：触发 started、skipped、failed 后查看日志或调试输出。
  - 预期结果：日志包含 projectId、cronId、targetType、taskId、decision、reason、error、timestamp。
  - 关联需求点：可观测性。

- [x] CHK-017 普通 Agent cron 不进入项目执行历史。
  - 验证方法：创建并运行普通 Agent cron。
  - 预期结果：不会写入任何项目的定时执行历史，普通 cron 行为不退化。
  - 关联需求点：兼容现有 Cron Manager。

- [x] CHK-018 Phase 2+3 既有项目定时任务能力不退化。
  - 验证方法：复测创建、编辑、启用/禁用、删除、立即运行、项目级暂停/恢复、重复触发开关。
  - 预期结果：既有能力保持可用。
  - 关联需求点：回归保护。

- [x] CHK-019 自动化测试覆盖核心历史和异常提示场景。
  - 验证方法：运行新增测试和相关项目定时任务测试。
  - 预期结果：测试覆盖 started、skipped、paused、failed、intervention_required、截断和旧项目兼容。
  - 关联需求点：测试可靠性。

- [x] CHK-020 8090 live 验收覆盖项目历史和控制面板异常提示。
  - 验证方法：在 8090 真实环境创建项目定时任务并触发成功、跳过、失败或人工介入场景。
  - 预期结果：项目详情历史和控制面板提示符合预期。
  - 关联需求点：人工验收。

## 人工确认记录

- checklist 确认：2026-06-18T22:11:20+08:00，用户回复 “continue”，确认 Phase 4 checklist，可以生成 todolist。
- tested 确认：2026-06-19T00:55:00+08:00，用户回复“先将phase4归档吧”，确认 Phase 4 测试和验收通过。
- done 确认：2026-06-19T00:55:00+08:00，用户要求归档 Phase 4，确认项目定时任务执行历史、控制面板异常提示和诊断日志子需求完成。

## 测试记录

- 自动化测试：2026-06-19T00:50:45+08:00，`python3 -m py_compile app/server.py app/project_store.py tests/test_project_scheduled_cron_phase4.py` 通过。
- 自动化测试：2026-06-19T00:50:45+08:00，`node --check app/projects.js` 通过。
- 自动化测试：2026-06-19T00:50:45+08:00，`.venv/bin/python tests/test_project_scheduled_cron_phase4.py` 通过，覆盖 started、skipped、paused、failed、intervention_required、历史截断和持久化。
- 回归测试：2026-06-19T00:40:58+08:00，`.venv/bin/python tests/test_project_scheduled_cron_phase2_3.py` 通过。
- 8090 live 验收：2026-06-19T00:45-00:50+08:00，使用 `VO_PORT=8090 VO_WS_PORT=8091 VO_STATUS_DIR=/tmp/vo-phase4-history-alerts ./start.sh` 启动真实服务；通过 HTTP API 创建项目、任务和项目定时任务，run-now 写入 paused 与 no_eligible_task 历史；项目列表摘要返回 `scheduledCronAlertCount: 0`，验证正常 skipped/paused 不进入控制面板异常提示。
- Chrome MCP 验收说明：2026-06-19T00:48+08:00，尝试使用 chrome-devtools MCP 打开 8090 页面时 profile 被已有实例占用，未能完成截图验收；本轮以真实 8090 HTTP API、服务端 dispatch 日志和自动化 UI 语法检查作为替代验收。
