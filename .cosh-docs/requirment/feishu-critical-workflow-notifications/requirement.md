# Feishu Critical Workflow Notifications

## Background

Virtual Office already has a Feishu notification module with app-based card delivery, webhook fallback, long-connection card action callbacks, and notification send records. It is currently used mainly by AI meeting request notifications and manual test cards.

The next product need is to extend Feishu notifications to three high-value workflow events where the user should not have to keep watching VO:

- Project Execution user acceptance.
- Project Execution blocked or failed states that need user intervention.
- AI meeting failures.

## Target Users

- The VO user who owns the existing Feishu notification configuration.
- Small-team operators using the configured Feishu receiver as a shared notification channel.

This version does not introduce project owner, task owner, or per-event recipient routing. All notifications use the already configured Feishu receiver.

## Product Goals

- Reduce workflow stalls by notifying the user when VO is waiting for a human decision.
- Improve visibility for critical failures without turning Feishu into a stream of ordinary logs.
- Let the user complete common Project Execution acceptance decisions directly from Feishu where product scope allows.

## Scope

### Project Execution User Acceptance

When a Project Execution task reaches `awaiting_user_acceptance`, send a Feishu application card.

The card should allow:

- Accepting the task.
- Requesting rework with a default feedback message.
- Opening the related project or task in VO.

The first version should not require the user to type a custom reason in Feishu.

### Project Execution Blocked / Failed Requiring User Intervention

Send a Feishu notification when Project Execution reaches a blocked state that requires user intervention.

Product rule:

- `blocked` always notifies.
- `failed` notifies only when automatic recovery is not available or has already failed, or the problem requires the user to provide configuration, permission, workspace access, context, or manual decision.

Ordinary transient failures that are scheduled for automatic retry should not notify immediately.

### AI Meeting Failure

Send a Feishu error notification for failed AI meetings.

The card should:

- Summarize the meeting and failure reason.
- Provide an open-meeting action.

Normal meeting completion and normal action item generation should not notify in this version.

## Non-Goals

- No per-project, per-task, per-agent, or per-user Feishu routing.
- No repeated reminders, timeout nudges, or escalation policy.
- No normal progress notifications.
- No normal meeting completion notifications.
- No Feishu notification for ordinary chat messages, agent activity logs, or every SSE status event.
- No custom feedback input from Feishu in the first version.

## Constraints

- Use the existing Feishu notification configuration and receiver.
- Use the existing Feishu card model and send records where possible.
- Avoid duplicate notifications for the same workflow event.
- Feishu button actions must be idempotent or safely reject stale actions.
- Notification content must avoid leaking secrets, raw credentials, or overly long diagnostic text.

## Success Criteria

- User decisions spend less time waiting in VO because acceptance cards are visible in Feishu.
- Required user interventions are less likely to be missed.
- Feishu notifications remain high signal and do not include ordinary workflow noise.

## Product Decisions From Clarification

- Notification receiver: existing configured Feishu receiver.
- Acceptance card actions: accept and request rework with default feedback.
- Blocked/failed boundary: blocked always notifies; failed only when user intervention is needed.
- Reminder policy: send once; no repeated reminder or escalation in this version.
- Meeting notification: notify failed meetings only; action items are normal and should not notify.
