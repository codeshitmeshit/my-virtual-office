# Meeting Request Blocks Task Todolist

## TODO-001 定义会议阻塞任务状态语义

- 目标：为 Project Execution 增加“等待会议结论”的任务执行语义。
- 涉及区域：`app/server.py` Project Execution 状态机、状态展示数据。
- 输入：产品结论、现有 `executionState`、`workflowPhase`。
- 输出：明确的状态命名、状态转换规则、历史记录字段约定。
- 依赖：无。
- 完成标准：任务能表达 awaiting meeting resolution，并与 In Progress 产品列语义兼容。
- 关联 checklist：CHK-001、CHK-002、CHK-013。

## TODO-002 会议申请创建时阻塞任务

- 目标：创建项目任务会议申请后，任务立即进入等待会议结论状态。
- 涉及区域：`_handle_meeting_request_create`、项目存储、任务历史。
- 输入：projectId、taskId、meeting request body。
- 输出：会议申请记录、任务 `meetingBlocker` 或等价引用、任务状态变更记录。
- 依赖：TODO-001。
- 完成标准：创建成功后任务不再继续执行；失败时不产生不一致状态。
- 关联 checklist：CHK-001、CHK-018。

## TODO-003 限制同一任务只有一个未解决阻塞会议申请

- 目标：防止一个任务同时存在多个竞争解锁来源。
- 涉及区域：meeting request store 查询、创建幂等逻辑、错误/返回语义。
- 输入：已有 pending/confirmed 未解决 request。
- 输出：拒绝第二个申请或返回现有申请。
- 依赖：TODO-002。
- 完成标准：重复创建不会生成多个 unresolved blocking request。
- 关联 checklist：CHK-003。

## TODO-004 让 Project Execution pipeline 识别会议等待状态

- 目标：pipeline 遇到等待会议结论的任务时暂停，不继续当前任务，也不越过它拉取 backlog。
- 涉及区域：`_wf_get_active_task`、`_project_execution_can_start`、workflow phase sync、项目启动/重启逻辑。
- 输入：任务状态、workflow 状态。
- 输出：正确暂停的 workflowPhase 和用户可读错误/提示。
- 依赖：TODO-001、TODO-002。
- 完成标准：等待会议任务被视为 active task，不会被后续任务绕过。
- 关联 checklist：CHK-002、CHK-013、CHK-016。

## TODO-005 定义会议结构化 outcome

- 目标：让会议结果可以稳定表达是否达成一致并允许继续。
- 涉及区域：executable meeting result、会议结束/仲裁/用户决策路径。
- 输入：会议完成结果、主持人决策、用户仲裁。
- 输出：`resolved_continue`、`no_consensus`、`needs_user_decision` 或等价枚举。
- 依赖：TODO-001。
- 完成标准：任务恢复不依赖自由文本 summary 猜测。
- 关联 checklist：CHK-005、CHK-006、CHK-007。

## TODO-006 会议结果回写任务状态

- 目标：关联会议状态变化后，同步更新被阻塞任务。
- 涉及区域：meeting request conversion、executable meeting completion/transition handlers、项目任务更新。
- 输入：meetingId、meetingRequestId、structured outcome。
- 输出：任务恢复执行、进入 blocked 或等待用户处理。
- 依赖：TODO-002、TODO-005。
- 完成标准：会议完成后任务状态与 outcome 一致，并记录会议引用。
- 关联 checklist：CHK-004、CHK-005、CHK-006、CHK-007、CHK-018。

## TODO-007 处理会议申请拒绝和超时

- 目标：拒绝/超时不自动放行任务，改为等待用户处理。
- 涉及区域：meeting request reject handler、preparing timeout release、pending request 超时检查或展示。
- 输入：拒绝原因、超时事件。
- 输出：任务保持等待用户处理，UI 可见原因。
- 依赖：TODO-002、TODO-006。
- 完成标准：拒绝和超时均不会触发自动继续。
- 关联 checklist：CHK-008、CHK-009。

## TODO-008 增加用户接管操作

- 目标：等待会议期间用户可继续执行、标记阻塞、重新申请会议。
- 涉及区域：项目任务 API、任务详情 UI、会议申请 UI。
- 输入：用户操作、原因/说明。
- 输出：任务状态变更、会议阻塞引用清理或替换、历史记录。
- 依赖：TODO-002、TODO-007。
- 完成标准：三个接管操作均可用且可追踪。
- 关联 checklist：CHK-010、CHK-011、CHK-012、CHK-018。

## TODO-009 更新前端状态展示和本地化

- 目标：任务详情、任务卡、workflow 状态、会议申请区展示一致文案。
- 涉及区域：`app/projects.js`、`app/projects.css`、`app/locales/zh.json`、`app/locales/en.json`。
- 输入：任务状态、meetingBlocker、request status。
- 输出：中文/英文状态、操作按钮、提示文案。
- 依赖：TODO-001、TODO-008。
- 完成标准：无裸 key，中英文切换正常。
- 关联 checklist：CHK-013、CHK-014。

## TODO-010 增加服务端回归测试

- 目标：覆盖状态流、会议结果、拒绝/超时和并发限制。
- 涉及区域：现有 Python 测试或新增测试脚本。
- 输入：临时项目、任务、会议申请、会议结果。
- 输出：自动化测试覆盖关键服务端状态。
- 依赖：TODO-002、TODO-006、TODO-007。
- 完成标准：测试能证明 CHK-001 到 CHK-009 的服务端核心行为。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009。

## TODO-011 增加前端/真实数据验收脚本

- 目标：用真实项目数据验证 UI 和 API 状态一致。
- 涉及区域：本地服务、真实 data 项目、浏览器/MCP 或现有前端检查脚本。
- 输入：可执行项目任务和会议申请。
- 输出：端到端验收记录。
- 依赖：TODO-009、TODO-010。
- 完成标准：真实数据路径完成可继续、无共识、拒绝至少三条路径验证。
- 关联 checklist：CHK-013、CHK-014、CHK-017。

## TODO-012 回归验证普通会议与既有 Project Execution 流程

- 目标：确保新阻塞语义不影响非项目会议和已有执行状态机。
- 涉及区域：会议创建/结束、Project Execution review/user acceptance/rework/blocked。
- 输入：普通会议、普通项目执行任务。
- 输出：回归测试结果。
- 依赖：TODO-006、TODO-009。
- 完成标准：普通会议不产生项目任务阻塞，既有执行流程保持可用。
- 关联 checklist：CHK-015、CHK-016。

## TODO-013 优化会议申请队列和侧边栏展示

- 目标：让会议申请队列适合扫描和处理，避免详情内容撑开列表，并用状态和数量提示提升辨识度。
- 涉及区域：`app/server.py` 会议申请列表排序、`app/game.js` 会议申请队列/详情弹窗/侧边栏提示、`app/style.css` 状态颜色和气泡样式、`app/projects.js`/`app/projects.css` 项目任务详情申请状态展示。
- 输入：会议申请 `status`、`updatedAt`、`createdAt`、申请详情、pending 数量。
- 输出：未处理优先排序、VO 风格详情弹窗、待确认/已确认/已拒绝状态色、侧边栏同一行数量气泡。
- 依赖：TODO-009、TODO-011。
- 完成标准：会议申请列表按状态和时间稳定排序；申请详情在弹窗中查看和处理；状态颜色在会议队列和项目详情一致；侧边栏 pending 数量以右侧气泡展示。
- 关联 checklist：CHK-019、CHK-020、CHK-021、CHK-022。
