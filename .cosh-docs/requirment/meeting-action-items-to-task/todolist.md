# Todolist

## TODO-001 Model meeting-applied action items on source tasks

- 目标：让原任务能保存会议新增行动项、完成状态和来源关系。
- 涉及区域：`app/server.py` project task data, meeting blocker result handling, task history/activity.
- 输入：meeting id, meeting request id, source project id, source task id, action item id, title, description, owner, priority.
- 输出：source task 上可追踪的 meeting action item records，包含 pending/completed 状态和来源元数据。
- 依赖：无。
- 完成标准：同一会议结果重复应用不会重复插入；任务数据能区分 meeting-created action item 与普通 checklist/todo。
- 关联 checklist：CHK-001, CHK-002, CHK-004, CHK-010, CHK-015.

## TODO-002 Apply approved meeting output before resuming the original task

- 目标：修改 approved meeting result path，先应用会议行动项、决策和风险，再决定是否继续原任务。
- 涉及区域：`_project_execution_apply_meeting_result`, meeting blocker state transitions, project execution restart logic.
- 输入：completed executable meeting result with approved outcome, actionItems, decision, summary, risks/unresolved questions.
- 输出：原任务进入 meeting action item processing/pending 状态，只有必要行动项完成后才恢复执行。
- 依赖：TODO-001.
- 完成标准：approved 会议不会直接跳回原任务执行；无行动项时仍可按原逻辑继续；有未解决问题时保持 blocked/awaiting。
- 关联 checklist：CHK-001, CHK-003, CHK-005, CHK-009, CHK-014.

## TODO-003 Route current-owner and other-owner action items correctly

- 目标：按 owner 将行动项分流：当前执行 agent 的行动项进入原任务，其他 owner 创建关联任务。
- 涉及区域：meeting action item normalization, project task create path, owner/assignee matching, source metadata.
- 输入：meeting actionItems with owner/assignee/responsible fields, current task executor/assignee.
- 输出：current-owner records on source task; other-owner project tasks with backlinks to source task and meeting.
- 依赖：TODO-001.
- 完成标准：多 owner 会议结果能正确分配；关联任务具有 `source.kind = meeting_action_item` 或等价来源标识；archive manager 不可被分配普通任务。
- 关联 checklist：CHK-006, CHK-010, CHK-014.

## TODO-004 Convert decisions and risks into task-visible execution context

- 目标：让会议决策影响后续执行，让会议风险影响 review/verification。
- 涉及区域：task comments/context/checklist/review data, task file writing if applicable, activity logging.
- 输入：meeting result summary, decision, risks, unresolved questions, disagreements.
- 输出：任务详情可见会议决策；风险进入 checklist/review-visible 条目；无共识或未解决问题阻止继续执行。
- 依赖：TODO-001, TODO-002.
- 完成标准：后续 agent prompt/task context 能读到会议决策；风险不只是会议详情文本；未解决问题不会被当作成功会议处理。
- 关联 checklist：CHK-007, CHK-008, CHK-009, CHK-015.

## TODO-005 Complete and check off meeting action items during execution

- 目标：让 agent 在恢复原任务前先处理会议新增行动项，并在完成后打钩。
- 涉及区域：project execution prompt building, execution result parsing/evidence, task action item completion state.
- 输入：source task meeting action items in pending state.
- 输出：completed/check-off state updates and activity records.
- 依赖：TODO-001, TODO-002.
- 完成标准：执行日志显示先处理会议行动项；全部 required action items completed 后才继续原任务；失败或未完成时不误恢复。
- 关联 checklist：CHK-003, CHK-004, CHK-005, CHK-015.

## TODO-006 Surface meeting action item status in task UI

- 目标：用户能在原任务详情中看到会议新增行动项、owner、来源会议、完成状态和阻塞关系。
- 涉及区域：`app/game.js` project task detail UI, localization strings, status badges/buttons if needed.
- 输入：task meeting action item data and linked task data.
- 输出：中文/英文 UI 展示 meeting-applied action items and status.
- 依赖：TODO-001.
- 完成标准：中文环境无英文占位；英文环境无中文硬编码；状态不会隐藏在 raw JSON 或不可见活动里。
- 关联 checklist：CHK-012, CHK-013, CHK-015.

## TODO-007 Preserve general meeting draft behavior

- 目标：确保非项目任务阻塞来源的普通会议仍使用手动 action item drafts。
- 涉及区域：meeting action item draft UI/API, meeting result application guard conditions.
- 输入：ordinary executable meetings without source task blocker.
- 输出：普通会议不自动改写项目任务；仍可手动创建任务。
- 依赖：TODO-002.
- 完成标准：普通会议行动项草稿 UI 与手动创建任务能力保持可用。
- 关联 checklist：CHK-011, CHK-014.

## TODO-008 Add automated regression tests

- 目标：用自动化测试覆盖会议结果应用、行动项完成门控、幂等和普通会议回归。
- 涉及区域：existing Python tests under `tests/`, possible focused server-level tests.
- 输入：fixture projects, source task, meeting result payloads.
- 输出：可重复运行的测试用例。
- 依赖：TODO-001, TODO-002, TODO-003, TODO-004, TODO-005.
- 完成标准：测试覆盖 approved with action items, no action items, no consensus, duplicate application, multi-owner routing, ordinary meeting drafts.
- 关联 checklist：CHK-001, CHK-003, CHK-006, CHK-009, CHK-010, CHK-011, CHK-014.

## TODO-009 Run MCP/browser acceptance on a real project fixture

- 目标：使用真实本地服务和 MCP/browser 验证用户可见流程。
- 涉及区域：local service, shared browser/MCP testing flow, project UI.
- 输入：sample project with task-triggered AI meeting and meeting result action items.
- 输出：验收记录：任务详情、行动项状态、原任务恢复、普通会议回归。
- 依赖：TODO-006, TODO-008.
- 完成标准：至少验证一个 current-owner action item 被添加、完成、打钩并恢复原任务；验证多 owner 或普通会议不回归。
- 关联 checklist：CHK-002, CHK-004, CHK-005, CHK-011, CHK-012, CHK-013, CHK-015.

## TODO-010 Update requirement artifacts after implementation

- 目标：把实现结果、测试结果和人工验收记录写回需求归档。
- 涉及区域：`.cosh-docs/requirment/meeting-action-items-to-task/`.
- 输入：implementation summary, test output, MCP/browser verification notes, user confirmations.
- 输出：updated checklist/status and eventual archive move after done confirmation.
- 依赖：TODO-008, TODO-009.
- 完成标准：测试通过后等待用户确认 tested；最终用户确认 done 后归档到 archive。
- 关联 checklist：CHK-015.
