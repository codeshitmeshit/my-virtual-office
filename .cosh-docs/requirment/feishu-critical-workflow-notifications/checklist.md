# Checklist

确认状态：已确认

## 验收标准

### CHK-001 Project Execution acceptance notification is sent

- 关联需求点：Project Execution task reaches `awaiting_user_acceptance`.
- 验证方法：Create or simulate a Project Execution task that passes review and requires user acceptance.
- 预期结果：Exactly one Feishu application-form notification is recorded and sent for that acceptance event, with project, task, attempt, summary, and open-VO action.

### CHK-002 Acceptance card can accept the task

- 关联需求点：User can accept directly from Feishu.
- 验证方法：Invoke the Feishu card action payload for the acceptance action with the current project ID, task ID, and attempt ID.
- 预期结果：The task is accepted through the existing Project Execution acceptance flow, stale actions are rejected, and the Feishu callback returns a success toast.

### CHK-003 Acceptance card can request rework with default feedback

- 关联需求点：User can request rework from Feishu without typing custom feedback.
- 验证方法：Invoke the Feishu card action payload for the rework action.
- 预期结果：The task enters the existing rework flow using the default Feishu feedback message, or returns a clear error toast if rework cannot start.

### CHK-004 Blocked Project Execution notification is sent once

- 关联需求点：`blocked` always notifies.
- 验证方法：Create or simulate representative blocked states, including executor blocked, reviewer blocked, missing workspace, missing role, and user-marked blocked where applicable.
- 预期结果：Each unique blocked event sends or records one Feishu notification with enough context to open the related project/task. Repeated status reads or repair passes do not resend the same event.

### CHK-005 Transient failures do not notify before automatic recovery is exhausted

- 关联需求点：failed notifies only when user intervention is needed.
- 验证方法：Simulate a transient executor failure that schedules automatic retry.
- 预期结果：No Feishu blocked/failed notification is sent for the transient failure before retry exhaustion or actual blocked transition.

### CHK-006 User-intervention failures notify clearly

- 关联需求点：failed requiring user intervention notifies.
- 验证方法：Simulate failures caused by missing configuration, permissions, workspace access, unavailable context, or exhausted automatic recovery.
- 预期结果：Feishu notification explains that user intervention is needed, includes sanitized reason details, and provides an open-project/task action.

### CHK-007 Meeting failure notification is sent for failed meetings only

- 关联需求点：Notify failed AI meetings; do not notify normal action items or normal completion.
- 验证方法：Simulate moderator failure or other meeting failure that requires user attention, and separately simulate normal meeting completion with action items.
- 预期结果：Failure sends one Feishu error notification with open-meeting action. Normal completion and normal action items send no Feishu notification.

### CHK-008 Feishu notification config behavior remains unchanged

- 关联需求点：Use existing configured receiver.
- 验证方法：Run existing Feishu notification config and test-card flows with app config and webhook fallback where available.
- 预期结果：Existing config endpoints, masked secrets, long connection startup, and manual test cards continue to work.

### CHK-009 Card action dispatcher remains backward compatible

- 关联需求点：Existing meeting request Feishu actions must keep working.
- 验证方法：Run existing meeting request card action tests or equivalent confirm/reject action simulations.
- 预期结果：Meeting request confirm/reject behavior is unchanged while new Project Execution actions are handled.

### CHK-010 Notification content is safe and concise

- 关联需求点：No sensitive leakage or noisy diagnostics.
- 验证方法：Send notifications with errors containing webhook URLs, tokens, secrets, long output, and multiline diagnostics.
- 预期结果：Secrets are redacted, long text is truncated, and cards remain readable.

### CHK-011 Send records and action records are auditable

- 关联需求点：Use existing notification module and observability.
- 验证方法：Inspect `feishu-notification-records.jsonl` and `feishu-card-actions.jsonl` after notifications and actions.
- 预期结果：Records include notification ID, type, title, related object, target, send status, channel, and action outcome without exposing secrets.

### CHK-012 Missing Feishu configuration is non-blocking

