# Todolist: Meeting Participant XP

## TODO-001: Add Meeting-Specific Score Award Helper

- Goal: Implement a helper that awards meeting participation XP without changing task completion semantics.
- Involved areas: `app/server.py` project scoring section.
- Input: Completed executable meeting object, configured default meeting XP value, participant list.
- Output: Updated `project-scores.json` entries with increased `score`, optional `meetings` count, and meeting-specific history records.
- Dependencies: Existing `_load_scores()`, `_save_scores()`, `_is_archive_manager_agent()`, and timestamp helpers.
- Completion criteria: Helper skips invalid/system participants, does not increment task `completed`, records traceable history, and returns award metadata.
- Related checklist: CHK-001, CHK-004, CHK-005, CHK-007.

## TODO-002: Add Meeting-Level Idempotency Marker

- Goal: Prevent duplicate XP awards for the same meeting across repeated completion calls or restarts.
- Involved areas: `app/server.py` executable meeting store mutation paths.
- Input: Meeting id and existing meeting state.
- Output: Persistent marker such as `meeting["scoreAwarded"]["meetingParticipantXp"]` with participants, points, and timestamp.
- Dependencies: TODO-001.
- Completion criteria: Repeated terminal handling returns without additional score changes.
- Related checklist: CHK-002, CHK-010.

## TODO-003: Wire Awarding Into All Executable Meeting Completion Paths

- Goal: Award participant XP whenever an executable meeting successfully transitions to `completed`.
- Involved areas: Completion branches in `_handle_executable_meeting_end_with_moderator()`, `_handle_executable_meeting_arbitration()`, `_handle_executable_meeting_moderator_takeover()`, and `_handle_executable_meeting_run()`.
- Input: Meeting object after `stage` is set to `completed`.
- Output: Meeting participant XP awarded before the completed meeting is persisted.
- Dependencies: TODO-001, TODO-002.
- Completion criteria: All known completion paths call the meeting XP helper exactly once per meeting.
- Related checklist: CHK-001, CHK-002, CHK-006, CHK-010.

## TODO-004: Preserve Existing Task Scoring Behavior

- Goal: Ensure task scoring helper behavior and existing XP values remain unchanged.
- Involved areas: Task completion paths and existing `_award_points()` usage.
- Input: Existing task completion logic.
- Output: No behavior changes for task XP, task streak, due-date bonus, checklist bonus, and `completed` count.
- Dependencies: TODO-001 through TODO-003.
- Completion criteria: Existing task scoring tests or targeted checks continue to pass.
- Related checklist: CHK-009.

## TODO-005: Expose Meeting Count In Leaderboard Payload If Stored

- Goal: Make meeting XP metadata available without changing ranking behavior.
- Involved areas: `_handle_scores_leaderboard()` response construction.
- Input: Score entries containing optional `meetings`.
- Output: Leaderboard entries include `meetings` defaulting to `0`, while sorting remains by `score` descending.
- Dependencies: TODO-001.
- Completion criteria: `/api/projects/scores` remains backward-compatible and sorted by `score`.
- Related checklist: CHK-008.

## TODO-006: Add Focused Regression Tests

- Goal: Cover the scoring and idempotency behavior without broad unrelated test churn.
- Involved areas: Existing Python test suite, likely new or extended meeting/scoring tests.
- Input: Temporary status directory, synthetic executable meeting data, and score store.
- Output: Tests for participant XP, idempotency, non-completed states, task completed count preservation, invalid participant skipping, and leaderboard ordering.
- Dependencies: TODO-001 through TODO-005.
- Completion criteria: Tests pass locally and directly map to confirmed checklist items.
- Related checklist: CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-010.

## TODO-007: Update Delivery Notes After Implementation

- Goal: Record implementation and verification outcomes for this requirement.
- Involved areas: Requirement archive files and final delivery message.
- Input: Test commands and results from TODO-006.
- Output: Concise implementation summary and test evidence tied to checklist items.
- Dependencies: TODO-006.
- Completion criteria: User can see what changed, how it was verified, and any remaining risk.
- Related checklist: CHK-009, CHK-010.
