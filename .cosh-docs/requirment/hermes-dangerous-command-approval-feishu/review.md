# Review

## Product Review

The product intent is clear: align VO with Hermes dangerous-command approval semantics and allow the same approval to be handled from either VO chat or Feishu. The requirement avoids broader OS/root privilege escalation, which keeps the product boundary safe and understandable.

No blocking product ambiguity remains.

## Technical Review

### Architecture

The preferred architecture is to extend the existing Hermes approval path instead of introducing a new approval subsystem.

- Keep `HERMES_APPROVAL_PENDING` as the pending approval registry.
- Keep `_handle_hermes_approval_respond()` as the single response path.
- Add Feishu card action handling that calls `_handle_hermes_approval_respond()` with the same payload shape as VO chat.
- Render VO chat approval buttons from `approval.choices`.
- Generate Feishu approval card buttons from the same `approval.choices`.

This avoids split-brain state between VO and Feishu.

### Interfaces

Backend approval choices should normalize to:

```text
once | session | always | deny
```

Compatibility aliases should include:

```text
approve_once -> once
approve -> once
allow_once -> once
approve_session -> session
allow_session -> session
approve_always -> always
allow_always -> always
cancel -> deny
no -> deny
denied -> deny
```

Native API response should call Hermes with the normalized value:

```text
client.respond_approval(run_id, choice)
```

Feishu card action payload should include:

```json
{
  "action": "hermes_approval_respond",
  "approval_id": "...",
  "agentId": "hermes-default",
  "session_id": "...",
  "choice": "once"
}
```

### Data And State

Approval state should remain keyed by `approval_id` and the existing agent/profile/session key helpers. A handled approval must be removed from pending state. Feishu notifications should be deduped with `approval_id` to avoid repeated cards on repeated progress events or polling.

History entries should record the normalized choice and a human-readable result:

- approved once
- approved for session
- approved always
- denied
- already handled or expired, when a duplicate action arrives

### Permissions And Safety

This feature does not grant root or OS privileges. It only forwards the user's dangerous-command decision to Hermes. If Hermes hardline-blocks a command or offers only `deny`, VO and Feishu must not add allow options.

The `always` action has higher safety impact. It should use danger styling and clear wording that Hermes may remember the authorization according to its own policy.

### Compatibility

Existing approve-once flows must continue to work through aliases. Existing tests that expect `approve_once` can be migrated gradually or kept through normalization.

CLI fallback should not pretend to support `session` and `always` unless Hermes CLI provides an explicit stable mechanism. The initial behavior should expose only `once` and `deny` for fallback approvals.

### Feishu Integration

The project already has Feishu notification configuration, interactive cards, and callback handling. The implementation should reuse these utilities rather than adding a separate Feishu sender. The first version should make the Feishu notification actionable immediately, since the user explicitly requested approval and notification to be combined.

### Observability

Approval lifecycle should be visible in:

- VO chat history.
- Gateway presence event `approval.responded`.
- Feishu notification records or callback logs.
- Test fixtures for native API and Feishu callback paths.

### Risks

- Feishu action callbacks may arrive after VO has already handled the approval. Mitigation: idempotent handling by `approval_id`.
- Hermes native API may not support all choice values in older versions. Mitigation: respect Hermes-provided `choices`, and surface Hermes error if a choice is rejected.
- CLI fallback may not support session/always. Mitigation: expose only supported fallback choices.
- Duplicate approval cards may be sent if progress events replay. Mitigation: notification dedupe by `approval_id`.

## Review Conclusion

No blocking issue found. Proceed to checklist draft. Implementation should start only after checklist confirmation.
