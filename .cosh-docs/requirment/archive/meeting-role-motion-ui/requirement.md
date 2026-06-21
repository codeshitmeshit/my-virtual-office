# Meeting Role Motion UI

## Background

Virtual Office meetings already place participants in the office and show active meeting metadata, transcripts, pending calls, and current speaker information in the meeting dashboard. The canvas characters, however, do not yet clearly express who is speaking and who is listening during a meeting.

The user wants meeting participants to feel more alive and make the current speaker easier to identify directly in the office scene.

## Target Users

- Local Virtual Office users watching AI meetings in the office canvas.
- Users who need to quickly understand who is currently speaking without reading only the meeting dashboard.

## Goals

- Make the current speaker visually identifiable during an active meeting.
- Add restrained meeting-room liveliness so non-speaking participants do not feel frozen.
- Align participant facing direction with the current speaker in a natural, not overly mechanical, way.
- Start mouth animation when a participant is considered speaking and stop it when that speaking state disappears.

## Scope

- Add active-meeting character motion in the office canvas.
- Current speaker should lightly bob up and down while speaking.
- Non-speaking participants should occasionally play a nod/listening animation.
- Non-speaking participants should face toward the current speaker while someone is speaking, with natural behavior preferred over instant rigid synchronization.
- Mouth animation should follow the active speaking state and stop when speaking ends.
- The first implementation should keep animation low-key with mild game-like liveliness.

## Non-Goals

- Do not change meeting execution rules, moderation rules, transcript content, or provider behavior.
- Do not make nodding mean agreement, voting, approval, or decision acceptance.
- Do not add new meeting controls or dashboard workflow in this requirement.
- Do not introduce large decorative effects that distract from meeting content.
- Do not change non-meeting idle, work, break, or social interaction semantics except where necessary to avoid conflicts.

## Product Clarification Results

- Primary product goals: improve current-speaker recognition and active-meeting atmosphere.
- Visual style: combine restrained office UI behavior with light game-like motion.
- Speaking state: product preference is to follow current-speaker state. Original wording also requested mouth animation when visible speech appears and stops when it disappears, so implementation should use current-speaker state as primary and visible/pending speech data as a compatible signal or fallback.
- Listener nodding: represents ordinary listening only, not agreement.
- Facing behavior: medium priority. Participants should usually turn toward the speaker, but small natural delays or non-frame-perfect sync are acceptable.

## Key Constraints

- Meeting participants can be represented by regular group meetings around the meeting table and 1:1 visiting meetings.
- Canvas character drawing already has mouth states, `talkTimer`, `faceDir`, social mouth overrides, and idle/social animations.
- Existing random talk animation in meeting or visiting states may conflict with deterministic speaker-driven mouth animation if not gated.
- Active executable meetings expose `currentSpeaker`, `transcript`, and `pendingCalls` in the meeting UI data path, while regular `_meetings` status processing currently drives canvas participant placement.
- The feature should degrade gracefully when no current speaker is known.

## Known Decisions

- Requirement directory name: `meeting-role-motion-ui`.
- Checklist must be confirmed before creating `todolist.md`.
