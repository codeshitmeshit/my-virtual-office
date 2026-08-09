## Why

Standard chat and Project Execution chat currently derive displayable conversation history, live progress, reasoning, tools, and status through separate provider-specific paths. The duplication has already produced observable drift—including missing Claude Code project conversation data, inaccurate Hermes reasoning state, incomplete OpenClaw projection, and a second Codex reasoning aggregator—and makes future provider support harder to keep correct.

## What Changes

- Establish one provider-neutral conversation timeline contract for standard chat and Project Execution chat across Codex, Claude Code, Hermes, and OpenClaw.
- Require both surfaces to project the same provider run and conversation scope into consistent message content, reasoning, tool activity, status, ordering, identity, and recoverable history while allowing their visual presentation to remain different.
- Normalize provider-specific durable history and live/transient progress without fabricating reasoning that a provider did not supply.
- Preserve strict Agent, provider, conversation, project, task, and attempt isolation during live delivery and history recovery.
- Remove parallel timeline interpretation and aggregation responsibilities after callers migrate to the shared authority.
- Permit reproducible defects found in the migrated timeline paths to be corrected when the expected behavior follows the confirmed consistency, isolation, or accuracy requirements and a regression scenario distinguishes the fix from refactoring drift.
- Preserve existing public routes and compatible response fields; no project-page or chat-window visual redesign is included.

## Capabilities

### New Capabilities

- `conversation-timeline-projection`: Defines the shared provider-neutral projection, cross-surface consistency, live/history reconciliation, provider degradation, isolation, compatibility, and verified in-scope defect-correction requirements for Codex, Claude Code, Hermes, and OpenClaw conversations.

### Modified Capabilities

None. Existing chat history navigation and Project Execution service-boundary requirements remain valid; this capability adds the cross-surface behavioral authority they currently lack.

## Impact

- Affected backend areas include provider conversation/history services, provider event/progress normalization, Project Execution workflow-chat reads, OpenClaw session projection, and thin HTTP compatibility delegates.
- Existing standard-chat and Project Execution endpoints remain compatible, but their normalized content and state will come from one shared authority.
- Provider adapters continue to own native protocol parsing; the shared projection owns provider-neutral timeline semantics.
- Tests will cover all four providers, active and completed runs, refresh recovery, ordering, deduplication, status normalization, scope isolation, unavailable reasoning, and failing-before regressions for confirmed defects.
- Unrelated working-tree changes and defects outside the migrated timeline paths are excluded.
