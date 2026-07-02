# Feishu Meeting Request Actions Requirement

## Background

VO now has a common Feishu notification module with app credential delivery, interactive cards, long-connection card action callbacks, delivery records, and basic action logging. The next product step is to mirror existing meeting requests that require human approval into Feishu, so users can see the request earlier and use Feishu as a quick confirmation channel.

The website remains the primary and authoritative meeting request surface. This requirement must not change the existing VO meeting request creation, queue display, state machine, approval policy, or rejection policy. Feishu is only an additional notification and shortcut path for the requests that already require human handling.

The relevant product clarification is complete:

- Use the existing "needs human meeting approval" flow as the trigger scope, especially high-priority project cases that already require manual meeting approval.
- Feishu should act as a synchronized notification and quick action entry, not a separate meeting management product.
- The application form card should include Agree, Reject, and View Details.
- Agree/Reject should update the VO meeting request state and return a clear result such as approved or rejected.
- Success requires delivery, state update, and traceability of who decided what and when.

## Target Users

- Primary decision maker: the VO user who receives Feishu meeting request cards and must approve or reject meeting creation.
- Request source: AI/project execution flows that determine a meeting is needed but are not allowed to approve the meeting themselves.
- Operators/developers: people troubleshooting whether a meeting request was delivered, clicked, and processed correctly.

## Goals

- Reuse the common Feishu notification module for existing human-required meeting requests while preserving the current website behavior.
- Let users approve or reject eligible meeting requests directly from Feishu as a shortcut to the existing VO decision flow.
- Preserve a View Details path back into VO for context-heavy decisions.
- Keep existing VO meeting request behavior authoritative: Feishu actions must call the same business semantics as VO approval/rejection and must not create another approval path.
- Record enough information to know who clicked which action, when, for which request, and with what result.

## Product Decisions

- Trigger scope is not all meetings. It is the existing set of meeting requests that already require human approval.
- Feishu cards should not introduce a new approval policy. They are a notification mirror and shortcut entry into the current meeting request state machine.
- Card buttons are:
  - Agree: approve the meeting request.
  - Reject: reject the meeting request.
  - View Details: open or navigate toward the relevant VO meeting request/project/task context.
- Button feedback should communicate the actual business result. A generic "received" toast is not sufficient for this feature.
- If a request is already processed, expired, invalid, or otherwise no longer actionable, Feishu should return a clear failure or no-op message rather than overwriting state.
- Auditability is part of success: the system must record action actor, time, request ID, action, and result.

## Scope

### In Scope

- Connect `confirm_meeting_request` and `reject_meeting_request` Feishu card action values to the corresponding existing VO meeting request handlers.
- Ensure Feishu meeting request cards include Agree, Reject, and View Details where possible.
- Use existing meeting request business rules for valid and invalid state transitions; do not change the original website queue or approval logic.
- Return clear Feishu toast feedback for success and failure.
- Record Feishu action attempts and outcomes for traceability.
- Cover stale/already-processed request behavior.
- Add focused automated tests for the Feishu-to-meeting-request action path.

### Out Of Scope

- Creating a new meeting approval product separate from VO meeting requests.
- Changing the existing VO meeting request display, creation trigger, queue behavior, approval policy, or rejection policy.
- Expanding trigger scope to every meeting notification.
- Building complex multi-person approval or delegation.
- Custom Feishu card editing after approval/rejection, unless already naturally supported by the current card flow.
- New user notification preferences.
- Full UI redesign of the VO meeting request detail page.

## Success Criteria

- When an existing human-required meeting request is created, a Feishu application-form card is delivered through the common notification module.
- The Feishu card has Agree, Reject, and View Details actions.
- Clicking Agree in Feishu approves the VO meeting request and returns a success toast.
- Clicking Reject in Feishu rejects the VO meeting request and returns a success toast.
- Clicking a stale or invalid action returns a clear failure toast and does not corrupt meeting request state.
- The action log records actor, request ID, action, timestamp, and outcome.
- Existing VO-side approval/rejection APIs and tests continue to pass.
