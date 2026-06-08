# Phase 5 Codex Live Bridge

## Background

Phase 4 exposes one Codex collaborator as a first-class Virtual Office agent, but the adapter only supports discovery, presence, visible communication events, and deterministic demo replies. Phase 5 must connect that adapter to a real local Codex execution surface.

## Target user

- Primary: a human user chatting with Codex from Virtual Office.
- Compatibility scope: OpenClaw and Hermes may send office-mediated messages to Codex, but their experience is not the primary Phase 5 optimization target.

## Goals

- Send one office-mediated message to a real Codex session.
- Support questions, analysis, and localized workspace code changes that finish in one turn.
- Preserve Codex context within the same office conversation across page refreshes.
- Isolate different office conversations from one another.
- Record working, success, timeout, error, and human-intervention outcomes in office history.
- Include the list of modified files in the final result when Codex changes the workspace.

## In scope

- One configured Codex collaborator.
- One active turn at a time for that collaborator.
- Workspace read and write access limited to the configured workspace.
- A stable mapping from an office `conversationId` to a Codex thread/session.
- Reusing that mapping until the user creates or resets the office conversation.
- Manually compacting the mapped Codex thread while preserving the conversation identity and visible history.
- Rejecting a new message while Codex is already working.
- A complete request lifecycle: accepted, working, completed or failed, and persisted history.
- Clear terminal handling when Codex needs approval, lacks required information, times out, or exceeds the short-task boundary.

## Out of scope

- Queuing messages while Codex is busy.
- Steering or supplementing a turn while it is running.
- Resuming a failed or interrupted turn through an approval flow.
- Long-running project automation and multi-step orchestration.
- Cancellation controls and streamed tool or file events in the UI.
- Full diff review, accept, reject, or rollback workflows.
- Multiple Codex collaborators.

## Confirmed product behavior

1. Human-originated chat is the primary launch path.
2. Each short task is expected to complete in one turn.
3. A conversation keeps context across page refreshes until explicitly reset or replaced.
4. A second message received while Codex is working is rejected with a wait message.
5. The final response identifies files modified by the turn.
6. Approval needs, missing information, unsupported task scope, timeout, and execution errors terminate the turn and clearly indicate that human intervention is required when applicable.
7. The user can explicitly compress the current Codex context without clearing the office chat or creating a new conversation.

## Success criteria

A human user can send a short task from Virtual Office to Codex, observe the working state, receive a real final response or a clear terminal failure, see modified-file information when applicable, refresh and continue the same conversation with retained context, explicitly compact that context, and inspect the persisted request and result in office history.

## Product constraints

- Existing Phase 4 demo reply behavior remains available for deterministic regression tests.
- OpenClaw and Hermes behavior must not regress.
- Phase 5 must retain a clear boundary from Phase 6 advanced session controls.
