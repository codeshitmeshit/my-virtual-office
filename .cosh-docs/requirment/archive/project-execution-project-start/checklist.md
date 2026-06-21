# Project Execution Project Start Checklist

确认状态：已确认

## 验收规则

- 本 checklist 确认前不得生成 todolist。
- Project Execution 项目级启动不得回退到旧 workflow 引擎。
- 普通项目旧 workflow 行为必须保持不变。
- Project Execution 项目级启动需要提供“启动下一个任务 / 连续启动任务”的单选控制。
- 默认启动模式为“连续启动任务”。
- 连续启动不得绕过 Project Execution 审查；遇到需要人工验收的任务必须停住。
- 所有执行验证应使用可控测试项目和临时工作区。

## Checklist

### CHK-001 Project Execution 项目显示启动按钮
- 验证方法：打开启用 Project Execution 的项目看板。
- 预期结果：toolbar 显示项目级“启动项目”或等价按钮，并显示“启动下一个任务 / 连续启动任务”单选控制；不需要打开任务详情才能发现启动入口。
- 关联需求点：Project Execution 项目保留项目级启动体验。

### CHK-001A 默认连续启动任务
- 验证方法：打开新建 Project Execution 项目或刷新已有项目看板。
- 预期结果：项目启动方式默认选中“连续启动任务”。
- 关联需求点：默认项目级启动使用连续 task 流。

### CHK-002 普通项目 workflow 控件不变
- 验证方法：打开普通项目看板。
- 预期结果：旧的 workflow start/stop/auto-mode 控件仍按原逻辑显示和工作。
- 关联需求点：普通项目兼容旧 workflow。

### CHK-003 启动下一个任务模式选择第一个 eligible task
- 验证方法：选择“启动下一个任务”，创建多列多任务 Project Execution 项目，设置不同 column order 和 task order，然后点击项目级启动。
- 预期结果：系统启动按列顺序和任务顺序排序后的第一个可启动任务。
- 关联需求点：项目级 start 映射到 next eligible task。

### CHK-003A 启动下一个任务模式不自动继续
- 验证方法：选择“启动下一个任务”，让被选任务完成执行和审查。
- 预期结果：任务完成或进入验收/终态后，系统不自动启动下一个任务。
- 关联需求点：单任务启动模式语义清晰。

### CHK-003B 连续启动任务模式自动推进
- 验证方法：选择“连续启动任务”，准备多个不需要人工验收且可通过审查的任务。
- 预期结果：前一个任务审查通过后，系统自动选择并启动下一个 eligible task，直到无任务或出现停止条件。
- 关联需求点：项目级连续 task 流调用。

### CHK-004 跳过 Done 类列
- 验证方法：在 Done/Completed/Verified 等完成列中放置任务，同时 Backlog 中有任务。
- 预期结果：项目级启动不会选择完成列任务，而是选择非完成列中的 eligible task。
- 关联需求点：任务选择规则不重启已完成任务。

### CHK-005 无任务时给出清晰提示
- 验证方法：打开没有任何任务的 Project Execution 项目并点击项目级启动。
- 预期结果：不报未知错误；提示用户没有可启动任务或需要先添加任务。
- 关联需求点：空项目可理解。

### CHK-006 无 eligible task 时给出清晰提示
- 验证方法：项目中只有已完成任务、不可启动状态任务或无非完成列任务时点击项目级启动。
- 预期结果：提示没有可启动任务。
- 关联需求点：边界状态清晰。

### CHK-007 缺少 executor 时复用角色错误
- 验证方法：创建没有 task executor、assignee、project default executor 的 Project Execution 项目并点击项目级启动。
- 预期结果：返回并展示有效 executor required 类错误。
- 关联需求点：不绕过执行 Agent 要求。

