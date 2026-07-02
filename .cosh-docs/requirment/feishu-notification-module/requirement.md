# Feishu Notification Module Requirement

## Background

VO needs a reusable notification module based on a Feishu custom bot webhook. The module should let internal VO features send clear, consistent Feishu messages without each feature rebuilding card formatting, severity styles, request forms, delivery recording, or basic action semantics.

The initial webhook has been verified to send interactive card messages successfully. The module must treat the webhook URL as a sensitive credential and avoid exposing it in logs, client code, repository files, or user-facing output.

## Target Users

- Primary user: VO internal modules, including meeting, task, and agent collaboration features.
- Message recipient: VO users and administrators who receive Feishu group notifications.
- First business example: meeting application or similar approval/request flows.

## Goals

- Provide one common module for VO features to send Feishu notifications.
- Support four notification categories:
  - Application form: an actionable card with configurable buttons and request state.
  - Notification: normal information delivery.
  - Warning: important but recoverable or attention-needed events.
  - Error: failure events that may need user and/or administrator attention.
- Make notifications visually and semantically consistent while allowing business-specific content.
- Allow application-form buttons to be extensible across business scenarios.
- Keep first-phase scope focused on reliable delivery, clear presentation, basic feedback semantics, and basic notification records.

## Product Decisions

- The module serves VO internal modules first, not external integrations.
- Application form is an independent notification type, parallel to notification, warning, and error.
- First phase sends all four message categories and expresses application form states such as pending, processed, cancelled, expired, and no longer actionable.
- First phase does not need to complete every business workflow after a button click, but button interaction should at least provide generic feedback such as submitted, processing, or failed.
- Visual standardization is semi-strict:
  - Category color, title hierarchy, core fields, and severity expression are unified.
  - Business modules may add scenario-specific fields and card sections.
- Application-form actions are extensible:
  - Business modules may define button text and meaning.
  - Each button must map to a common action category such as confirm, cancel, jump, or request_more_info.
- Application forms default to single final decision, but a business scenario can declare multi-participant handling.
- Application forms must support invalid states such as expired, cancelled, and no longer actionable.
- Error notifications are sent to both user and administrator by default to avoid missed failures, but product copy should distinguish user-understandable errors from internal system errors.
- Notification records in the first phase serve both troubleshooting and business traceability.
- Normal notification, warning, and error cards may include view-detail or open-related-page buttons, but they must not carry approval or decision actions.

## Scope

### In Scope

- Common notification abstraction for four categories.
- Feishu interactive card payload generation for all categories.
- Application-form card structure with extensible buttons and common action categories.
- Application-form state expression:
  - pending
  - submitted or processing feedback
  - approved or rejected where business state is provided
  - expired
  - cancelled
  - no longer actionable
- Semi-unified visual and content rules:
  - type-specific color/template
  - title
  - summary
  - severity
  - related business object
  - optional detail fields
  - optional jump buttons for non-application notifications
- Error audience handling that can produce user-facing and admin-facing message variants.
- Basic send record:
  - notification type
  - title
  - related business object identifier
  - target channel or recipient description
  - send time
  - success/failure status
  - failure reason when available
- Clear handling of webhook delivery failure.
- Tests or verification coverage for payload generation, category behavior, action semantics, record creation, and send failure handling.

### Out of Scope For First Phase

- Full business workflow completion for button clicks.
- Full audit trail of every click, processor identity, and final business result.
- User-configurable notification preferences.
- External system-facing notification API as a product surface.
- Reading Feishu group messages or user messages.
- Managing Feishu group membership or Feishu app permissions.
- Exposing webhook configuration in frontend UI.

## Non-Goals

- Do not build a general Feishu integration platform.
- Do not let arbitrary business code create inconsistent decision actions on non-application notifications.
- Do not store the webhook token in committed source files.
- Do not show raw internal stack traces or sensitive payloads to normal users.

## Constraints

- The current webhook is a Feishu custom bot webhook and supports sending interactive card messages.
- The webhook can send messages but cannot by itself receive button-click callbacks.
- Handling button-click results requires a later callback-capable Feishu app or backend callback integration.
- The module must be designed so later callback handling can be added without rewriting notification type semantics.
- The first phase should preserve clear separation between send-time notification behavior and later business workflow handling.

## Success Criteria

- VO modules can call one common module instead of handcrafting Feishu card payloads.
- Four notification categories render with consistent, readable card structure.
- Application forms can include business-defined buttons while preserving common action categories.
- Non-application notifications can include view-detail navigation without becoming decision workflows.
- Failed delivery is recorded and diagnosable.
- Basic records allow a developer or operator to confirm whether a business object was notified.
- Webhook secrets are not leaked through source, logs, frontend, or generated documentation.
