# Meeting Participant XP

## Background

The project leaderboard currently ranks AI agents by accumulated XP from project task completion and manual awards. Executable AI meetings record participants, moderator turns, meeting results, and conclusions, but meeting participation does not currently affect XP.

The user wants meeting-participating AI agents to gain some XP so collaboration work is reflected in the leaderboard.

## Target Users

- Local Virtual Office users who use Meeting for AI to coordinate multiple agents.
- AI agents that participate in executable meetings and should receive lightweight recognition for collaboration.

## Goals

- Award XP to AI agents that participate in an executable meeting when the meeting reaches a successful completed state.
- Keep leaderboard ranking based on existing cumulative XP without adding a separate ranking mechanism.
- Make XP awarding idempotent so repeated close/archive/end calls cannot double count the same meeting.
- Preserve existing task-completion XP behavior.

## Scope

- Add scoring for executable AI meetings.
- Reuse the existing `project-scores.json` score store and `/api/projects/scores` leaderboard response.
- Record meeting-award history in the existing score history format or a compatible extension.
- Cover all executable-meeting completion paths that set `stage: "completed"`.

## Non-Goals

- Do not award XP for cancelled, failed, paused, preparing, or awaiting-user-decision meetings.
- Do not change leaderboard sort order beyond XP totals.
- Do not add a new UI ranking mode.
- Do not award XP for ordinary non-executable meeting records unless explicitly requested later.
- Do not alter task completion XP values in this requirement.

## Proposed Product Rules

- Meeting participation XP is granted once per executable meeting when it transitions to `completed`.
- Each unique participant in `meeting.participants` receives a small base award.
- Moderator may receive the same participant award by default. A separate moderator bonus is optional but not required for this first version.
- Agents filtered out elsewhere as non-normal participants, such as archive manager agents, should not receive meeting XP.
- The award reason should include the meeting topic or meeting id for traceability.
- Default suggested value: `+3 XP` per participant per completed executable meeting.

## Key Constraints

- Existing score helper `_award_points()` increments both `score` and `completed`, which currently means task completions. Meeting XP must avoid making the `completed` count misleading unless the product explicitly accepts counting meetings there.
- Multiple completion paths exist in `app/server.py`, including moderator summary, arbitration decision, user moderator takeover, and fallback run completion.
- Completion handlers can be retried or called after terminal state. Awarding must be guarded by a per-meeting marker.
- Score persistence must remain compatible with existing `project-scores.json` data.

## Known Decisions

- Requirement directory name: `meeting-participant-xp`.
- Checklist must be confirmed before implementation planning.
