# Checklist

确认状态：已确认

## Acceptance Checklist

### CHK-001 Meeting result applies to source task

- 验证方法：创建一个正在执行的项目任务，让该任务触发 AI 会议并产生 approved 会议结果。
- 预期结果：会议完成后，会议结果写回原任务，而不是只停留在会议详情或行动项草稿里。
- 关联需求点：会议内容落实到触发会议的 task。

### CHK-002 Current-agent action items become pending task work

- 验证方法：会议结果包含 owner 为当前执行 agent 的 action item。
- 预期结果：该 action item 被添加到原任务的 backlog/todo/待办区域，并带有未完成状态。
- 关联需求点：当前执行 agent 的会议行动项合并进当前 task。

### CHK-003 Original task does not resume before meeting action items complete

- 验证方法：会议 approved 后检查任务状态和执行日志，保持至少一个会议新增行动项未完成。
- 预期结果：原任务不会直接继续原始执行内容；系统先处理会议新增行动项。
- 关联需求点：完成会议制定的行动项之后再继续原任务。

### CHK-004 Meeting action items are checked after completion

- 验证方法：让 agent 完成会议新增行动项，观察任务待办/checklist 状态。
- 预期结果：已完成行动项被打钩或标记为 completed，并保留来源会议信息。
- 关联需求点：执行完行动项后打钩。

### CHK-005 Original task resumes after required action items are checked

- 验证方法：完成并打钩所有当前-agent meeting action items。
- 预期结果：原任务自动从会议行动项处理阶段恢复正常执行，并继续进入后续 review/验收流程。
- 关联需求点：会议行动项全部完成后继续原任务。

### CHK-006 Multi-owner action items are routed correctly

- 验证方法：会议结果同时包含当前 agent 和另一个 AI owner 的行动项。
- 预期结果：当前 agent 的行动项进入原任务；其他 owner 的行动项创建关联项目任务，并保留与原任务、会议的来源关系。
- 关联需求点：多 owner 场景中当前 agent 与其他 owner 的不同处理方式。

### CHK-007 Meeting decision is visible in task context

- 验证方法：会议结果包含明确 decision/summary。
- 预期结果：原任务中可查看会议决策内容，后续 agent 执行时可以获得该上下文。
- 关联需求点：会议决策写入任务上下文。

### CHK-008 Meeting risks affect verification

- 验证方法：会议结果包含风险或注意事项。
- 预期结果：风险进入任务 checklist/review-visible 内容，不只是普通会议记录。
- 关联需求点：会议风险进入验收/检查项。

### CHK-009 No-consensus meeting keeps task blocked

- 验证方法：构造 no_consensus/rejected 或仍有未解决问题的会议结果。
- 预期结果：原任务保持 `awaiting_meeting_resolution` 或 blocked，不会新增执行阶段并继续原任务。
- 关联需求点：会议未解决问题时不继续执行。

### CHK-010 Idempotent meeting application

- 验证方法：重复触发同一个会议结果应用逻辑，或刷新/重试完成事件。
- 预期结果：不会重复添加同一个行动项、重复创建同一个关联任务、重复追加大量相同评论。
- 关联需求点：会议结果可安全重复应用。

### CHK-011 General meeting action item draft behavior remains available

- 验证方法：创建非项目任务阻塞来源的普通 AI 会议并产生 action items。
- 预期结果：普通会议仍可展示行动项草稿，并可由用户手动创建任务；不会被强制自动合并到某个任务。
- 关联需求点：不回归普通会议行动项能力。

### CHK-012 Localization is complete

- 验证方法：分别查看中文和英文界面中的会议行动项、任务待办、状态提示、按钮和错误消息。
- 预期结果：新增 UI 文案中英文均完整，中文环境不出现英文占位，英文环境不出现中文硬编码。
- 关联需求点：现有产品要求注意汉化与非汉化文案。

### CHK-013 UI exposes meeting-added action item status

- 验证方法：打开原项目任务详情，查看会议新增行动项。
- 预期结果：用户能看到每个会议行动项的标题、owner、来源会议、完成状态，以及是否阻塞原任务继续。
- 关联需求点：用户可检查会议内容如何落实到 task。

### CHK-014 Existing project execution regressions

- 验证方法：运行或手动验证普通 project execution：无会议任务、需要 review 的任务、需要用户验收的任务。
- 预期结果：普通任务状态机、review、用户验收、返工流程不受影响。
- 关联需求点：兼容现有项目执行流程。

### CHK-015 Observability and activity history

- 验证方法：查看项目 activity、任务 state history、会议 event history。
- 预期结果：会议结果应用、行动项添加、行动项完成、原任务恢复执行都有可追踪记录。
- 关联需求点：可观测、可验收、可排查。

## 人工确认记录

- checklist 确认时间：2026-06-23T21:13:52+08:00
- 确认人：user
- 确认摘要：pass

## 测试执行记录

- 执行时间：2026-06-23T22:00:58+08:00
- 自动化测试：
  - `.venv/bin/python tests/test_meeting_request_blocks_task.py`
  - `.venv/bin/python tests/test_project_execution.py`
  - `node --check app/projects.js`
  - `python3 -m json.tool app/locales/en.json`
  - `python3 -m json.tool app/locales/zh.json`
- 真实数据/UI 验证：
  - `.venv/bin/python tests/seed_meeting_action_items_fixture.py`
  - `node tests/chrome_meeting_action_items_task_check.mjs`
- 验证结果：
  - 会议 approved 后，当前执行 agent 的行动项写回原任务并保持 pending。
  - 其他 owner 的行动项创建关联项目任务。
  - 任务详情展示会议行动项区块，包含 pending 与 linked task 状态。
  - 任务验收 checklist 会保留为交付物验收标准；会议行动项和会议风险在任务详情的独立会议区块/讨论区块可见，不混入验收 checklist。
  - meeting action phase 完成后会打钩行动项，再恢复原任务执行。
- MCP 说明：
  - `mcp__chrome_devtools` 本次启动时报缺少 X server，无法直接使用该 MCP 的 headful 页面工具。
  - 已使用仓库现有 Chrome DevTools/CDP 验证方式进行等价真实 UI 验证，连接同一类 CDP 端口并访问本地服务。

## 修正验证记录

- 执行时间：2026-06-25T23:30:54+08:00
- 问题：任务阻塞会议生成了会议行动项，但原任务验收 checklist 仍为空，界面显示 `0/0`。
- 修正：会议结果应用到任务时，如果原任务没有交付物验收 checklist，会兜底生成最小验收清单；会议行动项和会议风险仍保持在独立数据区块，不作为 checklist 条目。
- 验证：`.venv/bin/python tests/test_meeting_request_blocks_task.py` 通过，覆盖首次生成、重复应用不重复生成、会议行动项不混入 checklist。
