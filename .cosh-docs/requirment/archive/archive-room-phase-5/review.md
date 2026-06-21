# Archive Room Phase 5 Review

## Product Review

The clarified Phase 5 requirement is coherent and ready for checklist confirmation.

Strengths:

- It keeps the original Archive Room promise: high-signal project memory for humans and future AI handoff.
- It adds a clear scope-control lever through the project maintenance attribute.
- It avoids a common archive-product failure mode: converting every event into noisy history.
- It distinguishes high-value events from low-value/routine events.
- It defines user-marked important messages as pending整理, not raw permanent facts.
- It keeps failure behavior intentionally quiet in Phase 5, leaving stronger governance to Phase 7.

Product risks:

- The maintenance attribute may confuse users if it reads like a hard off switch while high-value events still archive.
- High-value event classification must be consistent enough that users can predict why something was archived.
- Pending confirmation can still grow if too many inferred entries affect state, task conclusions, or risk judgment.
- Startup/daily inspections can create user distrust if they silently do nothing without showing freshness.
- Important-chat classification can feel opaque without recorded reasons.

Product mitigations:

- Use UI copy that explains maintenance off means routine maintenance is skipped, not that all archiving stops.
- Keep the high-value event list explicit.
- Record classification reason and trigger source for automatic整理.
- For no-update inspections, update latest inspection time instead of creating noisy records.
- Keep Phase 5 pending confirmation limited to state/task/risk-impacting changes.

## Technical Review

Existing foundations are sufficient for Phase 5 planning:

- Archive records and project archive derivation exist under `STATUS_DIR/archive-room`.
- Archive manager state, recent activity, pause/resume, manual current-project maintenance, and profile sync already exist.
- Project/task mutations already update `completedAt`, project status, artifact association, blockers/risks, and task metadata in the project store.
- Executable meeting lifecycle already records completion transitions and result events.
- Project scheduled tasks already provide cron-like daily/periodic execution patterns that Phase 5 can reuse conceptually.
- Archive Room UI already displays manager status, project detail, and recent activity.

Technical risks:

- Trigger hooks may be scattered across project mutation, execution, meeting, artifact, and chat paths.
- Some event sources may not have reliable project IDs; those must produce skipped records or source references rather than corrupt archives.
- Daily/startup inspection needs idempotency so repeated startup or tests do not create duplicate archive entries.
- Important-chat classification depends on archive manager availability and should degrade gracefully.
- Paused archive manager must consistently skip automatic triggers while still allowing existing archive browsing.

Technical recommendations:

- Introduce a single internal archive maintenance trigger function that accepts a structured event type, project ID, source reference, value level, and reason.
- Keep trigger outcomes idempotent by event key/source reference.
- Store project maintenance eligibility directly with project/archive metadata and derive defaults from project status when unset.
- Keep scheduled inspection state separate from full maintenance records: last startup inspection, last daily inspection, and last no-update timestamp.
- For Phase 5, automatic整理 can start as deterministic archive derivation plus structured maintenance records; deeper AI summarization can be isolated behind the archive manager output contract from Phase 4.
- Add focused tests for trigger routing, maintenance eligibility, idempotency, pause behavior, and noise control before broad UI polish.

## Scope Boundary Review

In scope for Phase 5:

- Maintenance eligibility attribute and UI visibility.
- Event-triggered archive maintenance.
- Startup and daily inspections for maintained projects.
- Important chat mark/classification intake.
- Maintenance records, latest inspection time, pending confirmation creation, and low-noise behavior.

Out of scope for Phase 5:

- Phase 6 AI context query/onboarding API.
- Phase 7 full confirmation queue governance and resolution UX.
- Human escalation for archive failures.
- Full replacement of raw history.
- Universal classification of every chat message.

## Review Conclusion

No blocking product or technical clarification remains. The requirement is ready for a Phase 5 acceptance checklist. The main implementation risk is trigger noise; the checklist should therefore emphasize maintenance eligibility, high-value event rules, idempotency, skip behavior, and no-update inspection behavior.

