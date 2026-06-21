# 项目定时任务 Phase 4 Todolist

## TODO-001 梳理项目定时任务派发和控制面板数据入口

- 目标：确认项目 cron 派发结果、项目活动记录、控制面板数据源和项目详情渲染路径。
- 涉及区域：`app/server.py`、`app/projects.js`、控制面板相关前端和 API、现有项目 activity/status 数据。
- 输入：Phase 2+3 项目 scheduled-cron 派发实现、父需求 Phase 4 checklist。
- 输出：历史写入点、异常提示接入点和诊断日志位置的实现结论。
- 依赖：无。
- 完成标准：明确 run-now 和 due dispatch 都能复用同一套历史写入逻辑；明确控制面板异常提示应从哪个数据源读取。
- 关联 checklist：CHK-001、CHK-007、CHK-009、CHK-016。

## TODO-002 设计并实现项目定时执行历史数据结构

- 目标：为项目定时任务运行结果建立稳定历史记录结构。
- 涉及区域：项目存储、项目读取/保存逻辑、可能的 markdown frontmatter 或 status-dir 存储。
- 输入：TODO-001 的数据入口结论。
- 输出：`scheduledCronHistory` 或等价历史存储字段，包含 id、cronId、cronName、projectId、targetType、taskId、taskTitle、status、reason、message、error、durationMs、source、createdAt。
- 依赖：TODO-001。
- 完成标准：旧项目没有历史字段时默认空数组；历史记录可持久化并随项目详情读取。
- 关联 checklist：CHK-001、CHK-012、CHK-015。

## TODO-003 实现历史写入和数量截断

- 目标：在项目 cron 每次派发决策后写入历史，并控制长期项目的历史规模。
- 涉及区域：项目 cron dispatch/run-now 逻辑、项目保存逻辑。
- 输入：TODO-002 历史结构。
- 输出：统一的历史追加函数和保留上限策略。
- 依赖：TODO-002。
- 完成标准：started、skipped、paused、failed、intervention_required 都能写入历史；每个项目只保留最近 N 条记录，建议默认 200。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-014。

## TODO-004 标准化状态和用户可读原因映射

- 目标：将内部 dispatch status/reason 映射为稳定状态和用户可理解文案。
- 涉及区域：服务端历史写入、前端历史展示、错误处理。
- 输入：现有 dispatch reason，例如 project_active、task_completed_repeat_disabled、paused、missing target。
- 输出：状态枚举和 reason label 映射。
- 依赖：TODO-003。
- 完成标准：skipped/paused/failed/intervention_required 的历史记录不只显示内部 code，中文文案可读。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-006、CHK-013。

## TODO-005 实现 failed 和 intervention_required 的控制面板异常源

- 目标：只把需要处理的项目定时任务异常暴露给控制面板。
- 涉及区域：控制面板 API/状态聚合、项目 activity 或异常列表、前端控制面板渲染。
- 输入：TODO-003 历史记录和 TODO-004 状态语义。
- 输出：控制面板可读取的项目定时任务异常数据。
- 依赖：TODO-003、TODO-004。
- 完成标准：failed 和 intervention_required 出现在控制面板；started、completed、normal skipped、paused 不出现。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-010。

## TODO-006 实现控制面板异常提示 UI 和定位入口

- 目标：用户能在控制面板看到项目定时任务异常，并跳转或定位到对应项目。
- 涉及区域：控制面板前端、项目打开/定位入口、异常卡片样式。
- 输入：TODO-005 异常数据。
- 输出：异常提示卡片或列表项，展示项目名、定时任务名、目标、原因、时间和查看入口。
- 依赖：TODO-005。
- 完成标准：失败和人工介入提示可见、可定位；正常运行不产生提示噪音。
- 关联 checklist：CHK-009、CHK-010、CHK-011。

## TODO-007 实现项目详情页执行历史 UI

- 目标：在项目详情页展示最近的项目定时任务执行历史。
- 涉及区域：`app/projects.js`、`app/projects.css`、项目详情数据渲染。
- 输入：TODO-002/003 历史数据。
- 输出：项目定时任务历史区域、空状态、状态标签、时间和原因展示。
- 依赖：TODO-003、TODO-004。
- 完成标准：历史按时间倒序展示，能区分 started/skipped/paused/failed/intervention_required，且不影响现有定时任务列表和看板。
- 关联 checklist：CHK-012、CHK-013、CHK-015。

## TODO-008 补充服务端诊断日志

- 目标：增强项目 cron 调度排查能力。
- 涉及区域：项目 cron dispatch/run-now 逻辑、服务端日志或调试输出。
- 输入：TODO-003 的统一历史写入点。
- 输出：包含 projectId、cronId、targetType、taskId、decision、reason、error、timestamp 的诊断日志。
- 依赖：TODO-003。
- 完成标准：started、skipped、paused、failed 场景均有可检索诊断信息，不暴露无关敏感数据。
- 关联 checklist：CHK-016。

## TODO-009 增加自动化测试

- 目标：用自动化测试覆盖 Phase 4 核心历史和异常提示语义。
- 涉及区域：`tests/`、项目 cron 测试、控制面板或状态聚合测试。
- 输入：TODO-003 至 TODO-008 的实现。
- 输出：新增或扩展测试文件。
- 依赖：TODO-003、TODO-004、TODO-005、TODO-007、TODO-008。
- 完成标准：测试覆盖 started、skipped、paused、failed、intervention_required、历史截断、旧项目兼容、普通 Agent cron 不进项目历史。
- 关联 checklist：CHK-001 至 CHK-019。

## TODO-010 执行 Phase 2+3 回归测试

- 目标：确认执行历史和异常提示没有破坏既有项目定时任务能力。
- 涉及区域：Phase 2+3 测试、`app/projects.js`、`app/cron.html`、`app/server.py`。
- 输入：已完成实现和已有 Phase 2+3 测试。
- 输出：回归测试结果记录。
- 依赖：TODO-009。
- 完成标准：创建、编辑、启用/禁用、删除、立即运行、项目级暂停/恢复、任务重复触发开关仍可用。
- 关联 checklist：CHK-017、CHK-018、CHK-019。

## TODO-011 8090 live 验收

- 目标：在真实运行环境验证项目历史和控制面板异常提示。
- 涉及区域：8090 本地服务、Chrome MCP/共享浏览器、项目详情页、控制面板。
- 输入：实现完成后的本地服务。
- 输出：live 验收记录和必要截图/日志。
- 依赖：TODO-009、TODO-010。
- 完成标准：真实环境覆盖至少成功启动、正常跳过、失败或人工介入三类记录；控制面板提示符合噪音规则。
- 关联 checklist：CHK-020。

## TODO-012 更新需求归档状态和测试记录

- 目标：把实现、测试和人工验收结果回写到 Phase 4 需求归档。
- 涉及区域：`checklist.md`、`status.json`、必要时 `review.md`。
- 输入：TODO-009 至 TODO-011 的测试和验收结果。
- 输出：测试记录、状态推进和等待用户确认记录。
- 依赖：TODO-011。
- 完成标准：开发完成后进入 `tested` 或等待用户确认的正确状态；最终必须由用户确认 done 后归档。
- 关联 checklist：CHK-019、CHK-020。
