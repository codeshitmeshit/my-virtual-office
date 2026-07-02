# Feishu Notification Module Review

## Review Summary

The product direction is clear enough to proceed to checklist drafting. The request is intentionally scoped as a reusable internal VO notification module, not a full Feishu workflow platform. The main implementation risk is overbuilding the application-form workflow before callback handling exists. The first phase should therefore define stable notification semantics, card structure, action categories, state expression, and delivery records while leaving full click-result business processing for a later integration.

## Product Review

### Clear Decisions

- Target consumer is VO internal modules.
- Four notification categories are required: application form, notification, warning, and error.
- Application form is independent from normal notification and can carry decision-like buttons.
- Buttons must be extensible by business scenario but constrained by common action categories.
- First phase sends cards, expresses state, provides generic interaction feedback, and records delivery.
- Error notifications default to both user and administrator visibility.
- Normal notification, warning, and error may include navigation buttons but should not carry approval decisions.

### Remaining Product Risks

- Error notifications sent to both users and administrators can create noise or expose internal details.
  - Mitigation: support user-facing and admin-facing variants for error messages.
- Extensible application-form buttons can degrade consistency if every business module invents unrelated meanings.
  - Mitigation: require every button to declare a common action category.
- Application form as an independent type may later overlap with a task or approval center.
  - Mitigation: first phase records related business object and state, but does not attempt to become a full approval system.

No blocking product ambiguity remains.

## Technical Review

### Architecture And Boundaries

- The module should own notification semantics, Feishu card rendering, webhook delivery, and send records.
- Business modules should provide intent-level inputs rather than raw Feishu JSON whenever possible.
- A lower-level escape hatch may be useful later, but first-phase usage should prefer typed notification categories and action categories.
- Webhook delivery should be isolated behind a sender boundary so tests can run without calling Feishu.

### Interface And Data

The module needs stable concepts, regardless of implementation language:

- Notification type: application_form, notification, warning, error.
- Severity or template mapping for display.
- Title, summary, details, related business object, and optional link.
- Audience intent for errors: user-facing, admin-facing, or both.
- Application-form state: pending, submitted, processing, approved, rejected, expired, cancelled, no_longer_actionable.
- Action category: confirm, cancel, jump, request_more_info, or a constrained extension.
- Send record fields for troubleshooting and business traceability.

### State Flow

- Send-time flow:
  1. Business module creates notification intent.
  2. Notification module validates category and action constraints.
  3. Notification module renders Feishu card payload.
  4. Sender posts to webhook.
  5. Send record captures success or failure.
- Application-form click flow:
  - First phase may render buttons and generic feedback semantics.
  - Full click callback processing is explicitly later work.
  - The module should avoid promising final business state unless a business module provides that state.

### Error Handling

- Webhook call failures must not crash unrelated VO workflows unless the caller explicitly treats notification failure as fatal.
- Failure reasons should be recorded in a sanitized form.
- Feishu response success and non-success responses should be distinguishable.
- User-facing error content must avoid stack traces, raw webhook URLs, tokens, or internal payloads.

### Security

- The webhook URL is a secret.
- The current conversation exposed a concrete webhook URL; implementation should not commit it to source.
- Configuration should be environment-based or otherwise secret-managed.
- Logs and records must redact webhook tokens and sensitive request bodies.
- Card content should avoid placing sensitive internal details in Feishu groups unless intended.

### Compatibility And Migration

- Existing VO features may currently have ad hoc notification behavior. First phase should introduce the module without forcing every existing feature to migrate at once.
- The module should be easy to call from meeting application flows first.
- If existing tests rely on no external network, sender tests should use a fake sender.

### Observability

- Basic records are required for send status and business traceability.
- Records should be queryable or inspectable enough to answer:
  - Was a notification attempted?
  - Which business object did it relate to?
  - Did Feishu accept it?
  - If not, what sanitized reason was captured?

### Testability

- Card rendering can be unit-tested with snapshot-like or structural assertions.
- Validation rules can be unit-tested without network.
- Sender behavior can be tested with a fake HTTP client or fake sender.
- Manual Feishu verification should use a disposable/test webhook or clearly marked test card.

## Review Conclusion

No blocking product or technical issue prevents moving to checklist. The checklist should especially guard against scope creep into full callback workflow, webhook secret leakage, inconsistent action semantics, and missing delivery records.
