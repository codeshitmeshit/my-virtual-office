# 项目定时任务 Phase 1 Todolist

## Phase 1：扩展现有 Cron 支持项目绑定

### TODO-001 确认现有 Cron RPC 所有权和字段行为

- 目标：确认本仓库内 Cron Manager 通过 gateway `cron.*` RPC 工作，VO 本地没有 `cron.*` handler。
- 涉及区域：`app/cron.html`、`app/server.py`、gateway RPC helper。
- 输入：现有代码搜索结果和 checklist。
- 输出：实现决策：使用 gateway `cron.*` 作为底层调度，VO 侧保存项目绑定元数据。
- 依赖：无。
- 完成标准：实现中不重做 scheduler，不改普通 Cron Manager 语义。
- 关联 checklist：CHK-001、CHK-007。

### TODO-002 增加 VO 侧项目 Cron 绑定表

- 目标：保存 `cronJobId -> projectId/targetType/taskId`，避免依赖 provider 是否保留未知字段。
- 涉及区域：`app/server.py`、`STATUS_DIR` 持久化文件。
- 输入：cron job id、项目绑定元数据。
- 输出：绑定表读写、原子保存、兼容缺失文件。
- 依赖：TODO-001。
- 完成标准：绑定表跨服务重启可恢复。
- 关联 checklist：CHK-002、CHK-003。

### TODO-003 增加项目绑定 Cron 校验

- 目标：校验项目存在、项目有负责人或绑定 Agent、目标类型合法、任务属于当前项目。
- 涉及区域：`app/server.py` 项目读取逻辑、项目任务数据。
- 输入：`projectId`、`targetType`、`taskId`。
- 输出：校验函数和清晰错误响应。
- 依赖：TODO-002。
- 完成标准：非法项目/目标不会创建 cron 或绑定记录。
- 关联 checklist：CHK-004、CHK-005、CHK-009。

### TODO-004 增加项目绑定 Cron 后端封装 API

- 目标：提供 Phase 2 项目页可用的稳定 API，内部代理 gateway `cron.*` 并维护绑定表。
- 涉及区域：`app/server.py` GET/POST/PUT/DELETE route。
- 输入：schedule、enabled、targetType、taskId、agentId、message、timeoutSeconds。
- 输出：按项目 list/create/update/delete/toggle/run-now 的后端能力。
- 依赖：TODO-002、TODO-003。
- 完成标准：项目页无需直接理解 provider cron 细节即可管理项目绑定 cron。
- 关联 checklist：CHK-002、CHK-006、CHK-008。

### TODO-005 增加 Phase 1 自动化测试

- 目标：覆盖项目绑定 CRUD、绑定持久化、校验失败、普通 Cron 兼容边界。
- 涉及区域：`tests/`。
- 输入：TODO-002 至 TODO-004 行为。
- 输出：后端单元测试。
- 依赖：TODO-004。
- 完成标准：新增测试覆盖 CHK-001 至 CHK-010。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010。

### TODO-006 运行回归测试并记录结果

- 目标：确认 Phase 1 实现不破坏现有项目和 Cron 相关行为。
- 涉及区域：新增测试、现有 websocket route contract、项目执行相关测试。
- 输入：TODO-005 测试。
- 输出：测试结果和必要修复。
- 依赖：TODO-005。
- 完成标准：相关测试通过，失败项有明确说明。
- 关联 checklist：CHK-007、CHK-010。
