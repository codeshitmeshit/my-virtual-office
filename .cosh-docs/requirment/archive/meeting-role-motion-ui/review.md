# Review: Meeting Role Motion UI

## Product Review

The clarified requirement is product-feasible and internally consistent. It improves two visible problems in meetings: users can identify the active speaker faster, and the meeting scene feels less static.

Recommended product stance:

- Treat current-speaker clarity as the primary acceptance target.
- Keep motion subtle: a small vertical speaking bob, occasional listener nods, and facing changes are enough.
- Avoid interpreting listener nods as agreement. They should be idle/listening feedback only.
- Prefer current-speaker state as the canonical speaking signal. Use visible speech or pending-call state as fallback if current-speaker data is absent.
- Keep behavior scoped to active meetings so normal office movement remains unchanged.

No product blocker remains.

## Technical Review

### Existing Frontend State

Meeting placement is handled in `app/game.js` by `processMeetings()`, `activeMeetings`, `Agent.joinMeeting()`, `Agent.visitAgent()`, and `Agent.leaveMeeting()`.

The meeting dashboard separately polls `/api/meetings/active` and executable meeting events, storing merged active data in `_mtgData.active` and `_mtgLiveEvents`. Active meeting cards already read `m.currentSpeaker`, `m.transcript`, and `m.pendingCalls`.

Character rendering already supports:

- `faceDir` for left/right facing;
- `talkTimer` for mouth animation;
- `_socialMouth` overrides for open/half/closed/laugh mouth states;
- per-frame `tick`;
- meeting and visiting states.

### Current Gap

The canvas meeting projection uses `_meetings` from `/status` to position characters, but that projection does not appear to carry rich speaking metadata into `activeMeetings`. Meeting dashboard state has speaker metadata, but canvas animation currently does not consume it.

Also, `Agent.update()` currently contains random talk animation for `meeting` and `visiting` states. If left unchanged, non-speakers may continue random mouth movement even when only one participant should be speaking.

### Recommended Implementation Shape

Add a small frontend meeting-motion layer in `app/game.js`:

- Maintain enough metadata in `activeMeetings[meetingId]` to know participants and current speaker.
- Derive current speaker for an active meeting from, in order:
  - `m.currentSpeaker`;
  - active `pendingCalls` speaker if a provider call is in progress;
  - the most recent transcript turn if it should remain visible briefly;
  - visible speech state only as a fallback.
- Resolve speaker keys against `agentMap` using known participant ids and status keys.
- In each frame or during agent update/draw, compute each participant's role in the meeting:
  - speaker: subtle vertical bob and deterministic mouth animation;
  - listener: occasional nod animation and face toward speaker;
  - no speaker: no forced meeting-motion state.
- Avoid mutating base coordinates permanently for bob/nod; apply draw-time offsets or temporary transforms.
- Gate random meeting `talkTimer` so it does not make listeners speak while another participant is the speaker.

### Facing Behavior

For horizontal sprites, `faceDir` only supports left/right. The practical behavior should be:

- if speaker.x > listener.x, listener `faceDir = 1`;
- if speaker.x < listener.x, listener `faceDir = -1`;
- avoid changing `faceDir` when participants overlap or no speaker is known.

Natural delay can be approximated by updating facing at a controlled interval or allowing normal update cadence; no new product state is required.

### Animation Behavior

The speaker bob should be low amplitude, approximately 1-3 pixels, and only while speaking. It should not affect collision, pathfinding, sort order, or target position.

Listener nods should be occasional and deterministic enough not to flicker constantly. They can be staggered by agent id/tick so all listeners do not nod in sync.

Mouth animation should reuse existing `_socialMouth` or `talkTimer` drawing pathways rather than adding a separate face renderer. The important constraint is stopping the mouth when speaking state disappears.

### Compatibility

The feature is frontend-only unless `/status` lacks enough speaking metadata for the canvas. If richer metadata is needed, prefer reusing existing `/api/meetings/active` data already fetched for the meeting dashboard before adding new backend fields.

The change should remain compatible with:

- active executable meetings;
- regular active meeting records that lack `currentSpeaker`;
- 1:1 visiting meetings;
- group meetings at the meeting table;
- normal idle/social/break animations outside meetings.

### Testability

Automated coverage is likely limited because canvas animation is visual. Useful verification should combine:

- static/unit-style checks for helper functions if helpers are extracted;
- manual browser validation with a simulated active meeting and current speaker;
- regression checks that meeting placement, dashboard rendering, and existing meeting tests still pass.

## Risks And Mitigations

- Risk: random existing meeting talk animation conflicts with speaker-driven mouth animation.
  Mitigation: disable random mouth animation for meeting participants when a known meeting speaker exists.

- Risk: current speaker id may not map to a canvas agent key.
  Mitigation: normalize ids and gracefully fall back to no forced speaking animation.

- Risk: all listeners nod in sync and look artificial.
  Mitigation: stagger nod timing by agent id or participant index.

- Risk: draw-time bob changes visual overlap or causes jitter.
  Mitigation: keep bob amplitude small and avoid changing persisted `x`, `y`, `targetX`, or `targetY`.

- Risk: meeting dashboard live state and canvas state diverge.
  Mitigation: use the same active meeting data source where practical and treat missing speaker metadata as non-blocking.

## Review Conclusion

No blocking product or technical issue remains. Proceed to checklist confirmation before implementation planning.
