# Task 1.2 Overlapping Change Contract Review

## Scope

Re-read the active or recently completed OpenSpec changes called out by `add-project-task-orchestration/design.md` and document the contracts that must be preserved or intentionally superseded while implementing the stage-pipeline project execution model.

Reviewed changes:

- `unify-project-materialization`
- `add-agent-managed-vo-projects`
- `add-project-workflow-chat-realtime-stream`

## Evidence Commands

```bash
npx --yes @fission-ai/openspec@latest status --change add-project-task-orchestration --json
npx --yes @fission-ai/openspec@latest instructions apply --change add-project-task-orchestration --json
sed -n '1,260p' openspec/changes/unify-project-materialization/proposal.md
sed -n '1,320p' openspec/changes/unify-project-materialization/design.md
sed -n '1,260p' openspec/changes/unify-project-materialization/tasks.md
sed -n '1,260p' openspec/changes/unify-project-materialization/specs/project-materialization/spec.md
sed -n '1,260p' openspec/changes/add-agent-managed-vo-projects/proposal.md
sed -n '1,340p' openspec/changes/add-agent-managed-vo-projects/design.md
sed -n '1,280p' openspec/changes/add-agent-managed-vo-projects/tasks.md
sed -n '1,260p' openspec/changes/add-agent-managed-vo-projects/specs/agent-project-authoring/spec.md
sed -n '1,260p' openspec/changes/add-project-workflow-chat-realtime-stream/proposal.md
sed -n '1,340p' openspec/changes/add-project-workflow-chat-realtime-stream/design.md
sed -n '1,280p' openspec/changes/add-project-workflow-chat-realtime-stream/tasks.md
sed -n '1,260p' openspec/changes/add-project-workflow-chat-realtime-stream/specs/project-workflow-chat-realtime/spec.md
```

## Overlap Summary

| Change | Current status observed | Overlap with stage orchestration | Required handling |
|---|---|---|---|
| `unify-project-materialization` | Tasks are complete and evidence says strict validation passed on 2026-07-23. | Owns canonical manual, Agent, template, recurrence materialization and currently requires old Project Execution defaults such as `projectExecutionStartMode`, `executionPolicy`, `projectExecutionFlowActive=false`, and `workflowActive=false`. | Treat its pure materialization boundary as the creation authority, but intentionally update its old execution-mode fields to the new `executionModel`, `orchestration`, and task `executionStage` contract in tasks 2.3-2.5. |
| `add-agent-managed-vo-projects` | Tasks are complete through direct-creation simplification and evidence confirms created projects do not start execution. | Owns Agent-safe direct creation, authoring skill contract, role validation, scoped grants, templates, recurrence, and maintenance. It currently states direct creation creates complete unstarted projects and uses old inactive flow fields. | Preserve Agent confirmation, idempotency, no-auto-execution, grant, template, recurrence, and maintenance semantics. Replace inactive old-flow persistence with draft stage-pipeline persistence without letting Agent creation start execution. |
| `add-project-workflow-chat-realtime-stream` | Tasks are not complete. The change is a future transport improvement and introduces no project persistence migration. | Owns Project Execution chat scope resolution, attempt-scoped stream isolation, canonical timeline events, and fallback polling. Stage orchestration introduces multiple active tasks, so chat scope can no longer rely on a singular `activeTaskId`. | Implement orchestration chat changes before or with realtime chat scope work: require explicit task scope for multi-active stages and keep realtime stream scope server-resolved, attempt-specific, and stale-scope safe. |

## Contract Details To Preserve

### Canonical materialization

- `app/services/project_materialization.py` is already the preferred creation boundary for manual, Agent, template, and recurrence creation.
- Source-specific overlays must stay overlays; orchestration fields belong in the canonical project/task base, not in separate builders.
- Materialization must remain pure: no repository calls, no HTTP response construction, no workspace side effects, and no execution launch.
- Existing creation transaction boundaries must remain separate:
  - manual project/task commands use project repository boundaries;
  - Agent direct creation uses root compare-and-set with grant/idempotency/template/recurrence data;
  - recurrence creates one deterministic project per occurrence.
- Existing projects remain readable; `add-project-task-orchestration` may remove pre-release legacy project data before release, but no implementation task may silently rewrite historical records as a side effect.

