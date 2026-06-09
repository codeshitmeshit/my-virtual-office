# Phase 6 Codex Live Activity and Controls

## Background

Phase 5 made Codex a real Virtual Office collaborator with durable conversation context, final replies, modified-file reporting, compaction, busy protection, and cross-agent communication. During execution, however, users only see a general working state. Tool activity, approval requests, missing-information questions, and cancellation are not yet interactive.

## Target user

- Primary: a human user chatting with Codex in Virtual Office.
- Compatibility: OpenClaw and Hermes may continue sending messages to Codex, but they do not receive interactive approval authority in Phase 6.

## Primary problem

Users cannot tell what Codex is doing while a turn runs, whether it is progressing or blocked, or which operation caused a failure. When Codex needs approval or information, Phase 5 terminates the turn instead of letting the user intervene and continue.

## Goals

1. Make Codex execution understandable through live, expandable tool cards.
2. Let a human approve, answer, reject, or cancel without starting a replacement turn.
3. Restore complete activity and pending interaction state after page refresh.
4. Preserve the single-active-operation model and provide a clear route to the active conversation.
5. Keep all displayed and persisted activity safe from obvious credential disclosure.

## In scope

- Live activity for file reads, searches, command execution, file changes, external/MCP tool calls, and errors.
- Compact tool summaries by default, with expandable sanitized inputs, outputs, progress, and errors.
- Full activity persistence and recovery across refreshes, including pending approval and pending user-input cards.
- Human approval choices: allow once, allow matching activity for the current Codex runtime session, or reject.
- Free-text or structured answers to Codex information requests, continuing the original turn.
- Cancellation of the active turn while running or waiting for user interaction.
- Long trajectories retain all events while older cards are collapsed by default.
- After cancellation, retain activity and modified-file evidence and state clearly that cancellation does not roll back changes.
- Other chat windows show which conversation owns the active Codex turn and provide a way to navigate to it.

## Confirmed product behavior

1. Activity coverage is comprehensive rather than limited to command execution and file changes.
2. Inputs and outputs are visible only after automatic sensitive-value filtering.
3. Refresh restores the complete trajectory and any unresolved human interaction.
4. Interactive approval and user-input continuation are human-only.
5. Agent-originated requests that require interaction remain terminal human-intervention outcomes.
6. While interaction is pending, ordinary new messages are rejected; they are not treated as answers or queued.
7. Runtime-session authorization uses Codex's native `acceptForSession` behavior; the UI states that its scope and lifetime are controlled by the Codex runtime and are not tied to a VO conversation.
8. Cancellation keeps all factual history and existing file changes; it never implies automatic rollback.

## Success criteria

Primary success: a human can understand what Codex is currently doing, whether it is progressing or blocked, and what it did before completion, failure, or cancellation.

Secondary success: when Codex requests permission or information, the human can respond in the existing chat and the original turn continues to a terminal result.

## Out of scope

- Automatic rollback of file changes.
- Pause/resume controls distinct from approval waiting.
- Live steering or changing the task goal during execution.
- Parallel Codex turns or multiple Codex collaborators.
- Agent-driven approval decisions.
- Autonomous multi-agent loops and long-running project orchestration.
- Full diff review and accept/reject workflows.

## Product risks

- Tool inputs and outputs may contain source code or business data even after credential redaction; the UI must communicate their visibility.
- Runtime-session authorization can be misunderstood as conversation-scoped or permanent permission unless its native Codex scope and lifetime are explicit.
- High-volume output can overwhelm the chat unless batching, truncation indicators, and default collapsing are predictable.
- Cancellation can occur after side effects; the product must never present it as undo.
