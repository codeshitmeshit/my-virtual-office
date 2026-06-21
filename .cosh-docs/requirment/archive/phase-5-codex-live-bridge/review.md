# Phase 5 Codex Live Bridge Review

## Review status

Reviewed with no remaining blocking product or technical questions.

## Existing foundation

- `app/providers/codex.py` already owns Codex discovery and message dispatch, and reserves `VO_CODEX_BRIDGE_URL`.
- `app/server.py` routes human and agent messages through `/api/agent-platform-communications/send` and persists normalized request/reply events in an office-owned JSONL history.
- Presence already changes to `working` around synchronous provider calls and returns to `idle` afterward.
- The current Codex provider has no live bridge call, conversation-to-thread persistence, busy lock, timeout classification, approval classification, or modified-file result contract.

## Recommended technical direction

Use a local bridge process backed by `codex app-server`, with Virtual Office remaining the owner of office conversation mapping and normalized event persistence.

Reasons:

- The official Codex app-server interface is intended for rich product integrations and exposes threads, turns, approvals, conversation history, final statuses, and item events.
- `thread/start` and `thread/resume` directly support the confirmed conversation continuity requirement.
- Turn and item notifications can distinguish completion, failure, approval needs, and file changes without parsing human-readable CLI output.
- `codex exec` is suitable for isolated automation, but using `exec resume` plus JSONL parsing would create a narrower and more fragile session bridge for a chat product.

Recommended ownership boundary:

- Codex app-server owns Codex authentication, threads, turns, and execution events.
- The bridge owns app-server process lifecycle, protocol normalization, timeout enforcement, and conversion to a compact HTTP contract.
- Virtual Office owns `conversationId -> Codex threadId`, the one-active-turn lock, office presence, communication history, and user-facing status classification.

Recommended security baseline:

- Bind the bridge locally rather than exposing an unauthenticated non-loopback Codex listener.
- Run turns with workspace-write permissions restricted to `VO_CODEX_WORKSPACE`.
- Do not auto-approve actions outside the configured workspace or actions requiring elevated/network permission.
- Treat approval-required events as terminal `needs_human_intervention` outcomes for Phase 5.

## Required response model

The normalized bridge result should carry at least:

- success flag and terminal status;
- Codex thread and turn identifiers;
- final agent reply;
- modified file paths;
- structured error code and safe error message;
- whether human intervention is required;
- timing information sufficient to diagnose timeouts.

## State and persistence review

- Office communication history is append-only JSONL and can already retain request/reply text, but it needs structured metadata for terminal status, Codex identifiers, and modified files.
- Conversation continuity requires a durable mapping stored under `VO_STATUS_DIR`; deriving the Codex thread only from visible chat text is not sufficient.
- The busy rule requires an atomic per-collaborator active-turn guard. Presence alone is display state and is not a concurrency lock.
- Conversation reset must delete or invalidate the office mapping without deleting visible communication history.
- Context compaction must retain the same office conversation and Codex thread mapping, record its outcome, and reject execution when another turn or compaction is active.

## Compatibility and migration

- Preserve `VO_CODEX_REPLY_TEXT` as the deterministic test mode.
- Preserve the existing no-bridge error when neither a live bridge nor demo reply is configured.
- Additive metadata should keep existing `/api/agent-platform-communications/send` consumers working.
- OpenClaw and Hermes routing should remain unchanged.

## Observability requirements

- Log request/conversation/thread/turn correlation identifiers without logging credentials.
- Record terminal categories separately: completed, busy, timeout, approval-required, invalid-request, bridge-unavailable, and execution-failed.
- Ensure presence always returns from `working` to `idle`, including protocol and timeout failures.

## Confirmed technical decisions

### TQ-001: Bridge runtime

Virtual Office starts and supervises a local app-server bridge by default, while retaining `VO_CODEX_BRIDGE_URL` as an external service override.

### TQ-002: Approval policy

Retain the normal workspace sandbox. Convert any approval request into a terminal human-intervention result rather than auto-approving it.

### TQ-003: Modified-file source

Use Codex file-change items as the primary source and a before/after Git status comparison as a validation fallback. Return paths only, not a full diff.

### TQ-004: Conversation reset surface

The existing clear/new-conversation action resets the Codex thread mapping so visible history and hidden context cannot diverge.

In addition, expose a distinct compact-context action. It calls the current app-server `thread/compact/start` method for the mapped thread, keeps the same conversation and visible history, reports working/success/failure state, and shares the single-active-operation lock with normal turns.

## Review conclusion

The current architecture can support Phase 5 without changing the provider abstraction or communication endpoint. The lifecycle, security, file-result, reset, and compaction decisions are confirmed, so the requirement can proceed to checklist review.

## Source basis

- Repository: `docs/UNIVERSAL-AGENT-HARNESS-SPEC.md`, `docs/CODEX_PROVIDER_ADAPTER.md`, `app/providers/codex.py`, and the office communication flow in `app/server.py`.
- OpenAI Codex manual fetched on 2026-06-09: Codex App Server and Non-interactive Mode sections.
- Locally generated app-server schema from `codex-cli 0.137.0`, confirming `thread/compact/start` with a required `threadId`.
