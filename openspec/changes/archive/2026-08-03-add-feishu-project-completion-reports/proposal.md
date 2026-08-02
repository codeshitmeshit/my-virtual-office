## Why

Project owners currently need to return to Virtual Office to discover a successfully completed project's final outcome. An optional Feishu completion report lets the owner receive a concise, human-readable result through the existing notification bot as soon as the project completes.

## What Changes

- Add a per-project Feishu reporting choice that defaults to enabled and remains editable until the project completes.
- On each successful project completion or successful rerun, submit only the project's final artifacts for report generation and deliver the structured result to the project owner through the Feishu notification bot.
- Structure the owner-facing report around a content title, a standalone conclusion summary, core conclusions, and a horizontal divider followed by the reporting Agent's unlabeled organizational reflections.
- Track project execution status separately from report delivery status so delivery failure never reverses successful completion.
- Expose report-delivery failure, perform bounded automatic recovery, and allow the owner to request a manual resend.
- Preserve the existing VO failure notification path for unsuccessful projects; when the notification bot deterministically fails, fall back once to the configured owner conversation through the Feishu chat bot.
- Exclude execution logs, intermediate files, and internal-only information from report input and delivery.
- Exclude project lifecycle status, versions, exceptions, follow-up task lists, and artifact paths from the owner-facing report content.

## Capabilities

### New Capabilities

- `project-completion-reporting`: Per-project Feishu report preference, successful-completion triggering, final-artifact report generation, owner delivery, rerun versioning, delivery-state visibility, and retry/resend behavior.

### Modified Capabilities

None.

## Impact

- Project creation, editing, persistence, and project-page presentation gain a report preference and delivery status.
- Successful project-finalization and rerun flows gain an asynchronous, idempotent report-delivery side effect without changing completion semantics.
- Final-result artifact selection and the existing Feishu notification-bot path become inputs to the reporting flow.
- Existing unsuccessful-project VO notifications remain behaviorally unchanged.
- The change depends on the project orchestration contract that automatically completes a project and records task final-result artifacts.
