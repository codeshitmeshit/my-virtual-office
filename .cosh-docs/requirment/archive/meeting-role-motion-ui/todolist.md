# Todolist: Meeting Role Motion UI

## TODO-001: Map active meeting speaker state into canvas meeting metadata

- Goal: Make the office canvas know which participant is currently speaking in each active meeting.
- Involved areas: `app/game.js` meeting state paths, including `processMeetings()`, `activeMeetings`, `_mtgData.active`, and live meeting merge helpers.
- Input: Active meeting records with participants, `currentSpeaker`, `pendingCalls`, and transcript data where available.
- Output: A normalized per-meeting speaker signal that canvas agent animation can query.
- Dependencies: Existing `agentMap`, `activeMeetings`, and meeting dashboard active data.
- Completion criteria: Group and 1:1 meeting records can resolve a speaker agent when speaker metadata is present, and return no speaker when it is absent or unresolvable.
- Related checklist: CHK-001, CHK-006, CHK-010.

## TODO-002: Add helper functions for meeting role motion

- Goal: Centralize speaker/listener state, face direction, bob offset, nod offset, and mouth state calculation.
- Involved areas: `app/game.js` near meeting or agent animation helpers.
- Input: Agent instance, active meeting metadata, current tick/time, and resolved speaker agent.
- Output: Small helper API such as current meeting role, speaking state, listener nod phase, and draw-time vertical offset.
- Dependencies: TODO-001.
- Completion criteria: Helpers are deterministic, handle missing data safely, and do not mutate persisted `x`, `y`, `targetX`, or `targetY` for visual offsets.
- Related checklist: CHK-001, CHK-002, CHK-003, CHK-005, CHK-006, CHK-009.

## TODO-003: Implement speaker bob and mouth animation

- Goal: Show the current speaker with subtle body bob and active mouth movement while speaking.
- Involved areas: `Agent.draw()` and existing mouth rendering paths using `talkTimer` or `_socialMouth`.
- Input: Speaker role state from meeting motion helpers.
- Output: Current speaker renders with restrained vertical bob and mouth animation only while speaking.
- Dependencies: TODO-001, TODO-002.
- Completion criteria: Speaker bob is small and draw-time only; mouth starts with speaker state and stops after speaker state disappears.
- Related checklist: CHK-001, CHK-002, CHK-009.

## TODO-004: Implement listener nod animation

- Goal: Make non-speaking participants occasionally nod to communicate listening.
- Involved areas: `Agent.draw()` or adjacent animation helper code in `app/game.js`.
- Input: Listener role state and per-agent stagger seed.
- Output: Non-speaking participants occasionally nod with restrained, staggered motion.
- Dependencies: TODO-002.
- Completion criteria: Listeners do not remain completely static, nods do not synchronize across all participants, and nods do not create decision/agreement state.
- Related checklist: CHK-003, CHK-004, CHK-009.

## TODO-005: Make listeners face the current speaker

- Goal: Turn non-speaking participants toward the current speaker during active speaking state.
- Involved areas: `Agent.update()` meeting/visiting behavior and `faceDir` handling.
- Input: Listener agent position and resolved speaker agent position.
- Output: Listener `faceDir` points toward the current speaker when speaker position is meaningfully left or right.
- Dependencies: TODO-001, TODO-002.
- Completion criteria: Listeners usually face the speaker; no forced face direction is applied when no speaker is known or the speaker cannot be resolved.
- Related checklist: CHK-005, CHK-006, CHK-007.

## TODO-006: Gate random meeting mouth animation

- Goal: Prevent random meeting/visiting `talkTimer` from making listeners appear to speak while another participant is the current speaker.
- Involved areas: `Agent.update()` random talking logic for `meeting` and `visiting` states.
- Input: Meeting role state from helpers.
- Output: Random talk animation is suppressed for meeting listeners when a known speaker exists, while non-meeting social animation remains unchanged.
- Dependencies: TODO-002, TODO-003.
- Completion criteria: Listeners do not randomly mouth-talk during an active speaker turn; non-meeting idle/social mouth behavior still works.
- Related checklist: CHK-002, CHK-008.

## TODO-007: Preserve existing meeting placement and lifecycle

- Goal: Keep current group meeting and 1:1 visiting placement behavior intact.
- Involved areas: `processMeetings()`, `Agent.joinMeeting()`, `Agent.visitAgent()`, `Agent.leaveMeeting()`.
- Input: Existing `_meetings` status records and active meeting records.
- Output: Meeting motion metadata layers on top of existing placement without breaking join/leave behavior.
- Dependencies: TODO-001 through TODO-006.
- Completion criteria: Participants still move to expected table slots or visiting positions and return to desk on meeting end.
- Related checklist: CHK-007, CHK-008.

## TODO-008: Run focused regression checks

- Goal: Verify meeting behavior and related automated checks still pass.
- Involved areas: Existing test suite, likely meeting-related Python tests.
- Input: Implemented frontend changes and existing tests.
- Output: Test command results documented in delivery notes or checklist.
- Dependencies: TODO-001 through TODO-007.
- Completion criteria: Relevant meeting tests pass, or unrelated failures are documented with reason.
- Related checklist: CHK-011.

## TODO-009: Perform manual canvas verification

- Goal: Validate the visual behavior that automated tests cannot fully cover.
- Involved areas: Running app in browser, office canvas, meetings dashboard.
- Input: Active meeting scenario with at least two participants and speaker transitions.
- Output: Manual verification notes covering speaker bob, mouth stop, listener nod, facing, and dashboard integrity.
- Dependencies: TODO-001 through TODO-008.
- Completion criteria: Manual verification result is documented and covers CHK-001 through CHK-010 and CHK-012.
- Related checklist: CHK-001, CHK-002, CHK-003, CHK-004, CHK-005, CHK-006, CHK-007, CHK-008, CHK-009, CHK-010, CHK-012.
