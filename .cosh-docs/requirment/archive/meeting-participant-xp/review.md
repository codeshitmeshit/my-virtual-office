# Review: Meeting Participant XP

## Product Review

The requirement is product-feasible. Meeting participation is a recognizable contribution type and can reasonably affect the same XP leaderboard used for tasks. The main product risk is score inflation or confusing task-completion counts.

Recommended product stance:

- Award only on completed executable AI meetings.
- Keep the default award small, initially `+3 XP` per participant.
- Do not count meeting XP as task completion.
- Show meeting awards in score history with a clear reason such as `Meeting completed: <topic>`.

No blocking product ambiguity remains for generating a checklist. The exact XP value can remain configurable or centralized as a constant during implementation; the checklist will verify the default.

## Technical Review

### Current Scoring Model

The existing score store is `STATUS_DIR/project-scores.json`, loaded by `_load_scores()` and saved by `_save_scores()` in `app/server.py`.

Leaderboard data is returned by `_handle_scores_leaderboard()` and sorted only by `score` descending.

Existing helper `_award_points(agent_key, points, reason)`:

- skips empty/unassigned agents;
- applies streak bonus based on `lastCompleted`;
- increments `score`;
- increments `completed`;
- updates `lastCompleted`;
- appends a history record.

This helper is task-oriented. Reusing it directly for meetings would incorrectly increment `completed` as if a task was completed and would apply task streak bonuses to meeting attendance.

### Meeting Completion Paths

Executable meeting completion occurs in multiple paths:

- `_handle_executable_meeting_end_with_moderator()` after moderator summary success.
- `_handle_executable_meeting_arbitration()` for final user/moderator arbitration decisions.
- `_handle_executable_meeting_moderator_takeover()` when a user closes after moderator failure.
- `_handle_executable_meeting_run()` fallback completion after rounds complete.

All of these set `meeting["stage"] = "completed"` and then call `_archive_trigger_meeting_conclusion(meeting)` outside the lock or after save.

### Recommended Implementation Shape

Add a meeting-specific scoring helper near the project scoring section:

- `_award_meeting_participation_points(meeting, points=None, reason=None)`
- It should validate `meeting.id`, `meeting.stage == "completed"`, and a non-empty unique participants list.
- It should skip archive manager and invalid/unassigned participants.
- It should use a per-meeting idempotency marker on the meeting object, for example `meeting["scoreAwarded"] = {"meetingParticipantXp": true, "at": ..., "points": ..., "participants": [...]}`.
- It should update the same score file but not increment task `completed`.
- It may update a separate `meetings` count per agent, e.g. `agent["meetings"]`.
- It should append to `history` with fields such as `type: "meeting_participation"`, `meetingId`, `points`, `reason`, and `at`.
- It should not apply task streak bonus unless a future product decision explicitly asks for meeting streaks.

Then call this helper in a single centralized completion helper if feasible, or immediately before each `_save_exec_meeting_store(store)` after setting `stage: "completed"` in all completion paths. Because the idempotency marker is stored on the meeting, the meeting store save must include it.

### Data Compatibility

Existing leaderboard reads only `score`, `completed`, and `streak`, so adding `meetings` and richer history entries is backward-compatible. Existing agents without `meetings` should default to `0`.

Optionally update `/api/projects/scores` to include `meetings` so future UI can display it. This is low risk because clients ignore unknown fields.

### Tests

Focused unit-style tests should cover:

- completed executable meeting awards all unique participants exactly once;
- duplicate completion/end calls do not double award;
- moderator is included as a normal participant;
- cancelled or failed meetings do not award;
- archive-manager participants are skipped defensively;
- leaderboard score increases but task completed count does not.

## Risks And Mitigations

- Risk: XP can be farmed by creating short meetings.
  Mitigation: keep award small and only completed executable meetings count.

- Risk: double awards from multiple completion paths or retries.
  Mitigation: persist a meeting-level idempotency marker before saving the completed meeting.

- Risk: confusing `completed` count.
  Mitigation: implement a meeting-specific award helper that increments `score` and `meetings`, not task `completed`.

- Risk: missed completion path.
  Mitigation: test all completion paths or refactor terminal completion to a shared helper.

## Review Conclusion

No blocking technical issue remains. Proceed to checklist confirmation before implementation planning.
