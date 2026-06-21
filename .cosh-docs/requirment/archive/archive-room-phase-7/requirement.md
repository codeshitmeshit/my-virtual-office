# Archive Room Phase 7 Requirement

## Background

Archive Room Phase 1-6 have delivered archive storage, the main Archive Room UI, project archive detail, artifact browsing, archive manager lifecycle, event/scheduled maintenance, human-readable project archive summaries, archive index, and AI onboarding/context packages.

The remaining product gap is trust governance. Archive Room can now collect and surface project knowledge, but it still needs a practical trust model: objective source-backed facts should not wait for humans, AI-processed archive content should be judged by the archive manager before it is trusted, and humans should focus on long-lived rules, high-impact judgments, and conflicts with confirmed knowledge.

## Goal

Make Archive Room's pending confirmations and knowledge governance practical for human project owners without forcing every reliable fact or low-risk AI summary through manual confirmation.

Phase 7 should let a human quickly discover projects needing governance, inspect pending confirmation items in project detail, understand their evidence and impact, confirm/reject/defer them, optionally edit before confirmation, and preserve human-confirmed knowledge from automatic AI overwrite. It should also let the system mark objective source facts, and let the archive manager judge whether AI-processed content can be confirmed under archive-manager authority, so the human queue stays focused.

## Primary User

The primary user is the human project owner or project operator. Execution AI and the archive manager benefit from the results, but the core workflow is human confirmation.

## Product Decisions From Clarification

- Phase 7 prioritizes the human confirmer / project owner, but does not require human confirmation for every archived fact.
- Confirmation authority is tiered:
  - `system_confirmed` / `source_confirmed`: objective facts directly proven by VO data or source events, such as task completion, artifact creation, meeting end, project status change, and artifact source/path mapping.
  - `archive_manager_confirmed`: low-risk, source-backed summaries or classifications that the archive manager has judged safe to confirm, such as meeting summaries, task result summaries, important-message classification, and artifact descriptions.
  - `human_confirmed`: long-lived rules, high-impact decisions, conflict resolutions, and edited confirmations made by a human.
  - `pending_human_confirmation`, `deferred`, and `rejected` remain explicit governance states.
- Ordinary business AI can propose or produce archive material, but it should not decide the final confirmation authority for AI-processed content; that judgment belongs to the archive manager.
- The pending confirmation queue includes:
  - Long-lived rules.
  - High-impact suggestions.
  - All items that conflict with confirmed content, especially human-confirmed rules or decisions.
- The pending confirmation queue excludes content that can be safely confirmed by source/system evidence or by archive-manager low-risk judgment.
- Phase 7 does not put every AI inference into the confirmation queue.
- User actions are:
  - Confirm.
  - Reject.
  - Defer.
  - Edit then confirm.
- Edit-then-confirm creates a human-confirmed version; the original AI suggestion remains as source/history.
- Human-confirmed content has strong protection:
  - AI must not automatically overwrite it.
  - New conflicting information becomes a conflict/pending item.
- Rejected items are recorded for this occurrence, but the archive manager may propose a similar item again later if it believes it is warranted.
- Confirmation/rejection/defer reasons are optional, not mandatory.
- Deferred items remain in the pending section but are marked deferred and sorted lower or collapsed by default.
- Confirmed items move into the archive context / key rules area and carry confirmation records; they do not remain in the main pending queue.
- Conflict item detail should be summary-first:
  - First show a concise conflict explanation.
  - Then allow viewing both sides and their sources.
- Pending queue default ordering:
  - Severe conflicts.
  - High-impact suggestions.
  - Long-lived rules.
  - Ordinary pending confirmations.
  - Deferred items.
- Archive Room overview should help discover governance work:
  - Default pending/risk priority.
  - Filter for projects with pending confirmations.
  - Filter for projects with risks.
  - Recent update sorting.
- A lightweight processed-history entry is needed in project detail:
  - View confirmed/rejected/deferred history.
  - Do not build a full audit center in this phase.

## Scope

### In Scope

- Project detail pending confirmation section.
- Pending confirmation item cards with:
  - Proposed content.
  - Confidence.
  - Impact area.
  - Reason.
  - Source references.
  - Created time.
  - Current status.
  - Conflict summary when applicable.
- User actions:
  - Confirm.
  - Reject.
  - Defer.
  - Edit then confirm.
  - Optional reason for each action.
- Confirmed entry conversion:
  - Confirmed item becomes a confirmed archive entry or confirmed rule.
  - Original suggestion is retained as source/history when edited.
  - Confirmation record is stored.
- Rejected/deferred records:
  - Rejected items become processed history for that occurrence.
  - Deferred items remain visible but lower-priority/collapsed.
- Conflict governance:
  - Confirmed facts/rules are not auto-overwritten.
  - Conflicting new suggestions are shown as conflicts.
  - Conflict details present a human-readable summary first, with sources available.
- Archive Room overview filtering/sorting:
  - Pending-first/risk-first default priority.
  - Filter to only projects with pending confirmations.
  - Filter to only projects with risks.
  - Recent update sorting.
- Lightweight processed-history view in project detail.
- AI context behavior should respect confirmation state:
  - Human-confirmed content is highest trust.
  - Source/system-confirmed content is trusted objective state.
  - Archive-manager-confirmed content is usable source-backed context, but lower authority than human-confirmed content.
  - Pending/deferred content is lower trust and should not be treated as settled guidance.
  - Rejected content should not be presented as active truth.

### Out Of Scope

- Full audit center across all projects.
- Complex role/permission system for multiple human approvers.
- Mandatory reason collection.
- Automatic semantic deduplication of rejected items.
- Full text diff editor for conflicts.
- Replacing raw project/task/chat/meeting history.
- Broad redesign of Archive Room outside governance surfaces.

## Success Criteria

- A human can open Archive Room and quickly find projects with pending/risk governance work.
- A human can open a project and understand each pending item without leaving Archive Room.
- A human can confirm, reject, defer, or edit-confirm a pending item.
- Confirmed content is preserved as trusted archive knowledge with a confirmation record.
- AI-generated conflicts do not silently overwrite human-confirmed content.
- Deferred and processed items remain traceable without crowding the main pending queue.
- Existing Archive Room project summaries, archive index, artifact browsing, maintenance status, and AI onboarding context remain usable.
