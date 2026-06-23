# Project Execution State Machine Columns Checklist

确认状态：已确认

## 验收规则

- 本 checklist 确认前不得生成 todolist。
- Project Execution 项目的列语义必须按状态机处理。
- 普通项目的自由看板行为必须保持不变。
- 所有验证都应覆盖接口状态、持久化数据和用户可见列位置。

## Checklist

### CHK-001 执行开始进入 In Progress
- 验证方法：创建 Project Execution 项目和 Backlog 任务，启动任务执行。
- 预期结果：任务 `executionState` 为 `executing`，`columnId` 指向 In Progress 列，`completedAt` 为空。
- 关联需求点：Project Execution 状态与看板列统一。

### CHK-002 执行完成进入 Review
- 验证方法：模拟 executor 成功完成，但 reviewer 尚未开始或正在等待 handoff。
- 预期结果：任务 `executionState` 为 `execution_complete`，`columnId` 指向 Review 列，执行证据保留，未进入 Done。
- 关联需求点：执行完成不能停留在 Backlog，也不能跳过 Review 语义。

### CHK-003 Reviewer 运行时停留 Review
- 验证方法：启动 reviewer handoff，让任务进入 `reviewing`。
- 预期结果：任务位于 Review 列，项目 active agent 指向 reviewer，左侧/控制面板能显示 reviewer 阶段。
- 关联需求点：Review 列承载独立审核阶段。

### CHK-004 默认 reviewer pass 直接进入 Done
- 验证方法：在未启用人工验收的任务上模拟 reviewer 返回 pass。
- 预期结果：任务 `executionState` 为 `done`，`columnId` 指向 Done 列，`completedAt` 存在，历史记录说明由 reviewer pass 完成。
- 关联需求点：AI reviewer 默认代替验收。

### CHK-005 启用人工验收时 reviewer pass 留在 Review
- 验证方法：创建或配置需要人工验收的任务，模拟 reviewer 返回 pass。
- 预期结果：任务 `executionState` 为 `awaiting_user_acceptance`，`columnId` 指向 Review 列，`completedAt` 为空。
- 关联需求点：人工验收选项保留 awaiting_user_acceptance 产品语义。

### CHK-006 人工验收通过后进入 Done
- 验证方法：对 `awaiting_user_acceptance` 任务调用人工验收通过动作。
- 预期结果：任务从 Review 进入 Done，`executionState` 为 `done`，`completedAt` 存在，历史记录说明由 human acceptance 完成。
- 关联需求点：人工验收路径为 Review -> Done。

### CHK-007 跳过 reviewer 且不需人工验收时进入 Done
- 验证方法：确认跳过 reviewer，并运行一个不需要人工验收的任务。
- 预期结果：任务记录 `reviewResult.status = skipped`，最终 `executionState` 为 `done`，`columnId` 指向 Done。
- 关联需求点：跳过 review 后按确认结果完成，并保留审计记录。

### CHK-008 跳过 reviewer 且需要人工验收时停留 Review
- 验证方法：确认跳过 reviewer，并运行一个需要人工验收的任务。
- 预期结果：任务记录 `reviewResult.status = skipped`，`executionState` 为 `awaiting_user_acceptance`，`columnId` 指向 Review。
- 关联需求点：人工验收选项对 skipped review 同样生效。

### CHK-009 Rework 进入 In Progress
- 验证方法：模拟 reviewer 返回 `needs_more_work`。
- 预期结果：任务进入 `reworking` 或下一次执行阶段时位于 In Progress，`reworkFeedback` 保留。
- 关联需求点：返工阶段属于执行工作，不应停留 Review 或 Backlog。

### CHK-010 Blocked 不误入 Done
- 验证方法：模拟 executor 失败、reviewer blocked、角色缺失或工作区错误。
- 预期结果：任务进入 `blocked`，不移动到 Done；错误原因在任务和项目状态中可见。
- 关联需求点：异常状态不绕过状态机完成。

### CHK-011 Project Execution 禁止非法手动移动到 Done
- 验证方法：尝试通过任务更新或拖拽/reorder 将未通过 review 的 Project Execution 任务移动到 Done。
- 预期结果：接口返回 409 或等价错误，UI 展示明确提示，任务位置和状态不变。
- 关联需求点：用户不能手动破坏状态机。

