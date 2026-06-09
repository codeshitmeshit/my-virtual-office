# Phase 6 Codex Live Activity and Controls Review

## Review status

Reviewed with no remaining blocking product or technical questions.

## Existing foundation

- Phase 5 maintains a persistent `codex app-server` client and durable `conversationId -> threadId` mapping.
- The server already enforces one active Codex operation and persists normalized communication history.
- The browser already renders OpenClaw and Hermes tool cards, so Codex can reuse the established visual model after event normalization.
- Current Codex handling only consumes final agent messages and file-change paths; approval and user-input requests are declined and interrupted.

## Protocol capability review

The locally generated Codex app-server schema supports the required Phase 6 behavior:

- `item/started` and `item/completed` expose structured turn items.
- command output, file-change progress, patch updates, and MCP progress have dedicated notifications.
- command and file approvals accept `accept`, `acceptForSession`, `decline`, and `cancel` decisions.
- tool user-input requests accept structured answers.
- `turn/interrupt` supports cancellation.
- `thread/read` with `includeTurns=true` returns persisted turns and items for recovery.

## Recommended technical direction

Extend the existing app-server client into a resumable operation broker instead of introducing a second bridge:

1. Normalize every supported Codex item into a provider-neutral activity event.
2. Persist activity and interaction state under `VO_STATUS_DIR` with conversation, thread, turn, and item correlation IDs.
3. Broadcast live events to the browser through a Codex-specific event stream or the existing office realtime surface.
4. Keep app-server request callbacks pending while a human decision is unresolved; map browser responses back to the original JSON-RPC request.
5. Rebuild browser state from persisted events and `thread/read` after refresh or service restart.

## State model

Recommended operation states:

- `running`
- `waiting_for_approval`
- `waiting_for_input`
- `cancelling`
- `completed`
- `failed`
- `cancelled`

The active-operation record should include conversation, thread, turn, pending server request, activity sequence, approval decisions, modified files, and timestamps. Terminal state must release the global Codex lock and restore presence to idle.

## Approval review

- Allow once maps to protocol `accept`.
- Allow for the current Codex runtime session maps to protocol `acceptForSession` for command execution and file-change approvals.
- The UI must describe this as a native Codex runtime-session decision, not a Virtual Office `conversationId`-scoped grant. Its exact cache lifetime is controlled by Codex.
- Permission-profile requests require an explicit least-privilege grant; unsupported or ambiguous grants must fail closed.
- Reject should use the decision that ends the current task, matching the confirmed product behavior.
- Approval requests include `threadId` and `turnId`, so the pending approval UI remains scoped to the correct conversation even though native runtime-session authorization is not.
- The public app-server API does not document listing or revoking native session approval-cache entries. Phase 6 therefore provides no authorization summary, manual revocation, or promise that a VO conversation reset clears this cache.

## User-input review

- Persist the question IDs, labels, choices, and whether free text is permitted.
- Only the owning human chat may answer.
- Ordinary chat sends remain blocked until the pending request is answered or cancelled.
- Agent-originated turns continue to fail closed with `needs_human_intervention` rather than waiting indefinitely.

## Event and persistence review

- Use immutable sequence numbers so live delivery, history reload, and deduplication agree.
- Store bounded payloads with explicit truncation metadata; do not silently drop the event itself.
- Restore historical cards from office persistence, using `thread/read(includeTurns=true)` as reconciliation rather than the sole UI database.
- Persist pending interaction before exposing it to the browser so refresh cannot lose the request.
- Do not persist raw terminal streams or tool payloads before redaction.

## Security review

- Apply recursive key-based and pattern-based redaction to arguments, output, errors, URLs, headers, and environment-like values.
- Never expose gateway tokens, API keys, cookies, authorization headers, or known secret-file contents.
- Keep output size limits and a visible truncation marker.
- Preserve the Phase 5 workspace sandbox and do not convert session approval into global or permanent permission.
- Log correlation IDs and decisions, but not raw sensitive payloads.

## Realtime and UI review

