# Todolist

## TODO-001 Inventory current Feishu notification and workflow hooks

- 目标：确认现有 Feishu 发送、记录、卡片动作、Project Execution 状态流和会议失败状态的准确挂接点。
- 涉及区域：`app/feishu_notifications.py`, `app/feishu_long_connection.py`, `app/server.py`, existing Feishu and Project Execution tests.
- 输入：`requirement.md`, `review.md`, existing code paths for meeting request notifications and Project Execution.
- 输出：Implementation notes or inline decisions reflected in later changes.
- 依赖：None.
- 完成标准：Identify where to send acceptance, blocked/intervention, and meeting failure notifications, and where to dispatch new Feishu card actions without breaking meeting request actions.
- 关联 checklist：CHK-001, CHK-004, CHK-007, CHK-008, CHK-009.

## TODO-002 Add shared Feishu notification helpers for critical workflows

- 目标：Create focused helpers for Project Execution acceptance, Project Execution blocked/intervention, and meeting failure notification intents.
- 涉及区域：`app/server.py` Feishu helper area and related status utilities.
- 输入：Existing `send_feishu_notification`, `VO_CONFIG.notifications`, `STATUS_DIR`, Project Execution project/task/attempt objects, meeting objects.
- 输出：Reusable helper functions that build safe notification intents and call the existing Feishu sender.
- 依赖：TODO-001.
- 完成标准：Helpers use existing configured receiver, app config/webhook fallback, safe summaries/details, open-VO jump actions, and non-blocking send behavior.
- 关联 checklist：CHK-001, CHK-006, CHK-007, CHK-010, CHK-012.

## TODO-003 Implement dedupe markers for notification events

- 目标：Prevent repeated Feishu notifications for the same acceptance, blocked/intervention, or meeting failure event.
- 涉及区域：Project/task attempt state, meeting state, notification helper call sites.
- 输入：Project ID, task ID, attempt ID, execution state/reason, meeting ID, meeting failure sequence or failure reason.
- 输出：Stable notification IDs and persisted sent markers on task/meeting objects.
- 依赖：TODO-002.
- 完成标准：Repeated status polling, repair routines, and repeated saves do not resend the same notification; legitimate new attempts/failures can still notify.
- 关联 checklist：CHK-001, CHK-004, CHK-007, CHK-011.

## TODO-004 Send Project Execution acceptance notifications

- 目标：Notify when a task enters `awaiting_user_acceptance`.
- 涉及区域：`_project_execution_run_review()`, `_project_execution_run_attempt()`, Project Execution transition handling.
- 输入：Project, task, review result, attempt ID.
- 输出：Feishu application-form card with accept, rework, and open-VO actions.
- 依赖：TODO-002, TODO-003.
- 完成标准：Acceptance notification is sent once when review pass or skipped review waits for user acceptance, includes current attempt identity, and does not block the workflow if Feishu is missing or disabled.
- 关联 checklist：CHK-001, CHK-012, CHK-013, CHK-014.

## TODO-005 Add Feishu card actions for Project Execution acceptance

- 目标：Allow Feishu card buttons to accept or request rework for current Project Execution acceptance.
- 涉及区域：`_handle_feishu_card_action()`, card action dispatch helpers, `_handle_project_execution_acceptance()`.
- 输入：Feishu action payload containing project ID, task ID, attempt ID, and action type.
- 输出：Callbacks for `project_execution_accept` and `project_execution_rework`.
- 依赖：TODO-004.
- 完成标准：Accept calls existing acceptance flow; rework uses default feedback; stale or invalid actions return clear error toasts; meeting request actions remain unchanged.
- 关联 checklist：CHK-002, CHK-003, CHK-009, CHK-011, CHK-013.

## TODO-006 Send Project Execution blocked/intervention notifications

- 目标：Notify blocked states and user-intervention failures while avoiding transient retry noise.
- 涉及区域：Project Execution executor failure, reviewer blocked/too-many-reworks, workspace/role failures, cancel/user blocked paths, meeting blocker paths if applicable.
- 输入：Project, task, attempt, blocked reason, provider error, retry scheduling result.
- 输出：Feishu warning/error notification with sanitized reason and open-project/task action.
- 依赖：TODO-002, TODO-003.
- 完成标准：Blocked states notify once; transient failures that schedule retry do not notify immediately; missing config/permission/workspace/context and exhausted recovery paths notify clearly.
- 关联 checklist：CHK-004, CHK-005, CHK-006, CHK-010, CHK-012, CHK-013, CHK-014.

## TODO-007 Send AI meeting failure notifications

- 目标：Notify failed AI meetings that need user attention, without notifying normal completions or action item generation.
- 涉及区域：Executable meeting failure and moderator failure paths, meeting result flow, meeting open links.
- 输入：Meeting ID, topic, stage, moderator failure or failure reason, related project/task context if present.
- 输出：Feishu error notification with open-meeting action.
- 依赖：TODO-002, TODO-003.
- 完成标准：Moderator failure or equivalent user-attention meeting failure sends one error notification; normal completed meetings and action items send none.
- 关联 checklist：CHK-007, CHK-010, CHK-011, CHK-012, CHK-014.

## TODO-008 Extend tests for Feishu critical workflow notifications

- 目标：Cover new notification intents, dedupe, callbacks, missing config behavior, and regressions.
- 涉及区域：`tests/test_feishu_notifications.py`, Project Execution tests, meeting tests, possible new focused test file.
- 输入：Existing test helpers and fake Feishu sender/action payloads.
- 输出：Automated tests for acceptance notification/action, blocked notification, transient retry suppression, meeting failure notification, and backward compatibility.
- 依赖：TODO-004, TODO-005, TODO-006, TODO-007.
- 完成标准：Tests cover CHK-001 through CHK-013 at the unit/integration level where feasible and existing Feishu/meeting request tests still pass.
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012, CHK-013.

## TODO-009 Perform manual VO verification

- 目标：Verify user-facing open links and card behavior in the VO UI.
- 涉及区域：VO project/task UI, meeting UI, Feishu card links.
- 输入：Running VO instance with Feishu config or safe dry-run/test setup.
- 输出：Manual verification notes.
- 依赖：TODO-004, TODO-005, TODO-006, TODO-007.
- 完成标准：Acceptance, blocked task, and meeting failure notification links land in useful VO contexts; text is readable and not noisy.
- 关联 checklist：CHK-014.

## TODO-010 Update requirement artifacts after implementation and testing

- 目标：Keep archived requirement state accurate through implementation, test confirmation, and final closeout.
- 涉及区域：`.cosh-docs/requirment/feishu-critical-workflow-notifications/`.
- 输入：Implementation result, test result, user confirmations.
- 输出：Updated checklist test notes, status updates, and final archive move when user confirms done.
- 依赖：TODO-008, TODO-009.
- 完成标准：Checklist results are recorded; tested and done confirmations are captured before moving the requirement to archive.
- 关联 checklist：CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-011, CHK-012, CHK-013, CHK-014.