### CHK-012 普通项目拖拽行为不变
- 验证方法：创建普通项目并手动移动任务到任意列。
- 预期结果：移动成功，普通项目不受 Project Execution 状态机限制。
- 关联需求点：非 Project Execution 项目保留自由看板。

### CHK-013 连续任务流不选择 Review/Done 中的非 startable 任务
- 验证方法：连续启动模式下准备多个任务，其中包含 Review、Done、awaiting_user_acceptance 和 Backlog 任务。
- 预期结果：系统只选择 startable 任务，不重复启动 Review/Done/awaiting acceptance 任务。
- 关联需求点：列同步不破坏 next eligible task 选择。

### CHK-014 真实持久化数据一致
- 验证方法：执行状态流转后读取项目 API 和 markdown/json 持久化结果。
- 预期结果：持久化的 `executionState`、`columnId`、`completedAt`、`stateHistory` 与预期一致。
- 关联需求点：刷新页面后看板仍一致。

### CHK-015 UI 看板显示一致
- 验证方法：打开本地服务，在浏览器中执行或加载 Project Execution 项目。
- 预期结果：执行中任务显示在 In Progress，审核/待人工验收显示在 Review，完成显示在 Done；Backlog 不出现 active/reviewed 任务。
- 关联需求点：用户可从看板理解状态。

### CHK-016 Toolbar 和任务详情状态一致
- 验证方法：分别在 executing、reviewing、awaiting_user_acceptance、done 状态查看 toolbar 和任务详情。
- 预期结果：toolbar、任务详情、看板列显示同一阶段，不出现列和状态矛盾。
- 关联需求点：状态机用户感知一致。

### CHK-017 旧 workflow 引擎回归
- 验证方法：运行或检查普通项目 legacy workflow 的 Backlog -> In Progress -> Review -> Done 流程。
- 预期结果：旧 workflow 原有移动列行为不被破坏。
- 关联需求点：修复只影响 Project Execution 新逻辑。

### CHK-018 自动化测试覆盖
- 验证方法：运行 Project Execution focused tests、相关 server py_compile、前端 JS 语法检查，以及现有项目 CRUD 回归。
- 预期结果：全部通过，无新增语法、持久化或回归错误。
- 关联需求点：实现可回归验证。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-23T02:51:35+08:00
- 用户确认摘要：用户回复“pass”，确认本 checklist 可作为后续 todolist、实现和验收依据。

## 测试执行记录

- 执行时间：2026-06-23T02:58:30+08:00
- 执行项：`python3 -m py_compile app/server.py app/project_store.py app/providers/codex_bridge.py tests/test_project_execution.py tests/test_codex_bridge.py`
- 结果：通过。

- 执行时间：2026-06-23T02:58:30+08:00
- 执行项：`node --check app/projects.js`
- 结果：通过。

- 执行时间：2026-06-23T02:58:30+08:00
- 执行项：`.venv/bin/python tests/test_project_execution.py`
- 结果：通过。输出包含测试环境预期的 Gateway 连接失败日志，最终退出 `ok`。

- 执行时间：2026-06-23T02:58:30+08:00
- 执行项：`.venv/bin/python tests/test_codex_bridge.py`
- 结果：通过。

- 执行时间：2026-06-23T02:58:30+08:00
- 执行项：`bash tests/test_crud_projects.sh http://127.0.0.1:8090`
- 结果：通过，5/5 passed。

- 执行时间：2026-06-23T02:58:30+08:00
- 执行项：`git diff --check`
- 结果：通过。

## 测试确认记录

- 确认项：tested
- 确认时间：2026-06-23T03:45:30+08:00
- 用户确认摘要：用户完成本地验收，确认 Project Execution 状态机、返工重跑、验收弹窗等相关修复没有问题。

## 最终验收记录

- 确认项：done
- 确认时间：2026-06-23T03:45:30+08:00
- 用户确认摘要：用户明确表示“没问题了，这个需求可以验收通过了”，确认需求闭环完成并允许归档。
