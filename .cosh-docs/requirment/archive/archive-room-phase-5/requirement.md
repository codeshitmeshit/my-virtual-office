# Archive Room Phase 5 Requirement

## Background

Archive Room Phase 1-3 established durable archive records, the main Archive Room UI, project archive detail, artifact browsing, and media preview. Phase 4 added the global OpenClaw archive manager lifecycle, profile synchronization, status visibility, pause/resume controls, current-project manual maintenance, and role boundaries.

Phase 5 turns Archive Room from a mostly manually refreshed archive into an automatically maintained project memory. It should keep active and maintained project archives current through important event triggers plus startup/daily gap-filling inspections, while avoiding noisy low-value archive churn.

## Product Goal

Keep project archives fresh without requiring humans to manually maintain them.

The goal has two product audiences:

- Human-facing completeness: people opening Archive Room should see important project activity, risks, decisions, artifacts, and maintenance freshness.
- AI handoff readiness: new AI agents should be able to understand a maintained project quickly from the archive/onboarding context later used by Phase 6.

## Primary Users

- Human project owner or operator.
- New AI agents joining an existing project.
- Active execution AI agents whose work produces archive-worthy events.
- The global archive manager AI that classifies and整理 archive updates.

## Scope

### Project Maintenance Eligibility

Projects gain a user-visible archive maintenance attribute:

- The product meaning is whether the project should receive ongoing automatic archive maintenance.
- Default follows project status:
  - active / ongoing projects default to maintained.
  - completed, paused, archived, or inactive projects default to not maintained.
- The attribute should be visible and manageable in both:
  - project detail / project settings context;
  - Archive Room project detail context.
- When maintenance is off, UI should show a lightweight explanation: startup/daily inspections and low-value events are skipped, but high-value events can still be archived.

### Event-Triggered整理

Phase 5 supports event-triggered整理 for both primary project execution events and collaboration events.

Primary project execution events:

- Task completion.
- Task failure.
- Project status change.
- Important artifact creation or update.
- Blocker creation or resolution.

Collaboration events:

- Meeting conclusion.
- Conflict reminder.
- AI stage summary.
- User-marked important message.

High-value events still trigger整理 even if a project is not marked for long-term maintenance:

- Task completion or failure.
- Project status change.
- Important artifact.
- Blocker.
- Conflict reminder.
- Meeting conclusion.

Low-value events and routine inspection are skipped when project maintenance is off.

### Scheduled Inspection

Phase 5 adds scheduled gap-filling inspections:

- Run once after VO startup.
- Run once daily.
- Inspections are补漏, not a full noisy rewrite of every archive.
- Inspections only process projects marked for long-term maintenance.
- If an inspection finds no update, it should update the latest inspection time but should not create a full maintenance record.
- If archive manager is paused, inspection should be skipped and record a concise skip reason.

### Important Chat Handling

Phase 5 adds important chat intake:

- User-marked important messages enter a pending整理 queue.
- The archive manager summarizes them into stable archive entries before they become normal archive content.
- Archive AI may classify unmarked chat as important when it contains decisions, risks, blockers, project-state changes, or artifact context.
- Classification should include a reason so humans and later AI can understand why it was treated as important.

### Archive Output And Confirmation

Automatic整理 should produce high-signal archive changes:

- High-confidence source-backed facts can enter the archive directly.
- Low-confidence, conflicting, or high-impact inferred content enters pending confirmation.
- Pending confirmation is required when a suggestion affects project status, task conclusions, or risk judgment.
- Ordinary summaries that do not change important state can be recorded silently.

### Maintenance Records And User Visibility

User-facing behavior:

- Important整理 results and pending confirmation entry points should be visible.
- Ordinary整理 should be quiet and visible through recent maintenance records.
- Failed整理 should be recorded in logs/activity but should not actively interrupt users in Phase 5.
- No-update inspections update latest inspection time without adding noisy records.

## Non-Goals

- Phase 5 does not implement the full Phase 6 AI onboarding/context query API.
- Phase 5 does not implement Phase 7 human confirmation queue polish, batch resolution, or governance UI.
- Phase 5 does not make every chat message a first-class archive item.
- Phase 5 does not replace raw task, meeting, chat, or artifact history.
- Phase 5 does not delete or hide the archive manager when maintenance is off.
- Phase 5 does not add aggressive user interruption for archive failures; failures are logged only in this phase.

## Success Criteria

- Important project activity updates archive content automatically.
- Startup and daily inspections fill gaps for maintained projects.
- Maintenance-off projects skip routine noise while still preserving high-value events.
- Low-value activity does not flood archive entries or pending confirmations.
- User-marked important messages are整理 into archive entries instead of being dumped raw.
- Archive maintenance activity is observable enough for users to understand what changed and when.