- 关联需求点：Notifications should not break VO workflows.
- 验证方法：Run acceptance, blocked, and meeting failure flows with Feishu config missing or disabled.
- 预期结果：VO workflow proceeds normally; notification result records skipped/disabled/missing config status without raising workflow-breaking errors.

### CHK-013 Regression coverage for Project Execution workflow

- 关联需求点：Do not change core Project Execution semantics.
- 验证方法：Run focused Project Execution tests covering start, review pass, awaiting acceptance, accept, rework, blocked, and continuous flow continuation.
- 预期结果：Existing task state transitions and project flow behavior remain correct.

### CHK-014 Manual verification in VO UI

- 关联需求点：Open actions should lead the user to the right VO context.
- 验证方法：Open Feishu notification jump links for acceptance, blocked task, and failed meeting.
- 预期结果：The user lands in a VO context where the relevant project/task/meeting can be inspected and acted on.

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-07-03T01:08:55+08:00
- 用户确认摘要：用户回复 `continue`，视为确认当前 checklist 并继续生成 todolist。

## 测试执行记录

- 执行时间：2026-07-03T01:30:28+08:00
- CHK-001/002/003：通过 `tests.test_project_execution` 聚焦用例验证 acceptance 通知、接受按钮、返工按钮和默认返工反馈。
- CHK-004/005/006：通过 Project Execution 聚焦用例验证 blocked 通知、start failure 去重持久化、transient retry 不通知、敏感信息脱敏。
- CHK-007：通过 `tests/test_meeting_for_ai_phase6.py` 验证 moderator failure 发送一次会议失败通知，正常 action item 会议不发送失败通知。
- CHK-008/009/011/012：通过 `tests/test_feishu_notifications.py`、`tests/test_meeting_request_blocks_task.py` 和新增 card action 记录断言验证现有 Feishu 配置、会议申请动作、记录与缺配置非阻塞行为。
- CHK-010：通过 Project Execution 和 meeting failure 测试验证 `password=hunter2` 等敏感文本不会进入通知 intent。
- CHK-013：通过 Project Execution 聚焦回归验证验收、返工、失败、retry、start failure 行为；既有自动 done 回归在 stub 掉 archive trigger 后通过，完整文件 runner 会被既有 archive manager gateway 等待阻塞。
- CHK-014：未执行真实 Feishu/浏览器手工验证；当前只验证了生成的 jump URL 形态。

追加执行记录：

- 执行时间：2026-07-03T07:33:32+08:00
- 追加范围：在 Project Execution 项目级流程完成后发送 Feishu 通知。
- 验证结果：`test_project_level_start_skips_done_columns_and_reports_no_eligible_task` 覆盖空项目不通知、已有完成任务且无可执行任务时发送一次 `feishu-project-execution-complete` 通知、重复 no-eligible 收口不重复发送。
- 追加命令：

```bash
.venv/bin/python -m py_compile app/server.py app/project_store.py tests/test_project_execution.py
.venv/bin/python - <<'PY'
import tests.test_project_execution as t
t.test_project_level_start_skips_done_columns_and_reports_no_eligible_task()
t.test_project_store_round_trip_and_legacy_defaults()
print('project complete notification tests passed')
PY
.venv/bin/python - <<'PY'
import tests.test_project_execution as t
t.test_feishu_start_failure_notification_dedupes_after_persisted_reload()
t.test_execution_failure_blocks_with_redacted_bounded_evidence()
print('feishu project notification regression passed')
PY
```

已运行命令：

```bash
.venv/bin/python -m py_compile app/server.py app/project_store.py tests/test_project_execution.py tests/test_meeting_for_ai_phase6.py
.venv/bin/python tests/test_feishu_notifications.py
.venv/bin/python tests/test_meeting_request_blocks_task.py
.venv/bin/python tests/test_meeting_for_ai_phase6.py
.venv/bin/python - <<'PY'
import tests.test_project_execution as t
names=[
 'test_project_store_round_trip_and_legacy_defaults',
 'test_execution_failure_blocks_with_redacted_bounded_evidence',
 'test_transient_gateway_timeout_retries_once_before_blocking',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_acceptance_reject_and_mark_blocked_require_feedback_and_invalidate_pass',
]
for name in names:
    getattr(t,name)()
PY
```
