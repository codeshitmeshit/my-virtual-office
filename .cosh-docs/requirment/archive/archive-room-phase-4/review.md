# Archive Room Phase 4 Review

## Product Review

Phase 4 is well-scoped after clarification. It answers the next product question after Phase 1-3: who maintains the archive, where can users see that maintainer, and how can users control it.

The main product risk is scope creep. The phrase "manual整理" can easily expand into Phase 5 automatic maintenance or Phase 6 AI context behavior. This sub-requirement must keep it narrow:

- one global archive manager
- lifecycle and status
- pause/resume
- current-project manual整理 only
- short recent activity log
- degraded read-only behavior when unavailable

The dual-visible agent decision is product-valid because it prevents invisible system automation. The risk is user confusion: users may treat `档案管理员` as a normal execution AI. Phase 4 must therefore include clear role boundaries in chat and project assignment surfaces.

## Technical Review

No blocking technical questions remain before checklist drafting, but implementation must be careful in these areas:

### Existing Dependencies

- Phase 1-3 Archive Room APIs and UI are complete and accepted.
- The project already has agent discovery, provider adapters, OpenClaw status/config surfaces, project task assignment, chat routing, and presence/status rendering.
- Phase 4 should reuse those existing mechanisms where possible rather than inventing a separate agent registry.

### Data And State

Phase 4 needs durable state for the archive manager lifecycle, likely under `VO_STATUS_DIR/archive-room/`, including:

- manager identity / agent id
- display name `档案管理员`
- provider kind / source
- status
- paused flag
- auto-created marker and timestamp
- last action / last error
- recent maintenance activity

The state must not replace the actual OpenClaw agent registry. It should record Archive Room's management view and references to the real agent.

### Auto-Creation

Auto-creation should be idempotent:

- If the agent already exists, do not create duplicates.
- If a previous auto-create partially succeeded, reconcile to one active manager.
- If creation fails, record the error and keep Archive Room read-only usable.

### UI And Controls

Archive Room should expose a global status bar. Project detail can show a lightweight paused notice. Controls should include pause, resume, and current-project manual整理.

The main office should make the agent visible as a real agent. Paused should be distinguishable from offline.

### Role Boundaries

The archive manager must be protected from normal project task assignment. This is a product rule, not only a UI preference; server-side validation should reject assignment where feasible.

Direct chat should be limited to archive-related topics. At minimum, Phase 4 needs clear feedback for out-of-scope usage. If robust classification is not available, start with conservative command/surface gating and explicit role prompt/guardrails.

### Prompt, Identity, Soul, And Output Contract

Phase 4 must treat the archive manager's prompt/persona files as product surface, not an implementation detail. The generated or maintained `agent.md`, identity, soul, and related prompt files should define:

- its name and role as `档案管理员`
- archive-only responsibility
- calm, precise, evidence-oriented work style
- non-execution-AI boundary
- behavior when asked out-of-scope questions
- strict operational output contract

The output contract is important because later phases depend on VO recognizing and rendering archive manager output. Phase 4 should therefore establish controlled output conventions now. Maintenance/action output should use stable labels or structured blocks, while free-form explanation should be limited to human-facing chat surfaces.

Open technical point for implementation: exact file names and provider-specific locations may depend on the existing OpenClaw agent profile format. This does not block checklist drafting, but implementation must discover and follow existing OpenClaw conventions instead of inventing incompatible files.

### Manual整理 Boundary

Manual整理 is included only for the current project. It can validate lifecycle and create/update lightweight archive summaries, but must not imply:

- all-project maintenance
- event subscriptions
- startup/daily schedules
- important-chat classification
- execution-AI reminder delivery

Those belong to later phases.

### Failure And Degraded Mode

Failure states must not block archive browsing. The expected degraded behavior is:

- status bar shows error
- recent activity records failure
- controls reflect unavailable action states
- existing project archives, onboarding packages, and artifacts remain readable

### Security And Safety

- The archive manager should not be deletable from Archive Room.
- It should not expose broader filesystem or raw provider history access beyond existing Archive Room boundaries.
- Manual整理 must respect existing source/artifact access rules.

## Review Conclusion

The requirement is ready for checklist drafting. There are no product blockers after clarification. The main engineering risks are duplicate OpenClaw agent creation, inconsistent paused/offline semantics, and leakage of the archive manager into normal task execution flows. These are addressable through explicit status records, idempotent creation, UI labels, and server-side validation where relevant.
