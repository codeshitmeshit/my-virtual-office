# 项目定时任务 Phase 2-3 Checklist

确认状态：已确认

## Phase 2：项目详情页配置体验与全局定时任务总览

- [x] CHK-001 项目详情页只对满足条件的项目显示定时任务配置能力。
  - 验证方法：打开满足条件和不满足条件的项目。
  - 预期结果：满足条件项目可配置；不满足条件项目不提供创建入口或显示明确原因。
  - 关联需求点：父需求 CHK-007。

- [x] CHK-002 项目详情页可以创建 whole-project 定时任务。
  - 验证方法：在项目详情页创建目标为整个项目 workflow 的定时任务。
  - 预期结果：创建成功，列表中显示 schedule、enabled、项目目标和下次运行信息。
  - 关联需求点：父需求 CHK-008。

- [x] CHK-003 项目详情页可以创建指定任务定时任务。
  - 验证方法：在项目详情页选择当前项目任务作为目标。
  - 预期结果：只能选择当前项目任务；保存后目标任务显示清楚。
  - 关联需求点：父需求 CHK-009。

- [x] CHK-004 项目详情页支持编辑、启用/禁用、删除和立即运行。
  - 验证方法：逐项操作项目定时任务。
  - 预期结果：UI 和后端数据一致；错误有明确提示。
  - 关联需求点：父需求 CHK-010。

- [x] CHK-005 项目级暂停/恢复影响该项目全部定时任务。
  - 验证方法：暂停项目定时任务后观察列表和派发行为，再恢复。
  - 预期结果：暂停时不派发；恢复后允许继续运行；配置不丢失。
  - 关联需求点：父需求 CHK-011、CHK-016。

- [x] CHK-006 UI 文案保持项目语境并完成中英文。
  - 验证方法：检查项目详情页和全局页新增文案，运行 locale 检查。
  - 预期结果：文案清晰，中文/英文都有覆盖。
  - 关联需求点：父需求 CHK-012、CHK-027。

- [x] CHK-007 全局 `/cron.html` 可以看到项目绑定 cron。
  - 验证方法：创建普通 Agent cron 和项目绑定 cron 后打开 `/cron.html`。
  - 预期结果：两类 cron 都可见，并能区分普通 Agent cron 与项目 cron。
  - 关联需求点：父需求 CHK-031。

- [x] CHK-008 全局 `/cron.html` 展示项目上下文。
  - 验证方法：查看项目绑定 cron 卡片或详情。
  - 预期结果：显示项目名、目标类型、目标任务名或整个项目 workflow，并能跳转或定位项目。
  - 关联需求点：父需求 CHK-032。

- [x] CHK-009 全局 `/cron.html` 支持按类型和项目过滤。
  - 验证方法：使用过滤控件筛选 Agent cron、Project cron、指定项目。
  - 预期结果：过滤结果准确，不影响原有 Agent 过滤。
  - 关联需求点：父需求 CHK-033。

## Phase 3：调度派发与项目执行绑定

- [x] CHK-010 到期 whole-project cron 在项目空闲时启动 workflow。
  - 验证方法：创建到期 whole-project cron，触发调度处理。
  - 预期结果：项目 workflow 启动，cron 状态更新。
  - 关联需求点：父需求 CHK-013。

- [x] CHK-011 到期 whole-project cron 在 workflow 已运行时跳过。
  - 验证方法：先启动 workflow，再触发到期 whole-project cron。
  - 预期结果：不重复启动；状态记录为 skipped，原因明确。
  - 关联需求点：父需求 CHK-014。

- [x] CHK-012 到期 project-task cron 启动指定项目任务。
  - 验证方法：创建到期指定任务 cron 并触发调度。
  - 预期结果：指定任务进入项目任务执行流程，状态关联该任务。
  - 关联需求点：父需求 CHK-015。

