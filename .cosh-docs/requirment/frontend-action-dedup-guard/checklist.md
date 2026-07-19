# Frontend Action Dedup Guard Checklist

确认状态：已确认

## Checklist

### CHK-001 统一 action guard

- 关联需求点：目标 1、关键约束。
- 验证方法：检查 `app/projects.js` 中存在统一 `runActionOnce` 或同等能力，并维护按 key 区分的 pending action 集合。
- 预期结果：同一 action key 执行中再次触发不会再次执行真实请求函数；不同 key 不互相阻塞。

### CHK-002 按业务粒度生成稳定防重 key

- 关联需求点：范围、防重 key 粒度。
- 验证方法：静态检查项目执行、会议 blocker、验收、workflow、cron 等入口的 key 组成。
- 预期结果：key 包含 projectId、taskId、attemptId、cronId、action 等必要维度；不会用一个全局锁挡住所有操作。

### CHK-003 单任务启动防重

- 关联需求点：单任务 Project Execution 启动。
- 验证方法：模拟或手动快速双击“启动此任务”；也可用 Chrome/CDP 监听 `/project-execution/start` 请求数。
- 预期结果：前端最多发出一次启动请求；按钮立即显示处理中或 disabled；请求返回且状态刷新完成前不会再次触发。

### CHK-004 项目级启动与重启防重

- 关联需求点：项目级 Project Execution 启动与重启流水线。
- 验证方法：快速双击“启动项目”和“重启流水线”，分别监听项目级 `/project-execution/start` 请求。
- 预期结果：每个业务动作只发一次请求；重启确认流程不会在确认后重复启动；状态刷新完成前旧按钮不可再次触发。

### CHK-005 停止执行防重

- 关联需求点：停止当前执行或指定 attempt。
- 验证方法：执行中的任务上快速点击停止按钮。
- 预期结果：同一 task/attempt 的 cancel 请求只发一次；失败时按钮或状态可恢复。

### CHK-006 会议 blocker 操作防重

- 关联需求点：会议 blocker 继续/阻塞/重开。
- 验证方法：在 `awaiting_meeting_resolution` 任务上分别快速触发继续执行、标记阻塞、重新申请会议。
- 预期结果：同一 task/action 只提交一次；文本输入弹窗确认按钮提交后 disabled；空必填理由仍能提示且不锁死。

### CHK-007 启动审查防重

- 关联需求点：启动审查。
- 验证方法：对 execution complete 状态任务快速双击启动审查。
- 预期结果：同一 task/attempt 的 review start 请求只发一次。

### CHK-008 验收与反馈提交防重

- 关联需求点：验收通过、退回返工、标记阻塞。
- 验证方法：在验收弹窗和反馈弹窗中快速双击确认按钮。
- 预期结果：同一 task/attempt/action 只提交一次；确认按钮立即 disabled；请求失败后可重新提交。

### CHK-009 Workflow start/stop 防重

- 关联需求点：工作流 start/stop。
- 验证方法：快速点击 workflow start/stop。
- 预期结果：同一 project 的 start 或 stop 请求不会重复发出。

### CHK-010 Scheduled cron 写操作防重

- 关联需求点：cron 创建/编辑、立即运行、暂停/恢复、启用/禁用、删除。
- 验证方法：快速双击 cron 表单提交、run now、toggle、delete。
- 预期结果：同一 cron action 最多发一次请求；删除确认后不会重复 delete；表单失败可恢复。

### CHK-011 对话框取消与异常释放锁

- 关联需求点：异常处理。
- 验证方法：打开需要确认的操作后取消；再重新点击同一操作。分别模拟普通错误和状态冲突类错误。
- 预期结果：取消会释放锁；普通错误允许恢复后重试；状态冲突类错误会刷新状态并避免原地重复提交。

### CHK-012 刷新与重渲染兼容

- 关联需求点：兼容性、状态机。
- 验证方法：action 成功后触发 `refreshProjectExecutionProject` 或重渲染任务卡。
- 预期结果：旧按钮状态不影响新 DOM；pending action 不会永久残留。

### CHK-013 重复点击可观测性

- 关联需求点：可观测性。
- 验证方法：触发一次重复点击拦截，检查控制台或测试 hook。
- 预期结果：有低噪日志或可测试信号能说明重复 action 被忽略；高风险动作最多给出一条轻量 toast，普通重复点击不产生噪音。

### CHK-014 回归测试覆盖

- 关联需求点：测试可行性。
- 验证方法：运行新增或更新的静态 JS 测试、相关 Chrome/CDP 测试，以及项目侧 Python 回归测试。
- 预期结果：测试通过；关键 action 防重逻辑被自动化覆盖；覆盖请求数、按钮 busy 反馈和状态一致性三个验收维度。

### CHK-015 不改变后端业务语义

- 关联需求点：非目标、架构与接口影响。
- 验证方法：检查后端接口行为和现有项目执行测试结果。
- 预期结果：不新增后端接口，不改变 Project Execution、meeting blocker、cron 的状态机语义。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-07-08T15:24:21+08:00
- 用户确认摘要：用户回复 `continue`，确认当前 checklist 可作为后续 todolist 和实现验收依据。

## 实施测试记录

- 记录时间：2026-07-08T15:42:46+08:00
- 静态防重覆盖：`node tests/check_project_action_dedup_static.mjs` 通过，覆盖 `runActionOnce`、action key 粒度、dialog submitting、workflow、project execution、meeting blocker、acceptance、cron 写操作。
- JS 回归：`node --check app/projects.js`、`node tests/check_project_execution_start_payload.mjs`、`node tests/check_project_execution_executor_required_prompt.mjs`、`node tests/check_project_meeting_blocker_view_reference.mjs` 通过。
- Python 回归：`PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest -q tests/test_project_execution.py tests/test_project_scheduled_cron_phase2_3.py tests/test_project_scheduled_cron_phase4.py` 通过，96 passed。
- 浏览器验收：通过应用内浏览器打开真实项目页，执行 workflow Start 浏览器级 double-click；页面切到 Stop 后回到 Start，服务日志中该 double-click 窗口只出现 1 条 `POST /api/projects/{id}/workflow/start`。
- CDP E2E：已补充 `tests/chrome_project_action_dedup_check.mjs`，但当前环境 `http://127.0.0.1:9224` 不可达，未启动本机 Chrome 调试端口，因此该脚本本机未能执行请求计数型验收。

## 会议侧补充记录

- 记录时间：2026-07-08T15:52:50+08:00
- 覆盖范围：会议请求确认/拒绝、新建 executable meeting、start/run、会中 intervention、agenda change、targeted question、arbitration、moderator takeover、decision continue、action item update/confirm/keep/reject、AI/manual end、transition pause/resume/cancel、conflict wait/reserve/replace/force/refresh、history delete。
- 防重 key 示例：`meeting-request-confirm:{requestId}`、`meeting-create:new`、`meeting-run:{meetingId}:{action}:{pendingSequence}`、`meeting-transition:{meetingId}:{action}`、`meeting-conflict:{meetingId}:{action}:{agentId}:{replacement}`、`meeting-action-item:{meetingId}:{actionItemId}:{action}`。
- 新增测试：`node tests/check_meeting_action_dedup_static.mjs` 通过；`node --check app/game.js` 通过；项目侧 `node tests/check_project_action_dedup_static.mjs` 仍通过。
