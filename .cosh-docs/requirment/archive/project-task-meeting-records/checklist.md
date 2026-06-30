# Project Task Meeting Records Checklist

确认状态：已确认

## 验收标准

### CHK-001 Task-triggered meeting records are persisted

- 验证方法：从项目任务执行中发起并完成一场 AI 会议，查看任务数据。
- 预期结果：该任务持久化保存会议记录，至少包含 meetingId、requestId、会议结果状态、结论文本和记录时间。
- 关联需求点：只记录项目任务内召开的会议。

### CHK-002 Approved meeting conclusion appears in task detail

- 验证方法：完成一场 outcome 为 approved 的任务会议，打开任务详情。
- 预期结果：任务详情中的会议记录模块展示会议结论，不需要进入会议详情页才能看到最终结论。
- 关联需求点：用户可在任务里快速看到会议最终结论。

### CHK-003 Risks appear with the meeting record

- 验证方法：会议结果包含 risks，打开任务详情。
- 预期结果：会议记录模块能看到风险信息；风险不混入任务验收 checklist。
- 关联需求点：会议记录包含风险。

### CHK-004 Follow-up action items remain visible and linked to meeting context

- 验证方法：会议结果包含 action items，打开任务详情。
- 预期结果：行动项在任务会议行动项区域可见，并能从 meetingId 或同等上下文知道来源会议；会议记录模块能让用户理解行动项来自哪次会议。
- 关联需求点：会议记录包含后续行动项信息，但不替代行动项执行区。

### CHK-005 Multiple task meetings are listed in chronological order

- 验证方法：同一任务触发两次或更多会议，并分别产生结论。
- 预期结果：任务详情列出所有任务触发的会议记录，按时间顺序展示，不只保留最新一次。
- 关联需求点：多个会议按时间列出。

### CHK-006 No-consensus and rejected meetings are recorded

- 验证方法：构造 no_consensus 和 rejected 会议结果。
- 预期结果：任务会议记录模块显示未达成共识或不通过的结论状态，并解释任务为何阻塞或等待处理。
- 关联需求点：无共识会议也要记录。

### CHK-007 Needs-user-decision meetings are recorded

- 验证方法：构造需要用户决策的会议结果或会议状态。
- 预期结果：任务会议记录模块显示需要用户决策状态；任务仍按既有规则等待用户处理。
- 关联需求点：没有明确结论的会议也应解释任务状态。

### CHK-008 Non-task meetings do not pollute task records

- 验证方法：创建普通项目会议或非任务来源会议。
- 预期结果：无关会议不会出现在任意任务的会议记录模块中。
- 关联需求点：只记录项目任务里面召开的会议。

### CHK-009 Idempotent result application

- 验证方法：重复应用同一个会议结果或重复刷新完成事件。
- 预期结果：任务会议记录、风险和行动项不会重复生成。
- 关联需求点：会议记录可追溯但不能重复污染。

### CHK-010 Existing meeting action item behavior does not regress

- 验证方法：运行已有会议行动项流程，检查 pending/completed 状态和原任务恢复逻辑。
- 预期结果：行动项仍独立显示和执行；不被会议记录模块吞掉，也不进入验收 checklist。
- 关联需求点：会议记录和行动项职责分离。

### CHK-011 Existing acceptance checklist behavior does not regress

- 验证方法：任务有会议记录、风险和行动项时，检查验收 checklist。
- 预期结果：验收 checklist 仍只表示交付物验收标准；会议记录、风险、行动项不作为 checklist 条目。
- 关联需求点：会议记录不替代验收 checklist。

### CHK-012 Localization is complete

- 验证方法：分别在中文和英文界面查看会议记录模块标题、状态、字段标签。
- 预期结果：中文界面无英文占位，英文界面无中文硬编码；现有硬编码标题应被本地化文案替换。
- 关联需求点：任务详情中会议记录模块清晰可读。

### CHK-013 Activity and audit trail remain traceable

