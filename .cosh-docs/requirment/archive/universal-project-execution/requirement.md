# 通用项目执行 Universal Project Execution

## Background

The original universal harness roadmap described 通用项目执行 as universal projects and automations. The implemented roadmap diverged when Codex live activity controls focused on Codex live activity, approvals, input, cancellation, recovery, and reasoning summaries instead of adding Claude Code and general project binding.

Virtual Office already has a project board and an OpenClaw-oriented workflow engine. It can dispatch to OpenClaw, Hermes, and Codex through provider-specific branches, but projects do not yet own a validated workspace binding, execution and review are not separated, and a successful agent review can move a task directly to Done without explicit user acceptance.

通用项目执行 is therefore corrected to establish a reliable universal project execution loop before universal scheduling is added.

## Target user

- A self-hosted Virtual Office user managing local projects with OpenClaw, Hermes, and Codex collaborators.
- The user is the final acceptance authority for every completed task.

## Product goal

Make a project a provider-neutral office object that binds to one local directory or Git repository and supports a traceable task lifecycle across the existing OpenClaw, Hermes, and Codex agents.

The required lifecycle is:

`backlog -> executing -> reviewer pre-acceptance -> rework or blocked -> awaiting user acceptance -> done`

## Delivery and acceptance split

通用项目执行 is delivered and accepted in two sequential increments.

### 执行底座: Universal project execution foundation

- Add project workspace binding, project default roles, and task-level role overrides.
- Let the user explicitly start one selected task with an OpenClaw, Hermes, or Codex executor.
- Enforce workspace validation, dirty-worktree confirmation, one active task per project, durable attempts, cancellation, failure handling, evidence capture, refresh recovery, and restart reconciliation.
- Configure and validate the independent reviewer identity, but do not run automated review yet.
- A successfully executed task stops at `execution_complete`, waiting for 独立审查与最终验收 review. It cannot use the legacy self-review path or enter Done.

执行底座 is independently acceptable when universal project binding and execution are reliable across the three existing providers and all completion shortcuts are closed.

### 独立审查与最终验收: Independent review and final acceptance

- Send the 执行底座 evidence bundle to an independent read-only Reviewer.
- Add structured reviewer outcomes, up to three automatic rework cycles, blocked escalation, final acceptance evidence, and explicit user acceptance actions.
- Complete the full lifecycle through Done only after a valid Reviewer pass and explicit user acceptance.

独立审查与最终验收 is independently accepted after 执行底座 and completes the overall 通用项目执行 requirement.

## In scope

1. Every project must bind to an accessible local directory or Git repository.
2. A project defines a default executor and a default reviewer; an individual task may override either role.
3. OpenClaw, Hermes, and Codex agents may act as executors or reviewers.
4. The reviewer must be a different agent from the executor.
5. Reviewer pre-acceptance evaluates the task checklist, changed-file evidence, test evidence, execution summary, and prior rework history.
6. Reviewer results are structured as `pass`, `needs_more_work`, or `blocked`, with evidence and rationale.
7. A failed review automatically returns to the original executor for rework, up to three rework cycles.
8. A blocked or indeterminate review stops automation and waits for the user.
9. After reviewer approval, every task waits for explicit user acceptance before entering Done.
10. User acceptance actions are `accept`, `reject_and_rework`, and `mark_blocked`.
11. User rejection returns the task to the executor and requires a new independent reviewer pass.
12. Only one task may execute per project at a time; the user manually selects the task to start.
13. Invalid or inaccessible project bindings prevent task execution.
14. A dirty Git worktree requires explicit user confirmation for that execution attempt.
15. Execution failure or cancellation moves the task to blocked while retaining all activity and modification evidence.
16. Existing projects and tasks are upgraded compatibly with defaults rather than discarded.
17. User acceptance changes task state only; it does not commit or push Git changes.

## Final acceptance evidence

The user acceptance surface must show:

- task checklist and per-item reviewer status;
- executor summary;
- changed-file evidence;
- test commands and results;
- reviewer conclusion and rationale;
- all rework cycles and user feedback;
- warnings for dirty-worktree execution, cancellation, failure, truncation, or incomplete evidence.

## Constraints

- The reviewer is read-only and must not modify project files.
- Reviewer isolation must be enforced by the Office runtime, not only requested in a prompt.
- The executor and reviewer identities must remain stable and auditable for each attempt.
- A task cannot reach Done through board drag, workflow auto-mode, API shortcuts, or reviewer output alone.
- Existing Codex live bridge and Codex live activity controls Codex conversation/activity behavior must remain available.
- Existing OpenClaw and Hermes chat behavior must not regress.

## Out of scope

- Claude Code provider integration.
- Office-owned schedules, universal Cron, or recurring automation.
- Automatic task selection or continuous backlog execution.
- Multi-agent autonomous decomposition or orchestration.
- Parallel tasks within one project.
- Worktree isolation and concurrent branch management.
- Automatic Git commit, merge, push, deployment, or rollback.
- Reviewer repair of implementation defects.

## Deferred roadmap

- A later phase must add per-project concurrent task execution with isolated worktrees and explicit merge/conflict handling.
- Universal automations and office-owned scheduling move to a later phase after the 通用项目执行 project execution contract is stable.

## Success criteria

通用项目执行 succeeds when a user can bind a project to a valid local workspace, select a task, assign distinct executor and reviewer agents from the existing providers, observe execution and evidence, receive up to three controlled rework cycles, and explicitly accept the task into Done. All abnormal paths remain recoverable and auditable, and no provider-specific session convention is treated as the canonical project state.
