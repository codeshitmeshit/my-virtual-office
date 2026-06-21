# Archive Room Phase 7 Review

## Product Review

The product direction is clear enough to proceed to checklist.

The request narrows Phase 7 to governance rather than general archive browsing. The main value is giving humans a workable control point over long-lived knowledge and high-impact AI suggestions, while allowing objective source-backed facts and archive-manager-approved low-risk summaries to be confirmed without creating manual review noise. This fits the parent Archive Room requirement: archive data should be source-backed, confidence-aware, and safe for AI onboarding/context use.

Key product choices are coherent:

- Human project owner is the primary actor for governance decisions.
- Confirmation authority is tiered so not every reliable item requires human review.
- The archive manager is the decision owner for whether AI-processed content can be `archive_manager_confirmed`; ordinary business AI does not assign that authority directly.
- Pending confirmation queue is constrained to high-value governance items.
- Human-confirmed content is strongly protected from automatic AI overwrite.
- Edit-then-confirm allows humans to improve AI suggestions without losing traceability.
- Deferred items stay visible but lower priority.
- Processed history remains lightweight.

No additional product clarification is required before checklist generation.

## Technical Review

### Data And State

Phase 7 needs to formalize pending confirmation state transitions. Current archive records already contain `pendingConfirmations`, entries, confidence levels, source references, and maintenance metadata. The phase should extend these records conservatively rather than create a separate unrelated store.

Expected state model:

- system_confirmed / source_confirmed
- archive_manager_confirmed
- pending_human_confirmation
- deferred
- human_confirmed
- rejected

Each action should preserve:

- Actor.
- Timestamp.
- Optional reason.
- Original suggestion.
- Edited confirmed value when applicable.
- Sources.

Source/system-confirmed content should be derived from objective VO records or source events and should not enter the manual queue. Archive-manager-confirmed content should be produced or reviewed through the archive manager's judgment, retain source references and authority metadata, and not be assigned directly by ordinary business AI. Human-confirmed content should become or update a confirmed archive entry while retaining confirmation metadata.

### UI Surface

The Archive Room project detail page is the correct primary UI. The overview list should stay lightweight and only help users find governance work. Project detail should carry the actual decision UI.

The existing artifact modal and archive index should not be displaced. Pending confirmation UI should fit into the project detail flow as a dedicated governance section.

### API And Behavior

The implementation will likely need project-scoped actions for confirm/reject/defer/edit-confirm. These actions should be idempotent enough for repeated UI clicks or retry. Errors should not corrupt archive records.

AI context generation should filter or label content by governance status:

- Human-confirmed content is the highest-trust guidance.
- Source/system-confirmed content is trusted objective state.
- Archive-manager-confirmed content is usable source-backed context, but lower authority than human-confirmed content.
- Pending/deferred content should be marked as not confirmed.
- Rejected content should not appear as active guidance.
- Conflicts should be surfaced as conflict reminders rather than overwrites.

### Compatibility

Existing Phase 1-6 behavior must remain intact:

- Archive Room opens.
- Project list renders.
- Project detail renders.
- Archive index remains visible.
- Artifact browsing still works.
- Archive manager status and maintenance history still work.
- AI onboarding/context package still works.

### Risks

- Pending queue can become noisy if every weak inference enters the queue. Product scope avoids this by limiting automatic entry and allowing source/system confirmation for objective facts plus archive-manager judgment for suitable low-risk AI-processed content.
- Edit-confirm can lose traceability if the original suggestion is overwritten. The requirement explicitly preserves original suggestion history.
- Strong human-confirmed protection can create stale confirmed content if humans never revisit it. Phase 7 should show stale/conflict indicators, but full governance automation is not required.
- Rejected items can be re-proposed later, which preserves flexibility but may create repeat noise. This is accepted for Phase 7 and can be improved later.

## Review Conclusion

No blocking product or technical ambiguity remains for checklist drafting.

Proceed to checklist with emphasis on:

- Pending item display quality.
- Confirmation authority labels and auto-confirm eligibility.
- State transitions.
- Confirmation record durability.
- Human-confirmed content protection.
- Conflict summary-first display.
- Overview filters/sorting.
- Regression across Phase 1-6 surfaces.