- [x] CHK-013 项目级暂停阻止派发。
  - 验证方法：暂停项目定时任务后触发 due cron。
  - 预期结果：不启动 workflow 或任务执行，状态可见。
  - 关联需求点：父需求 CHK-016。

- [x] CHK-014 删除、归档、缺失或不再满足条件的目标不会派发。
  - 验证方法：分别模拟项目删除、归档、任务缺失、不满足配置条件。
  - 预期结果：调度器拒绝派发并记录原因，不崩溃。
  - 关联需求点：父需求 CHK-017。

- [x] CHK-015 调度后正确更新 last/next run 状态。
  - 验证方法：分别触发 started、skipped、failed、paused 场景。
  - 预期结果：`lastRunAt`、`lastStatus`、`lastError`、`nextRunAt` 或等价字段准确。
  - 关联需求点：父需求 CHK-018。

- [x] CHK-016 普通 Agent cron 行为不退化。
  - 验证方法：在 `/cron.html` 创建、编辑、运行、删除普通 Agent cron。
  - 预期结果：普通 Agent cron 原流程保持可用。
  - 关联需求点：兼容现有 Cron Manager。

- [x] CHK-017 自动化测试和 live 验收覆盖 Phase 2-3。
  - 验证方法：运行新增测试、现有 cron/websocket/project 相关测试，并用 8090 做 live 复测。
  - 预期结果：测试通过；live 复测覆盖 UI 可见性和项目派发主链路。
  - 关联需求点：回归保护和人工验收。

## 人工确认记录

- checklist 确认：2026-06-18T04:05:09+08:00，用户回复 “continue”，确认可以基于当前 Phase 2+3 checklist 生成 todolist。
- done 确认：2026-06-18T18:04:05+08:00，用户回复“我验收了，归档吧”，确认 Phase 2+3 子需求验收通过并归档。

## 测试记录

- 2026-06-18T04:33:36+08:00 自动化测试通过：
  - `python3 -m py_compile app/server.py app/project_store.py tests/test_project_scheduled_cron_phase2_3.py`
  - `.venv/bin/python tests/test_project_scheduled_cron_phase2_3.py`
  - `.venv/bin/python tests/test_project_scheduled_cron_phase1.py`
  - `.venv/bin/python tests/test_websocket_route_contract.py`
  - `.venv/bin/python tests/test_project_execution.py`
  - `node --check app/projects.js`
- 2026-06-18T04:33:36+08:00 8090 live 验收通过：创建项目、任务、项目绑定 cron；`/api/projects/scheduled-cron` 返回项目上下文；`/cron.html` 可见 Project cron、项目名、目标任务、类型过滤、项目过滤。
- 2026-06-18T04:33:36+08:00 Chrome MCP 验收通过：全局定时任务页显示 `Live Project Cron`，项目详情页显示“项目定时任务”配置区、暂停、新建、立即运行、禁用、删除控件；截图保存到 `/tmp/phase23-project-cron-ui.png`。
- 2026-06-18T04:51:15+08:00 Chrome MCP 真实环境补充验收通过：创建并触发 `Live Whole Project Cron`，`targetType=projectWorkflow`；run-now 返回 `dispatch.status=started`，`/workflow/status` 显示 `active=true`、`autoMode=true`、`phase=in_progress`、`currentTaskId=9210e8e7-bae8-4bbb-9e61-5c6929068b10`；项目任务写入 `Sent to agent for work` 评论。验收后已调用 `/workflow/stop` 停止 live workflow，确认 `active=false`、`phase=stopped`。
- 2026-06-18T05:47:04+08:00 根据用户反馈补充“已完成任务重复触发”语义：`projectTask` cron 指向 Done 任务时，不应默认重复触发；只有目标任务显式开启可重复触发属性后，才允许重新打开并派发。
- 2026-06-18T05:47:04+08:00 回归通过：
  - `python3 -m py_compile app/server.py tests/test_project_scheduled_cron_phase2_3.py`
  - `.venv/bin/python tests/test_project_scheduled_cron_phase2_3.py`
