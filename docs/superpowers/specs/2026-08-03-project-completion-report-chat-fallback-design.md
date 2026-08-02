# Project Completion Report Chat Fallback Design

## Goal

When a project completion report cannot be sent by the Feishu notification app, deliver the same bounded report through the configured Feishu chat app so the project owner still receives it.

## Scope

- The behavior applies only to project completion reports.
- The notification app remains the primary channel.
- The chat app uses one explicitly configured owner chat ID.
- Existing retry limits, manual resend behavior, report generation, and sensitive-artifact controls remain unchanged.

## Delivery Rule

The existing completion-report delivery boundary performs one minimal fallback decision:

1. Send through the notification app.
2. If delivery succeeds, return that result.
3. If delivery returns a deterministic failure, send the same human-readable report through the chat app.
4. If the notification result is unknown (`network_error`, `timeout`, or equivalent), do not fall back because the notification may already have been delivered.

Deterministic failures include missing notification-app configuration and explicit Feishu authentication, permission, validation, or API error responses.

## State and User Visibility

- A successful result stores the actual delivery channel: `notification_app` or `chat_app_fallback`.
- The project report page displays the channel used for each delivered version.
- If both deterministic attempts fail, the existing completion-report failure and retry state machine handles the combined failure.
- Project completion state is never rolled back by delivery failure.

## Audit Logging

Each fallback decision writes bounded, redacted audit data containing:

- project ID and occurrence ID;
- primary channel status and error code;
- whether fallback was attempted or suppressed;
- fallback channel status and error code;
- final channel and message ID when delivered.

Logs must not contain App secrets, access tokens, webhook values, artifact contents, or full Agent prompts.

## Acceptance Simulation

Create a local completed demo project with a final Markdown artifact and reporting enabled. Because the local notification app is currently unconfigured, its deterministic failure must trigger the chat app. The configured owner P2P chat receives the generated report, the occurrence becomes delivered with channel `chat_app_fallback`, and the audit record shows the primary failure followed by fallback success.

## Tests

- Notification-app success does not call the chat app.
- Missing notification-app configuration calls the chat app once.
- Explicit notification-app failure calls the chat app once.
- Network or timeout uncertainty does not call the chat app.
- Chat fallback failure returns a redacted combined failure for the existing retry policy.
- Successful fallback persists and exposes `chat_app_fallback`.
- Audit records contain routing metadata but no secrets or report body.
