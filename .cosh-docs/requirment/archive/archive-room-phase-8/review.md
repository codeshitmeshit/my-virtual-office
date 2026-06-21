# Archive Room Phase 8 Review

## Review Conclusion

No blocking product issue remains after clarification. Phase 8 is ready for checklist confirmation.

The implementation should be scoped carefully because it touches archive scheduling, project archive state, archive manager governance rules, Archive Room UI, and AI context trust behavior. The main risk is not technical feasibility but product trust: automatic governance must reduce human work without making archive changes feel opaque.

## Product Fit

The requirement fits the Archive Room roadmap:

- Phase 5 introduced event-triggered and scheduled整理.
- Phase 6 made archive data useful to AI.
- Phase 7 made confirmation governance visible and controllable.
- Phase 8 now makes maintenance configurable and shifts routine governance from humans to the archive manager.

This is a natural next step because a high-volume project archive will otherwise create too many manual confirmation tasks.

## Key Product Risks

### Risk 1: Automatic governance could feel untrustworthy

If the archive manager silently replaces old content, users may not trust the archive.

Mitigation:

- Keep old content as stale.
- Show source comparison summaries.
- Show recent automatic governance actions in the long-term maintenance area.
- Preserve governance history.

### Risk 2: Frequency controls could confuse users

Users may think setting a schedule disables event-triggered整理.

Mitigation:

- Wording should consistently describe the schedule as inspection frequency.
- UI should show event-triggered整理 separately from scheduled整理.
- Last event-triggered整理 and last scheduled整理 should be separate fields.

### Risk 3: Human queue may still be noisy

If the archive manager classification remains too conservative, Phase 8 may not reduce human work.

Mitigation:

- Acceptance must compare the same event set under Phase 7-style behavior versus Phase 8 behavior.
- Low-risk source-backed content and non-human-confirmed conflicts should be auto-handled.

### Risk 4: Auto-resolving source/system facts is subtle

`source_confirmed` and `system_confirmed` can be objective but still become stale, such as project state or task status changing over time.

Mitigation:

- Treat them as objective at the time of source, not permanently immutable.
- Let archive manager mark stale when newer stronger sources exist.
- Keep source timestamps visible.

## Technical Considerations

These are not product questions, but implementation should account for them:

- Project archive records need a durable maintenance schedule state.
- Maintenance records need trigger type and skipped reason.
- Scheduled整理 needs deduplication/cooldown to avoid repeated runs after startup or close event bursts.
- Archive governance entries need stale relationships and source comparison metadata.
- Archive Room UI should preserve existing scroll behavior when frequency controls or notices update.
- Context packages should not treat stale/replaced content as active guidance.

## Suggested Scope Boundaries

Must-have:

- Frequency mode: event-only, daily, weekly.
- Default: event-triggered + daily.
- Project detail UI for current frequency and adjust action.
- Next/last scheduled and last event-triggered timestamps.
- Skipped-run records.
- Archive-manager-first auto handling for non-human-confirmed content.
- Source comparison summaries and stale markers.
- Recent 3-5 automatic governance notices.
- Phase7/Phase8 same-event comparison test.

Should-have:

- Custom interval if simple enough.
- Inline explanation of why event-triggered整理 remains active.

Not required for this phase:

- Full cron editor.
- Rich notification center.
- Automatic replacement of human-confirmed content.
- Cross-project schedule templates.

## Checklist Readiness

The checklist should cover:

- Schedule configuration UI and persistence.
- Scheduled整理 execution.
- Event-triggered整理 independence.
- Paused/disabled skip records.
- Deduplication/cooldown.
- Automatic governance of low-risk and non-human-confirmed content.
- Human escalation boundaries.
- Source comparison and stale display.
- AI context exclusion of stale/rejected content.
- Regression for Phase 1-7 archive behavior.
