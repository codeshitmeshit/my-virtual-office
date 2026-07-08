# Project Reset Actions Checklist

确认状态：已通过

## Acceptance Checklist

### CHK-001 Toolbar Entry

- 关联需求点：新增项目级 "重置" 按钮。
- 验证方法：打开项目详情页，检查截图标注区域附近出现按钮文案 "重置"。
- 预期结果：按钮位于项目级操作区，不挤压启动、编辑、产物、报告、模板等现有操作；中文界面显示 "重置"，英文界面有对应文案。

### CHK-002 Reset Choice Dialog

- 关联需求点：点击 "重置" 后展示两个选择。
- 验证方法：点击 "重置"。
- 预期结果：弹窗展示 "重置任务状态" 和 "彻底重置项目" 两个互斥操作，并说明二者差异；取消弹窗不改变项目数据。

### CHK-003 Risky State Confirmation

- 关联需求点：仅执行中、阻塞、review、done 等非初始状态需要高风险确认。
- 验证方法：构造包含 executing、blocked、review、done/completed、activeAttemptId 或 blockedReason 的任务，触发任一 reset 操作。
- 预期结果：系统先展示高风险确认；用户取消时不改变项目；用户确认后才执行 reset。

### CHK-004 Initial State No Extra Confirmation

- 关联需求点：普通空项目或全部 backlog 初始状态重置成本低。
- 验证方法：在所有任务均处于 backlog 且无 active/blocked/done/review 状态时点击 reset。
- 预期结果：可以直接执行所选 reset 操作，不弹高风险确认；操作完成后状态保持合理。

### CHK-005 Reset Task State Behavior

- 关联需求点："重置任务状态" 清当前执行上下文但保留历史。
- 验证方法：对包含 active attempt、blocked reason、review result、meeting blocker/current meeting action fields、completedAt、executionState 的任务执行 "重置任务状态"。
- 预期结果：任务回到 backlog；activeAttemptId、blockedReason、lastError、reviewResult、meetingBlocker、当前 meeting action fields、completedAt、executionState 等当前上下文被清理；comments、attempts、stateHistory、meetingBlockerHistory、历史记录仍保留。

### CHK-006 Full Project Reset Behavior

- 关联需求点："彻底重置项目" 保留新增任务、项目配置和定时任务，只复位任务流。
- 验证方法：创建初始任务后再新增任务，配置项目元信息和 scheduled cron，再执行 "彻底重置项目"。
- 预期结果：所有任务仍存在并回到 backlog；新增任务未被删除；项目标题、描述、优先级、默认 agents、workspace、scheduled cron 配置不变。

### CHK-007 Task Order Preservation

- 关联需求点：重置时必须注意执行顺序。
- 验证方法：构造跨 backlog、in progress、review、done 多列的任务，并记录 reset 前用户可见顺序；执行两个 reset 操作分别验证。
- 预期结果：所有任务回到 backlog 后顺序稳定且符合产品约定，不因状态清理、列迁移或持久化读写而打乱。

### CHK-008 Project Execution Flow Reset

- 关联需求点：执行中或阻塞项目强制回到可重新启动状态。
- 验证方法：构造 projectExecutionFlowActive、workflowActive、activeTaskId、activeAgent、workflowPhase 非 idle 的项目后执行 reset。
- 预期结果：项目级 active fields 被清理；页面不再显示当前任务执行中或阻塞；用户可以重新点击启动项目。

### CHK-009 API Safety

- 关联需求点：高风险确认不能只依赖前端。
- 验证方法：直接调用 reset API，先不带确认参数，再带确认参数。
- 预期结果：存在风险状态时不带确认返回 `confirmationRequired` 与 409；带确认后 reset 成功并返回更新后的 project。

### CHK-010 Persistence Compatibility

- 关联需求点：现有 markdown/json 项目数据兼容。
- 验证方法：对已有项目和新建项目分别执行 reset，重启服务或重新读取项目。
- 预期结果：项目可正常读取；任务状态、顺序、历史字段与 reset 结果一致；无旧项目因缺失新字段而失败。

### CHK-011 Scheduled Cron Regression

- 关联需求点：reset 不影响项目定时任务配置。
- 验证方法：创建项目 scheduled cron，执行两种 reset，再读取 scheduled cron 面板/API。
- 预期结果：cron binding、enabled 状态、schedule、history 不被 reset 删除或篡改。

### CHK-012 Unit Tests

- 关联需求点：核心状态转换可靠。
- 验证方法：新增或更新 Python 单测，覆盖重置任务状态、彻底重置项目、风险确认、顺序保持、历史保留、cron 不变。
- 预期结果：相关单测全部通过，并能防止状态字段误清或顺序回归。

### CHK-013 Frontend Static Tests

- 关联需求点：UI 入口和文案可维护。
- 验证方法：运行 JS 语法检查和 i18n 完整性检查。
- 预期结果：`app/projects.js` 语法通过；中英文 locale key 完整；无未定义文案。

### CHK-014 E2E Acceptance

- 关联需求点：真实用户流程可用。
- 验证方法：启动本地服务，使用浏览器打开项目页，构造或使用测试项目验证按钮、选择弹窗、高风险确认、reset 后看板状态、顺序和可重新启动。
- 预期结果：E2E 观察到用户可完成完整 reset 流程；截图或 DOM 断言证明任务回 backlog、顺序正确、风险确认生效。

### CHK-015 Manual验收

- 关联需求点：最终用户验收。
- 验证方法：开发完成并测试通过后，让用户在本地服务中操作真实项目。
- 预期结果：用户确认 reset 入口、弹窗、确认策略、任务状态、顺序和保留边界符合预期。

## 人工确认记录

- 确认项：checklist 初次确认
- 确认时间：2026-07-07T13:38:04+08:00
- 用户确认摘要：用户回复 "pass"，确认该 checklist 可作为后续实现、测试和 E2E 验收依据。
- 确认项：tested / done
- 确认时间：2026-07-08T11:56:00+08:00
- 用户确认摘要：用户验收项目重置功能通过，并要求标记与提交。

## 测试执行记录

- 执行时间：2026-07-07T14:51:23+08:00
- 自动化测试：
  - `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_project_execution.py`：83 passed
  - `node tests/test_i18n_integrity.js`：通过
  - `node --check app/projects.js`：通过
  - `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py`：通过
- E2E 验收：
  - 本地服务：`http://localhost:8090`
  - 测试项目：`E2E Reset Project 1783406773300`
  - 验证到项目详情页工具栏出现 "重置" 按钮。
  - 点击后出现 "重置任务状态" 与 "彻底重置项目" 两个选择。
  - Backlog/In Progress/Done 分布为 1/1/1 时，选择 "重置任务状态" 后出现高风险确认，文案显示 2 个非初始状态任务并列出 `Beta running`、`Gamma done`。
  - 确认后 Backlog 变为 3 个任务，顺序为 `Alpha backlog`、`Beta running`、`Gamma done`，In Progress/Review/Done 均为 0。
  - 干净 backlog 状态再次选择 "彻底重置项目" 不弹高风险确认，toast 显示处理 0 个任务。
- 当前状态：用户已确认测试通过并完成验收。
