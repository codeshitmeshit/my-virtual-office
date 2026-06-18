# Meeting for AI Phase 4 Review

## Review Conclusion

Conclusion: approved for checklist draft.

The product boundary is clear enough after clarification. Phase 4 should be implemented as a request and confirmation layer on top of the existing executable meeting flow. It must not bypass the user-started meeting safety model from Phase 1-3.

## Product Review

### Clear Decisions

- The first request trigger is a project task AI encountering a clear collaboration blocker.
- Ordinary chat-originated requests are explicitly out of scope.
- Later request sources should be possible, so the product language should avoid hard-coding "project task" as the only permanent source.
- User review is editable, not accept/reject only.
- Context candidates come from the same project boundary and are unselected by default.
- Rejected requests must feed back to the source task context.

### Product Risks

1. Meeting request spam.
   - Mitigation: require meeting goal, expected outcome, and why the AI cannot continue alone.
2. Context overload.
   - Mitigation: keep context as candidates, default unselected, grouped by source.
3. Unauthorized context leakage.
   - Mitigation: only selected context enters the final snapshot; unselected candidates stay out of prompts, transcript, and result.
4. User review friction.
   - Mitigation: keep review editable in one flow, not a multi-step wizard for the first implementation.
5. Future trigger expansion.
   - Mitigation: model request source conceptually as a source type, while only enabling project-task source in Phase 4.

No blocking product ambiguity remains.

## Technical Review

### Existing Foundation

Phase 1-3 already provides:

- Durable executable meeting entities and events.
- User-started meeting creation.
- Context modes and prompt building.
- Live meeting detail and history UI.
- User intervention and meeting control.
- Occupancy protection for active executable meetings.

Phase 4 can build on these capabilities by adding a pre-confirmation request state and a conversion path to an executable meeting.

### Required Technical Boundaries

- A meeting request must not be the same as an active executable meeting.
- Pending requests must not reserve occupancy.
- Pending requests must not call providers.
- Context candidates and confirmed context snapshot must be distinct.
- Rejection and confirmation should be durable and idempotent.
- User edits should preserve at least lightweight traceability from original request to final meeting.

### Suggested State Flow

```text
requested
  -> rejected
  -> confirmed
      -> executable meeting create/start flow
```

The confirmed state should record the created meeting ID. If meeting creation fails after confirmation, the request should stay recoverable rather than disappear.

### Data Considerations

Request records should contain:

- Request ID.
- Source type, initially `project_task`.
- Source project ID and task ID.
- Requesting Agent ID.
- Original proposal:
  - Topic.
  - Purpose.
  - Meeting type.
  - Goal.
  - Expected outcome.
  - Reason the AI cannot continue alone.
  - Suggested participants.
  - Suggested moderator.
- Context candidates:
  - Candidate ID.
  - Source kind.
  - Title.
  - Summary or excerpt.
  - Source reference.
  - Default selected false.
- User review:
  - Final configuration.
  - Selected context IDs.
  - Supplemental context.
  - Edit summary.
  - Decision and decision reason.
- Conversion:
  - Created meeting ID.
  - Confirmation timestamp or equivalent event.

### Security and Privacy

- Candidate generation must respect same-project scope for this Phase.
- Unselected candidates must never enter provider inputs.
- Rejected request text should be safe to show in the source task context.
- No provider credentials or raw hidden context should be persisted in user-visible request fields.

### Compatibility

- Existing user-started meetings must continue working.
- Existing meeting history and active meeting projections should not treat pending requests as active meetings.
- Old data without request records should continue to load normally.
- The Meetings dashboard currently separates Active and History; Phase 4 should add a separate AI Requests queue rather than overloading either tab.
- The Projects UI already has a task detail panel; Phase 4 should use that as the source-context view for task-originated requests.
- The right control panel Meetings widget should remain lightweight and should show only a pending request count or confirmation-needed prompt, not full review controls. The prompt should open the Meetings dashboard AI Requests queue.

### Testing Feasibility

The feature is testable without real provider calls:

- Create valid and invalid AI meeting requests.
- Verify pending requests do not appear as active meetings and do not reserve participants.
- Verify context candidates default unselected.
- Confirm with selected context and inspect created meeting prompt/context payload.
- Reject with reason and inspect source task-visible request state.
- Regression-test existing user-started executable meeting creation.

Testing should be staged:

1. Build and validate request APIs, request lifecycle, context candidates, conversion, rejection, and frontend UI with deterministic or equivalent fixtures.
2. Stop before the true AI-originated request gate and notify the user.
3. Continue real AI validation only after the user confirms the required skill has been installed for the requesting AI.

## Blocking Issues

None.

## Non-Blocking Decisions for Implementation

- Whether request persistence lives in the existing meeting store or a parallel request store.
- Exact wording for the source task feedback shown to the AI/user.
- Exact shape of same-project related-task ranking.

These can be resolved during implementation without changing the product contract.