### Agent-authored projects

- Explicit conversation confirmation remains the authority for Agent direct creation.
- Direct creation must remain atomic and idempotent by requesting Agent plus idempotency key.
- Direct creation returns a one-time scoped grant secret only on first creation.
- Direct creation must not call Project Execution.
- Existing authoring safety properties remain:
  - loopback/no-browser-Origin Agent route;
  - registered Agent identity;
  - no management token exposure;
  - bounded JSON/task limits;
  - scoped maintenance grants;
  - strict/autonomous maintenance boundaries.
- New stage-pipeline fields must preserve the old product meaning "created but not started": `orchestration.state=draft`, no active run, and all initial tasks pending in valid stages.

### Workflow chat and realtime stream

- Snapshot endpoint remains authoritative for durable recovery.
- Stream scope is server-resolved from the selected project and attempt; the browser must not broaden Provider, Agent, conversation, task, or attempt identifiers.
- Stage orchestration must remove the singular `activeTaskId` assumption from project workflow chat before realtime stream scope relies on it.
- With multiple active tasks, project-level chat display may choose a recent active task only as a display fallback. Execution authority must require an explicit task scope.
- Stale attempt/project events must not update the visible chat after stage advancement, pause, or project switching.

## Implementation Order

The following order keeps the already-confirmed contracts intact while moving to stage orchestration:

1. **Baseline and characterization first**
   - Complete tasks 1.1-1.4 before changing behavior.
   - Add failing-before tests that freeze single/continuous, `executionOrder`, singular active-task, task-start, continuation, recovery, and schedule behavior.

2. **Add the new model beside the old fields**
   - Implement pure orchestration validation/projection in a new focused module.
   - Extend `MarkdownProjectStore` to round-trip `executionModel`, `orchestration`, task `executionStage`, `stageRunId`, and `orchestrationSkip`.
   - At this stage, preserve read compatibility for old records; do not delete old fields yet.

3. **Move creation authorities to the new contract together**
   - Update canonical materialization first because every creation source depends on it.
   - Update manual browser, Agent direct-create, versioned template, legacy template adaptation, and recurrence creation in the same phase.
   - Preserve "execution-capable but unstarted" by writing `stage_pipeline_v1` with draft orchestration, not old inactive flow flags.

4. **Migrate commands and lifecycle**
   - Introduce orchestration auto-save, start, reservation, dispatch, terminal reconciliation, skip, pause, resume, and recovery services.
   - Keep `app/server.py` and legacy service entry points thin; route work into focused orchestration modules.
   - Do not add new orchestration business logic to the large legacy files except transport delegation.

5. **Migrate chat, realtime, and projections before field removal**
   - Derive `activeTaskIds`, `activeTaskCount`, `currentStage`, `orchestrationState`, and `pauseReason`.
   - Update workflow chat to require explicit task scope when more than one current-stage task is active.
   - Reconcile this with `add-project-workflow-chat-realtime-stream` before implementing its SSE route or scope-change logic.

6. **Remove old authorities only after every caller migrates**
   - Remove persisted/client/API/test support for free, continuous, single-task, manual-next, singular active-task, and `executionOrder` eligibility.
   - Keep unrelated `autoMode` and unrelated frontend `activeAgent` queue uses out of the removal blast radius.
   - Add static checks proving no marked-project path can restore old progression behavior.

7. **Run real acceptance last**
   - After storage, lifecycle, frontend, and AI-facing authoring paths are updated, run browser acceptance and real AI project creation smoke tests.
   - Re-run strict OpenSpec validation and attach focused test evidence before final test-result confirmation.

## Open Coordination Notes

- `unify-project-materialization` and `add-agent-managed-vo-projects` used old inactive fields to express "does not auto-start." The new equivalent is draft orchestration with no `currentRunId`; later tasks must update tests and docs to avoid reintroducing old fields as hidden compatibility switches.
- `add-project-workflow-chat-realtime-stream` has no direct old-field hits in the task 1.1 `rg` inventory, but its server-resolved scope depends on current Project Execution scope. It must be considered affected by any change from one active task to multiple current-stage active tasks.
- The final implementation should review AI-facing surfaces again after coding, especially `vo-project-authoring`, Agent direct-create payloads, template snapshots, recurrence definitions, and maintenance APIs.
