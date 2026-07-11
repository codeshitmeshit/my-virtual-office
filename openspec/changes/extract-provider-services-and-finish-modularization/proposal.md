## Why

Provider run orchestration, conversations, approvals, cancellation, and event normalization remain distributed across the main server and provider adapters. The final modularization phase should establish provider-neutral service ownership and retire temporary migration seams.

## What Changes

- Extract provider registry, run lifecycle, conversation, approval, cancellation, and event-normalization orchestration into provider-neutral services.
- Keep Codex, Claude Code, Hermes, and OpenClaw adapters responsible for provider-specific protocol conversion.
- Preserve run/SSE semantics, conversation continuation, approval and cancellation behavior, provider isolation, API contracts, and persisted mappings.
- Remove obsolete compatibility delegates after all migrated paths pass regression tests.
- Complete architecture documentation and enforce the final module dependency direction.
- This change starts only after the meeting and collaboration service change is accepted and archived.

## Capabilities

### New Capabilities

- `provider-service-boundaries`: Defines provider-neutral runtime orchestration and provider-adapter responsibility boundaries.

### Modified Capabilities

None currently; detailed review must reassess existing provider behavior requirements before implementation.

## Impact

- Expected code: `app/server.py`, `app/providers/`, provider execution helpers, new provider service modules, and provider/SSE contract tests.
- No intentional frontend protocol, provider behavior, persistence, or runtime dependency changes.
- This is the final roadmap change; detailed design depends on the accepted outcomes of the preceding phases.