- Reuse existing tool-card components after adding Codex event normalization.
- Batch high-frequency output deltas to avoid DOM and storage amplification.
- Older cards remain available but collapsed; current running or pending cards remain expanded.
- A pending approval/input card must remain actionable after refresh.
- Non-owning windows show busy state plus a link or action to focus the active conversation.
- Cancellation must immediately disable duplicate actions and show a `cancelling` transition until terminal acknowledgement.

## Compatibility and migration

- Phase 5 synchronous response consumers remain compatible; live events are additive.
- Demo mode needs deterministic synthetic activity fixtures without invoking a real Codex account.
- Existing Phase 5 terminal human-intervention behavior remains for agent-originated messages.
- Existing OpenClaw and Hermes tool rendering and routing must not regress.
- Old history without activity metadata must continue to render normally.

## Recommended delivery phases

The Phase 6 scope should be delivered as three independently testable increments. This keeps the protocol and UI changes reviewable while preserving a usable result at the end of each increment.

### Phase 6A: Live activity visibility

Deliver the read-only execution-observability foundation:

- normalize Codex item lifecycle events;
- stream and persist command, file, search/read, MCP, and error activity;
- redact sensitive values and bound large payloads;
- render expandable tool cards and collapse older activity;
- restore completed and currently running activity after a browser refresh;
- preserve the existing Phase 5 terminal handling for approvals and user input.

Acceptance scope: CHK-001 through CHK-008, CHK-019, CHK-025, CHK-026, and the relevant parts of CHK-027/CHK-028.

This phase produces the primary user value: Codex is no longer a black box. It can ship without interactive approval risk.

### Phase 6B: Human-in-the-loop controls

Add the resumable interaction state machine:

- allow once, allow for the current Codex runtime session, and reject;
- answer structured or free-text Codex questions in the active chat;
- block ordinary sends while interaction is pending;
- cancel running or waiting turns;
- preserve activity and modified-file evidence after cancellation;
- keep agent-originated interaction requests fail closed.

Acceptance scope: CHK-009, CHK-010, and CHK-012 through CHK-018.

This phase is higher risk because it keeps app-server requests pending and maps browser actions back to the original turn. It should build on the event identity and persistence model proven in Phase 6A.

### Phase 6C: Recovery and production hardening

Complete durable recovery and cross-window behavior:

- restore pending approval/input cards after refresh;
- reconcile activity and terminal state after service restart;
- show waiting-for-user presence distinctly;
- direct other windows to the active conversation;
- harden deduplication, terminal cleanup, cancellation races, and delivery gaps;
- run the full Phase 5, OpenClaw, Hermes, demo, security, and browser acceptance matrix.

Acceptance scope: CHK-020 through CHK-022, CHK-024 through CHK-028, plus regression of all earlier Phase 6A/6B checks.

Phase 6 is complete only after Phase 6C. The sub-phases are delivery checkpoints, not separate product requirements, so they continue to share this requirement archive and checklist.

## Phase split rationale

- Two phases would combine interactive controls with recovery and create too large a state-management change to diagnose safely.
- Four or more phases would separate tightly coupled approval, cancellation, and authorization behavior and create temporary user experiences that are difficult to explain.
- Three phases align with the product value sequence: visibility, intervention, then durability.

## Observability

- Correlate request, conversation, thread, turn, item, pending interaction, and browser subscriber IDs.
- Record delivery gaps, duplicate events, redaction counts, truncation, decision latency, cancellation latency, and terminal state.
- Presence and active-operation diagnostics must distinguish running from waiting-for-user.

## Review conclusion

Live activity, allow-once approval, native runtime-session approval, reject/cancel, user input, and turn interruption are supported by the official app-server contract. Conversation-scoped authorization and manual revocation are excluded, so there are no remaining blocking technical questions before checklist confirmation.

## Source basis

- Phase 5 requirement, review, implementation, and tests in this repository.
- Existing OpenClaw/Hermes tool-card and history behavior in `app/chat.js` and `app/server.py`.
- Locally generated Codex app-server schema from the installed Codex CLI, including item notifications, approvals, user input, thread read, and turn interrupt.
- Official Codex App Server documentation checked on 2026-06-09, confirming `accept`, `acceptForSession`, `decline`, and `cancel`, while documenting no approval-cache list or revoke method.