### CHK-008 缺少 reviewer 时复用角色错误
- 验证方法：创建没有 task reviewer 和 project default reviewer 的 Project Execution 项目并点击项目级启动。
- 预期结果：返回并展示 reviewer required 类错误。
- 关联需求点：不绕过独立审查要求。

### CHK-009 已有 active task 时阻止重复启动
- 验证方法：让一个任务处于 executing/reviewing/reworking 等 active 状态，再点击项目级启动。
- 预期结果：接口返回 active task conflict，UI 显示已有任务正在执行。
- 关联需求点：同项目同时只执行一个 Project Execution task。

### CHK-010 Dirty worktree confirmation 保持可用
- 验证方法：绑定 git workspace 且存在 dirty files，点击项目级启动。
- 预期结果：返回或展示 dirty confirmation；用户确认后能启动同一个 selected task。
- 关联需求点：复用现有任务启动安全机制。

### CHK-011 状态流复用任务级 Project Execution
- 验证方法：项目级启动后观察被选任务状态。
- 预期结果：任务进入 existing Project Execution state machine，如 executing、execution_complete、reviewing、awaiting_user_acceptance；不会创建独立的项目级状态流。
- 关联需求点：保持任务级证据、审查和验收。

### CHK-011A 创建任务时可设置是否需要人工验收
- 验证方法：在 Project Execution 项目中创建任务。
- 预期结果：创建任务流程明确提供“需要人工验收”配置，并能保存到任务。
- 关联需求点：任务级人工验收配置。

### CHK-011B 控制面板显示并可调整人工验收标记
- 验证方法：打开任务详情或 Project Execution 控制面板。
- 预期结果：用户能看到当前任务是否需要人工验收，并能按产品设计调整该标记。
- 关联需求点：控制面板标记需要用户验收。

### CHK-011C 需要人工验收的任务会停止连续流
- 验证方法：连续启动任务模式下，让一个标记为需要人工验收的任务审查通过。
- 预期结果：项目进入等待用户验收状态，不自动启动下一个任务；控制面板明确提示需要用户验收。
- 关联需求点：连续流保留人工验收停止点。

### CHK-011D 不需要人工验收的任务审查通过后自动继续
- 验证方法：连续启动任务模式下，让一个标记为不需要人工验收的任务审查通过，且后面还有 eligible task。
- 预期结果：系统不等待用户验收，自动启动下一个 eligible task。
- 关联需求点：不需验收任务支持连续推进。

### CHK-012 任务详情启动仍可用
- 验证方法：打开某个任务详情，点击“启动此任务”。
- 预期结果：原任务级启动行为不受影响。
- 关联需求点：保留精确启动某个任务能力。

### CHK-013 Toolbar 状态可理解
- 验证方法：项目级启动后观察 toolbar 状态。
- 预期结果：toolbar 显示 executing/reviewing/blocked/awaiting_user_acceptance 等当前项目执行状态或 active task 信息，并能看出当前启动模式。
- 关联需求点：用户知道项目为什么不能再次启动或下一步要做什么。

### CHK-014 API 返回 selected task 信息
- 验证方法：直接调用项目级启动 API。
- 预期结果：成功响应包含 selected `taskId`、`attemptId`、启动模式和该任务是否需要人工验收；错误响应包含可操作错误。
- 关联需求点：项目级启动作为 task start coordinator。

### CHK-015 回归 Project Execution 审查验收
- 验证方法：通过项目级启动完成一次执行、审查、用户验收流程。
- 预期结果：审查、返工、阻塞、验收通过逻辑与任务级启动一致。
- 关联需求点：不破坏 Project Execution 核心闭环。

### CHK-016 回归现有自动工作区项目创建
- 验证方法：创建默认可执行项目，不填写工作区，然后使用项目级启动。
- 预期结果：自动工作区仍创建成功；项目级启动能在该工作区执行任务。
- 关联需求点：与默认可执行项目体验闭环。

