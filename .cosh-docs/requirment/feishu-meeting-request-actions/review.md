# Feishu Meeting Request Actions Review

## Review Summary

The product scope is clear enough to proceed. The feature should reuse the common Feishu notification card infrastructure and mirror only existing human-required meeting requests into Feishu. The original VO website meeting request queue and state machine remain authoritative. The main technical risk is bypassing, duplicating, or subtly changing the VO meeting request state machine from the Feishu callback path. The implementation should therefore route Feishu actions into the same confirmation/rejection handlers or equivalent shared domain logic.

## Product Review

### Clear Decisions

- Scope is existing meeting requests that need human approval, not all meeting events.
- Feishu is a synchronized notification and shortcut decision surface.
- Agree/Reject are direct decision actions.
- View Details remains available for context.
- Success includes state update and decision traceability.

### Product Risks

- Users may click a stale card after the request has already been handled.
  - Mitigation: return a clear failure/no-op toast and preserve the current state.
- Reject normally benefits from a reason, but Feishu card button may not provide one.
  - Mitigation: use a default Feishu-origin reason for direct button rejection, while keeping VO detail view for richer rejection.
- Feishu approval could feel final without enough context.
  - Mitigation: include enough summary fields on the card and provide View Details.
- The implementation could accidentally change website meeting request behavior.
  - Mitigation: treat the website as the source of truth and add regression checks for the existing meeting request flow.

No blocking product ambiguity remains.

## Technical Review

### Existing Surfaces

- Feishu notification card generation and sending exist in `app/feishu_notifications.py`.
- Feishu long-connection card action handling exists through `_handle_feishu_card_action`.
- Meeting request creation and business state handling exists in `app/server.py`.
- Existing meeting request notification actions already include values:
  - `confirm_meeting_request`
  - `reject_meeting_request`
  - `request_id`

### Architecture Recommendation

- Keep Feishu card action parsing generic.
- Add a narrow dispatcher for known action values.
- Route `confirm_meeting_request` to the existing meeting request confirm behavior.
- Route `reject_meeting_request` to the existing meeting request reject behavior.
- Preserve generic action logging for all card actions, but enrich known meeting actions with business outcome.
- Do not alter the original meeting request trigger, queue rendering, or website approval/rejection behavior.

### State Flow

1. A human-required meeting request is created.
2. The existing notification path sends an application-form card.
3. User clicks Agree or Reject in Feishu.
4. Long connection receives `card.action.trigger`.
5. `_handle_feishu_card_action` extracts action value and user identity.
6. Known meeting action dispatcher calls meeting request confirm/reject logic.
7. Handler returns a Feishu toast with approved/rejected or failure message.
8. Action log records the click and business result.

### Data And Traceability

Minimum data to preserve:

- Feishu action record ID.
- `request_id`.
- Action: confirm or reject.
- Feishu user identifiers when present.
- Message ID/chat ID when present.
- Business result: approved/rejected/already handled/not found/error.
- Timestamp.

### Compatibility

- Existing VO UI/API approval and rejection should remain unchanged.
- Existing website display of human-required meeting requests should remain unchanged.
- Existing notification send behavior should remain compatible.
- Direct Feishu rejection should choose a deterministic default reason if no reason is supplied.
- Existing long-connection callback tests should remain valid.

### Security And Permissions

- This feature assumes the Feishu card is only delivered to the configured recipient/channel.
- First phase does not introduce per-user authorization mapping between Feishu user and VO account.
- The action log should not include app secret or Feishu credentials.

### Testability

- The dispatcher can be tested by directly invoking `_handle_feishu_card_action` with synthetic Feishu events.
- Meeting request tests can create pending requests, then simulate Feishu confirm/reject.
- Stale state tests can click after already confirmed/rejected.
- No real Feishu network calls are required for automated tests.

## Review Conclusion

No blocking product or technical issue prevents moving to checklist. The checklist should focus on preserving existing meeting request semantics, Feishu button outcomes, stale-action safety, traceability, and regression coverage.
