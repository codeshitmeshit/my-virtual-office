## Why

Manual project creation, Agent-authored creation, template instantiation, and recurring project instantiation currently assemble persisted Project and Task objects through separate code paths. Their defaults have drifted, so an Agent-created project can silently omit execution, workspace, column, checklist, or compatibility fields and become a legacy workflow project even though the user expected the Agent to execute it.

## What Changes

- Establish one canonical materialization contract for Project, Task, column, checklist, workspace, and Project Execution fields across manual, Agent-authored, template, and recurring creation paths.
- Require creation-source differences to be explicit overlays for activity, authoring audit/source, grants, idempotency, template/version, and recurrence metadata rather than independent object builders.
- Make every Agent-initiated project execution-capable by default without starting execution. The confirmed proposal must show whether execution is enabled, the executor, the reviewer, and whether creation will start execution.
- Reject execution-capable Agent creation when its executor or workspace prerequisites cannot be satisfied; never silently downgrade it to a legacy workflow project.
- Allow the user to explicitly request a tracking-only Agent-created project, which does not require executable-agent or executable-workspace prerequisites.
- Require recurring project authoring to distinguish “create instances only” from the separately confirmed “create and automatically execute each instance” behavior.
- Preserve existing transaction, authorization, idempotency, public API, and source-specific audit behavior, and do not automatically modify projects created before this change.

## Capabilities

### New Capabilities

- `project-materialization`: Defines canonical Project and Task creation semantics, source-specific overlays, Agent-created execution defaults and confirmation behavior, template and recurrence inheritance, failure behavior, and compatibility boundaries.

### Modified Capabilities

None.

## Impact

- Affects manual project/task commands, Agent direct creation, template instantiation, recurring instance creation, workspace preparation/projection, and their focused contract tests.
- Adds a focused project materialization service boundary while retaining the existing repositories, root compare-and-set operations, HTTP routes, and Agent authorization surfaces.
- Changes future Agent-created project behavior intentionally: execution is enabled by default, but ordinary creation remains unstarted unless automatic recurring execution was separately confirmed.
- Intentionally refines the still-active `add-agent-managed-vo-projects` recurrence rule: recurring instances remain unstarted by default, but a recurrence may start each instance only when that automatic execution behavior was separately shown and confirmed.
- Existing stored projects and previously created Agent projects are not migrated or automatically enabled.
