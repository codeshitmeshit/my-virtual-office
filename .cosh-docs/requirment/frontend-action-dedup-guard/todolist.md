# Frontend Action Dedup Guard Todolist

## TODO-001 梳理项目侧写操作入口和风险分级

- 目标：确认首期覆盖的项目执行和 cron 写操作入口，建立 action key 清单。
- 涉及区域：`app/projects.js`，现有项目侧按钮渲染与 action 函数。
- 输入：`requirement.md`、`review.md`、`checklist.md`、现有 `projects.js` 写操作入口。
- 输出：代码内稳定 action key 规则和覆盖范围。
- 依赖：无。
- 完成标准：项目执行、会议 blocker、验收、workflow、scheduled cron 的写操作均有明确 key 粒度。
- 关联 checklist：CHK-001、CHK-002、CHK-015。

## TODO-002 实现统一 action guard 基础能力

- 目标：在 `ProjMgr` 内提供统一的 action 防重能力。
- 涉及区域：`app/projects.js` 的 state 初始化、工具函数区、toast/按钮反馈逻辑。
- 输入：TODO-001 的 key 清单。
- 输出：`runActionOnce` 或同等函数，支持 pending action 集合、重复触发拦截、异常释放和可选按钮 busy 状态。
- 依赖：TODO-001。
- 完成标准：同一 key 并发调用只执行一次真实 action；不同 key 可并行；失败和取消能释放锁。
- 关联 checklist：CHK-001、CHK-011、CHK-012、CHK-013。

## TODO-003 为项目执行启动/停止/审查操作接入防重

- 目标：保护单任务启动、项目级启动、重启流水线、停止执行和启动审查。
- 涉及区域：`projectExecutionStartAction`、`projectExecutionProjectStartAction`、`projectExecutionProjectRestartAction`、`projectExecutionCancelActiveAction`、`projectExecutionCancelAction`、`projectExecutionReviewStartAction` 及相关按钮。
- 输入：TODO-002 的 guard 能力。
- 输出：这些 action 使用稳定 key，并在请求返回且刷新完成前保持防重。
- 依赖：TODO-002。
- 完成标准：快速双击不会重复发起 start/cancel/review 请求；状态冲突类错误优先刷新状态。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-007、CHK-011、CHK-012。

## TODO-004 为会议 blocker 操作接入防重

- 目标：保护继续执行、标记阻塞、重新申请会议三个会议 blocker 操作。
- 涉及区域：`renderMeetingBlocker`、`projectExecutionMeetingBlockerAction`、文本输入弹窗提交路径。
- 输入：TODO-002 的 guard 能力。
- 输出：`meeting-blocker:${projectId}:${taskId}:${action}` 粒度防重；文本弹窗确认后同步 busy。
- 依赖：TODO-002。
- 完成标准：同一 task/action 只提交一次；空必填理由不锁死；普通失败可恢复重试；状态冲突刷新后再允许继续。
- 关联 checklist：CHK-006、CHK-011、CHK-013。

## TODO-005 为验收与反馈弹窗提交接入防重

- 目标：保护验收通过、退回返工、标记阻塞提交，避免同一弹窗重复提交。
- 涉及区域：`showProjectExecutionAcceptDialog`、`showProjectExecutionFeedbackDialog`、`submitProjectExecutionAcceptanceAction`、`submitProjectExecutionFeedbackAction`、`submitProjectExecutionAcceptance`。
- 输入：TODO-002 的 guard 能力。
- 输出：`project-exec-accept:${projectId}:${taskId}:${attemptId}:${action}` 粒度防重；确认按钮提交后立即 disabled 或 busy。
- 依赖：TODO-002。
- 完成标准：快速双击弹窗确认按钮只提交一次；失败后可重新提交；成功后弹窗关闭并刷新状态。
- 关联 checklist：CHK-008、CHK-011、CHK-012。

## TODO-006 为 workflow start/stop 接入防重

- 目标：保护项目 workflow start/stop 操作。
- 涉及区域：`workflowStartAction`、`workflowStopAction` 及相关按钮。
- 输入：TODO-002 的 guard 能力。
- 输出：`workflow-start:${projectId}` 和 `workflow-stop:${projectId}` 防重。
- 依赖：TODO-002。
- 完成标准：快速点击 start/stop 不重复发请求，成功和失败路径均释放锁。
- 关联 checklist：CHK-009、CHK-011、CHK-012。

## TODO-007 为 scheduled cron 写操作接入防重

- 目标：保护 cron 创建/编辑、立即运行、暂停/恢复、启用/禁用、删除。
- 涉及区域：`submitProjectCron`、`toggleProjectCronPauseAction`、`runProjectCronAction`、`toggleProjectCronAction`、`deleteProjectCronAction` 及相关按钮。
- 输入：TODO-002 的 guard 能力。
- 输出：cron action key 覆盖 new/edit/run/toggle/delete/pause-resume。
- 依赖：TODO-002。
- 完成标准：快速双击 cron 写操作只发一次请求；删除确认后不会重复 delete；表单失败能恢复。
- 关联 checklist：CHK-010、CHK-011、CHK-013。

## TODO-008 补充静态和行为回归测试

- 目标：用自动化覆盖关键 action 防重行为。
- 涉及区域：`tests/` 中 JS 静态检查或 CDP/Chrome 检查脚本，必要时补充 Python 回归。
- 输入：TODO-003 至 TODO-007 的实现。
- 输出：新增或更新测试，覆盖请求数、按钮 busy、状态一致性。
- 依赖：TODO-003、TODO-004、TODO-005、TODO-006、TODO-007。
- 完成标准：测试能证明同一 key 重复点击只执行一次；高风险重复点击最多一条轻量提示；状态刷新完成后可再次合法操作。
- 关联 checklist：CHK-003、CHK-004、CHK-006、CHK-008、CHK-010、CHK-014。

## TODO-009 执行回归验证并记录结果

- 目标：完成实现后的测试执行和交付记录。
- 涉及区域：`checklist.md`、测试命令输出、最终交付说明。
- 输入：TODO-008 的测试。
- 输出：测试结果写回 checklist 或交付说明。
- 依赖：TODO-008。
- 完成标准：相关 JS/Chrome/Python 回归通过；确认没有改变后端业务语义。
- 关联 checklist：CHK-014、CHK-015。

## 执行状态

- TODO-001：已完成。
- TODO-002：已完成。
- TODO-003：已完成。
- TODO-004：已完成。
- TODO-005：已完成。
- TODO-006：已完成。
- TODO-007：已完成。
- TODO-008：已完成，新增静态覆盖和 CDP E2E 脚本。
- TODO-009：已完成自动化和应用内浏览器验收记录；CDP 请求计数脚本受当前 Chrome DevTools 端口不可达限制，未能在本机执行。