### CHK-017 前端错误展示
- 验证方法：触发无任务、缺角色、active task conflict、dirty confirmation 场景。
- 预期结果：前端展示明确 toast/提示，不静默失败。
- 关联需求点：用户能理解为什么项目未启动。

### CHK-017A 连续流停止条件展示
- 验证方法：连续启动任务模式下分别触发无 eligible task、缺角色、dirty confirmation、审查失败、阻塞、需要人工验收。
- 预期结果：前端清楚显示连续流为什么停止，以及用户下一步可做什么。
- 关联需求点：连续 task 流可理解且可控。

### CHK-018 自动化与静态检查
- 验证方法：运行 Project Execution focused tests、项目 CRUD 回归、前端语法检查和 diff 检查。
- 预期结果：全部通过，且无新增语法或 whitespace 问题。
- 关联需求点：不破坏现有项目管理和执行流程。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-16T16:07:31+08:00
- 用户确认摘要：用户回复“pass”，确认本 checklist 可作为后续 todolist 和实现验收依据。

## 测试执行记录

- 执行时间：2026-06-16T16:33:22+08:00
- 执行项：`python3 -m py_compile app/server.py app/project_store.py tests/test_project_execution.py`
- 结果：通过。

- 执行时间：2026-06-16T16:33:22+08:00
- 执行项：`node --check app/projects.js`
- 结果：通过。

- 执行时间：2026-06-16T16:33:22+08:00
- 执行项：`.venv/bin/python tests/test_project_execution.py`
- 结果：通过。输出包含既有非致命提示：gateway session abort failed，但进程退出 `ok`。

- 执行时间：2026-06-16T16:33:22+08:00
- 执行项：`bash tests/test_crud_projects.sh http://127.0.0.1:8090`
- 结果：通过，5/5 passed。

- 执行时间：2026-06-16T16:33:22+08:00
- 执行项：HTTP 冒烟验证。
- 结果：通过。创建默认可执行项目时自动创建工作区，默认 `projectExecutionStartMode` 为 `continuous`；空项目调用 `/project-execution/start` 返回 `no_eligible_task`；删除项目时自动工作区删除成功。

- 执行时间：2026-06-16T16:33:22+08:00
- 执行项：`git diff --check`
- 结果：通过。

- 执行时间：2026-06-16T16:46:02+08:00
- 执行项：chrome-devtools 真实浏览器验证，访问沙箱外 `start.sh` 启动的 `http://127.0.0.1:8090`。
- 结果：通过。页面加载 `projects.js` 成功；真实页面中创建默认可执行项目，验证 toolbar 显示“启动项目”“启动下一个任务”“连续启动任务”，默认选中连续模式；创建任务时保存 `requiresUserAcceptance: true`；项目级 start 在缺 executor 时返回清晰 `executor_required`；临时项目和自动工作区清理成功。
- 截图：`/tmp/project-execution-project-start-chrome-dev.png`
- Console/Network：无本功能非预期错误；console 中 409 为刻意触发的缺 executor 验证，pointer-lock 为浏览器 feature 警告。

- 执行时间：2026-06-16T17:59:02+08:00
- 执行项：缺 Reviewer 启动提示与跳过审查确认验证。
- 结果：通过。项目级启动在缺 Reviewer 时返回 `reviewer_skip_confirmation_required`，项目状态写入同名 `workflowPhase` 和 `projectExecutionFlowStopReason`；前端会弹出“没有 Reviewer，是否确认跳过独立审查并继续执行”的确认。用户确认后后端允许执行，并在执行完成后跳过 review，按任务人工验收设置进入等待验收或直接完成。

## 验收与归档确认记录

- 确认项：tested
- 确认时间：2026-06-17T03:05:27+08:00
- 用户确认摘要：用户确认验收通过，可以归档。

- 确认项：done
- 确认时间：2026-06-17T03:05:27+08:00
- 用户确认摘要：用户确认验收通过，并请求将该需求归档为完成。
