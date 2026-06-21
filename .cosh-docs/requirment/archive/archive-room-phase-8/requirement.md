# Archive Room Phase 8 Requirement

## Background

Archive Room Phase 1-7 has established project archives, artifact browsing, archive manager lifecycle, event-triggered maintenance, AI context packages, and human confirmation governance.

Phase 7 intentionally used a conservative confirmation model for accuracy: long-lived rules, high-impact suggestions, and conflicts enter a human confirmation queue. During acceptance, this exposed two product gaps:

- Archive maintenance frequency is not configurable per project. Users can enable or disable long-term maintenance, but cannot choose how often scheduled整理 should run.
- The human queue can become too dependent on manual work. The desired direction is to let the archive manager resolve most ordinary archive changes and only escalate truly ambiguous or high-impact owner decisions.

Phase 8 addresses these gaps by combining maintenance scheduling controls with archive-manager-first governance.

## Product Goals

- Let users control how often long-term-maintained projects are scheduled for archive整理.
- Keep event-triggered整理 independent from scheduled整理.
- Make archive maintenance predictable by showing current frequency, next scheduled整理, last scheduled整理, last event-triggered整理, and skipped-run reasons.
- Reduce unnecessary human confirmation by allowing the archive manager to auto-resolve low-risk and non-human-confirmed archive knowledge changes.
- Keep the human confirmation queue small, high-value, and actionable.
- Preserve trust by showing source comparison summaries and archive manager judgment when automatic governance changes archive knowledge.

## Users

- Human project owner/operator who opens Archive Room to understand project memory and maintenance health.
- Archive manager AI that keeps project archives current and resolves routine governance.
- Execution AI agents that consume project context and should receive current, source-backed archive knowledge without waiting for excessive human confirmation.

## Scope

### Maintenance Frequency Controls

- Add per-project archive maintenance frequency configuration.
- Keep the existing long-term maintenance on/off setting.
- Add schedule modes:
  - Event-triggered only.
  - Event-triggered + daily inspection.
  - Event-triggered + weekly inspection.
  - Custom interval only if it can be made clear and maintainable in the product.
- Default frequency: event-triggered + daily inspection.
- Show frequency configuration in Archive Room project detail as current frequency plus an "adjust" control.
- Place frequency controls in the long-term maintenance / advanced settings area so they do not distract from archive reading.
- If long-term maintenance is disabled, keep the frequency configuration visible but disabled/greyed, so users know what will apply if maintenance is resumed.
- Show:
  - Current frequency.
  - Next scheduled整理 time.
  - Last scheduled整理 time.
  - Last event-triggered整理 time.
  - Last skipped scheduled整理 reason, when applicable.
- Maintenance history must distinguish manual, event-triggered, startup, daily, weekly, and custom scheduled整理.
- Paused archive manager or disabled project maintenance must skip scheduled整理 and record a clear reason.
- Avoid duplicate scheduled整理 when startup inspection, scheduled inspection, and event triggers happen close together.

### Archive-Manager-First Governance

- The archive manager should resolve ordinary archive knowledge changes before involving humans.
- Low-risk, source-backed整理 should be auto-confirmed by the archive manager.
- Conflicts should first be classified by the archive manager as:
  - Wording drift.
  - Stale old context.
  - Stronger new source.
  - True owner decision.
  - Mutually conflicting high-trust sources.
- For `archive_manager_confirmed`, `source_confirmed`, or `system_confirmed` content:
  - If a newer/stronger source supersedes old content, the archive manager may auto-confirm the new content and mark old content stale.
  - The old content must remain visible as stale rather than silently disappearing.
- For `human_confirmed` content:
  - The archive manager must not automatically replace it.
  - Replacement or contradiction of human-confirmed rules must enter human confirmation.
- Human confirmation should be reserved for:
  - Replacing or contradicting human-confirmed rules.
  - Mutually conflicting high-trust sources that cannot be resolved automatically.
  - High-impact owner/business decisions.
- Pending human items must include:
  - Archive manager judgment summary.
  - Why automation was insufficient.
  - What decision the human needs to make.
  - Source comparison when relevant.
- Automatic governance should produce a lightweight notice in the long-term maintenance area, not a new manual to-do.
- The notice should show the latest 3-5 automatic governance actions.
- Source comparison summary should include old source, new source, source type, time, and archive manager judgment.

## Non-Goals

- Phase 8 does not replace the Phase 7 human confirmation queue.
- Phase 8 does not allow automatic replacement of human-confirmed rules.
- Phase 8 does not require a full calendar scheduler UI.
- Phase 8 does not require every possible custom cron expression.
- Phase 8 does not make automatic governance invisible; actions must remain auditable.

## Success Criteria

- Users can configure each long-term-maintained project's archive整理 frequency from Archive Room.
- Scheduled整理 follows the project frequency while event-triggered整理 continues to work independently.
- Disabled maintenance or paused archive manager produces skipped-run records instead of silent failure.
- Archive manager automatically handles ordinary governance and reduces human pending items compared with Phase 7 behavior for the same event set.
- Users can understand automatic governance changes through lightweight notices, source comparisons, stale markers, and history.
- Human pending items are fewer, higher signal, and explain why human judgment is required.

## Product Clarification Decisions

- Phase8 balances scheduling controls and reducing manual confirmation.
- Human queue should contain only owner-level decisions.
- Archive manager may automatically handle non-human-confirmed content.
- Frequency controls are shown as current frequency plus an adjust action in the long-term maintenance area.
- Default schedule is event-triggered + daily inspection.
- Automatic handling uses lightweight notices in the long-term maintenance area.
- Notices show recent 3-5 actions and do not require manual clearing.
- Source strength should be shown as a comparison summary rather than a one-line reason or full evidence dump.
- Disabled long-term maintenance greys out frequency controls while preserving the configured value.