- 2026-06-18T06:05:53+08:00 任务级重复触发开关验收通过：
  - 新增任务属性 `scheduledRepeatEnabled`，默认 `false`；任务详情 UI 显示“允许定时任务重复触发已完成任务”复选框。
  - Chrome MCP 真实环境 8090 验收：关闭开关时，Done 任务通过项目定时任务立即运行返回 `status=skipped`、`reason=task_completed_repeat_disabled`，任务保持 Done，`completedAt` 不变。
  - Chrome MCP 真实环境 8090 验收：开启开关后，同一项目定时任务立即运行返回 `status=started`、`reopenedCompletedTask=true`，目标任务清空 `completedAt`，写入 `project-cron` 重新打开评论，并继续进入派发流程。
  - 任务详情 UI 验收：打开项目任务详情后可见复选框，开启后的任务显示为已勾选。
- 2026-06-18T06:05:53+08:00 回归通过：
  - `python3 -m py_compile app/server.py app/project_store.py tests/test_project_scheduled_cron_phase2_3.py`
  - `.venv/bin/python tests/test_project_scheduled_cron_phase2_3.py`
  - `node --check app/projects.js`
- 2026-06-18T16:42:03+08:00 根据用户截图反馈补充全局定时任务入口：`/cron.html` 增加“+ 项目定时任务”按钮，可以直接选择项目、目标类型（整个项目 workflow / 指定任务）、任务和调度计划，并通过 `/api/projects/{projectId}/scheduled-cron` 创建项目绑定 cron。
- 2026-06-18T16:42:03+08:00 8090 真实环境验收通过：全局页 HTML 已包含项目定时任务入口和项目绑定表单；API 创建 `Global Entry Project Cron` 成功；`/api/projects/scheduled-cron` 聚合列表返回 `kind=project`、项目名 `Global Cron Entry Acceptance`、任务名 `Global entry task`。
- 2026-06-18T16:42:03+08:00 回归通过：
  - `node -e "...new Function(inline script)..."` 验证 `app/cron.html` 内联脚本语法。
  - `npx -y html-validate app/cron.html` 仅报既有页面风格规则（inline style、button type、input type），未发现新增入口导致的结构性运行错误。
- 2026-06-18T16:59:58+08:00 根据用户截图反馈补充项目详情页创建体验：项目详情页“新建定时任务”不再使用浏览器 `prompt()`，改为复用项目模块表单弹窗，表单包含名称、目标（整个项目 workflow / 指定任务）、任务选择、调度类型（按间隔重复 / Cron 表达式 / 一次性）、启用状态和 Done 任务重复触发提示。
- 2026-06-18T16:59:58+08:00 8090 真实环境验收通过：服务重新启动后首页加载 `projects.js?...project-cron-form` 和 `projects.css?...project-cron-form`，确认浏览器拿到新表单版本；`node --check app/projects.js` 通过；项目定时任务创建 API 和全局聚合 API 保持可用。
- 2026-06-18T17:49:16+08:00 根据用户反馈补充编辑入口：项目详情页项目定时任务卡片新增“编辑”按钮；“新建”和“编辑”入口标识明确，但共用同一套表单。编辑模式会回填名称、目标、任务、调度计划、启用状态，提交时调用 `PUT /api/projects/{projectId}/scheduled-cron/{cronId}` 保存。
- 2026-06-18T17:49:16+08:00 回归通过：`node --check app/projects.js`；8090 服务正常监听；`/api/projects/scheduled-cron` 正常返回用户创建的项目定时任务 `Real AI Urgency Auto Run Retest 定时任务`。
- 备注：Chrome 控制台存在既有 `/pc-metrics` 和 `weather-proxy` 502 轮询错误，项目定时任务相关请求均为 200。