- 验证方法：查看项目 activity、任务 state history、会议详情和任务会议记录。
- 预期结果：能追踪会议如何影响任务状态，包含会议 ID、请求 ID 和结果状态。
- 关联需求点：用户可追溯任务为什么进入当前状态。

### CHK-014 UI remains scan-friendly

- 验证方法：构造包含多条会议记录、多条行动项和风险的任务详情。
- 预期结果：任务详情不出现内容重叠、超长文本撑破、记录难以区分的问题。
- 关联需求点：会议记录模块提供摘要，不复制完整会议过程。

### CHK-015 Regression tests cover the meeting record contract

- 验证方法：运行后端相关测试和至少一个 UI/DOM 验证。
- 预期结果：测试覆盖 approved、no_consensus/rejected、needs-user-decision、多会议、幂等和非任务会议隔离。
- 关联需求点：主要流程和边界都有可重复验证。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-25T23:48:28+08:00
- 用户确认摘要：用户回复 `pass`，确认当前验收清单可作为后续开发和测试依据。

## 测试执行记录

- 执行时间：2026-06-26T00:18:40+08:00
- `node --check app/projects.js`：通过。
- `node --check tests/chrome_project_meeting_records_check.mjs`：通过。
- `python3 -m json.tool app/locales/en.json`：通过。
- `python3 -m json.tool app/locales/zh.json`：通过。
- `.venv/bin/python tests/test_project_execution.py`：通过；过程中出现本地 Gateway 未运行的连接拒绝日志，测试按预期使用降级路径并退出 0。
- `.venv/bin/python tests/test_meeting_request_blocks_task.py`：通过。
- `node tests/check_project_meeting_records_ui.mjs`：通过。
- `node tests/check_project_polling_preserves_detail.mjs`：通过。
- `node tests/test_i18n_integrity.js`：通过。
- `.venv/bin/python tests/test_meeting_for_ai_phase6.py`：通过。
- `VO_LIVE_URL=http://192.168.100.3:8148/ VO_API_URL=http://127.0.0.1:8148 node tests/chrome_project_meeting_records_check.mjs`：通过；临时服务在 `VO_PORT=8148`、`VO_STATUS_DIR=/tmp/vo-meeting-records-ui` 下启动，脚本创建临时项目和任务，真实 Chrome 页面确认显示 2 条会议记录、风险和会议行动项，测试后清理临时项目并关闭临时服务。

## 复测记录

- 复测时间：2026-06-26T00:35:35+08:00
- 服务状态：`http://127.0.0.1:8090/health` 返回 `{"ok": true, "status": "running"}`；Chrome CDP `127.0.0.1:9224` 可用。
- `node --check app/projects.js`：通过。
- `node --check tests/chrome_project_meeting_records_check.mjs`：通过。
- `python3 -m json.tool app/locales/en.json`：通过。
- `python3 -m json.tool app/locales/zh.json`：通过。
- `.venv/bin/python tests/test_project_execution.py`：通过；本地 Gateway 未运行时出现预期连接拒绝降级日志，退出码 0。
- `.venv/bin/python tests/test_meeting_request_blocks_task.py`：通过。
- `node tests/check_project_meeting_records_ui.mjs`：通过。
- `node tests/check_project_polling_preserves_detail.mjs`：通过。
- `node tests/test_i18n_integrity.js`：通过，结果为 `i18n integrity ok: 1729 keys, 1004 static references`。
- `.venv/bin/python tests/test_meeting_for_ai_phase6.py`：通过。
- `VO_LIVE_URL=http://192.168.100.3:8090/ VO_API_URL=http://127.0.0.1:8090 node tests/chrome_project_meeting_records_check.mjs`：通过；真实 Chrome 页面确认会议记录模块显示 2 条记录、风险和会议行动项。

## 最终验收记录

- 确认项：tested
- 确认时间：2026-06-27T00:23:32+08:00
- 用户确认摘要：用户确认该需求可以验收，认可当前实现与测试结果。

- 确认项：done
- 确认时间：2026-06-27T00:23:32+08:00
- 用户确认摘要：用户明确表示“这个需求可以验收了”，需求闭环完成并归档。
