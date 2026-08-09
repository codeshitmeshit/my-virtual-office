# project-task-orchestration Specification

## Purpose
TBD - created by archiving change add-project-task-orchestration. Update Purpose after archive.
## Requirements
### Requirement: Marked new projects use mandatory orchestration
Every project created under the new project contract SHALL persist an internal orchestration marker in its canonical Markdown project frontmatter, and every task in such a project MUST belong to exactly one execution stage before the project can start. The marker SHALL NOT require a user-visible "new project" or "orchestration project" badge.

#### Scenario: A new project is created
- **WHEN** any supported project-creation path materializes a project under the new contract
- **THEN** the persisted canonical Markdown project record SHALL contain the internal orchestration marker
- **AND** the project SHALL use stage orchestration rather than free or single-task progression

#### Scenario: A marked project contains an unassigned task
- **WHEN** a user attempts to start a marked project while any task lacks a valid execution stage
- **THEN** the project SHALL remain unstarted
- **AND** the user SHALL be shown which tasks still require orchestration

#### Scenario: Legacy project data is prepared for release
- **WHEN** the orchestration-only release is prepared
- **THEN** legacy unmarked projects MAY be removed before deployment
- **AND** the product SHALL NOT require migration of those projects into the new contract

### Requirement: Figma-aligned orchestration workspace
The project-management orchestration workspace MUST match the approved Figma design represented by full-screen frame `147:2` and modal `148:3` for typography, font sizes, dimensions, spacing, colors, borders, radii, shadows, task-state styling, canvas composition, and controls, except that the bottom "保存编排" action SHALL be absent.

#### Scenario: Orchestration modal is rendered
- **WHEN** an authorized user opens orchestration for a project
- **THEN** the modal, header, explanatory notice, controls, pipeline canvas, task cards, parallel groups, and directional relationships SHALL match the approved Figma specifications
- **AND** the dimmed project page SHALL remain visible behind the modal as shown in frame `147:2`

#### Scenario: Visual acceptance is performed
- **WHEN** the implementation is rendered at the Figma reference viewport
- **THEN** visual verification SHALL compare it with frames `147:2` and `148:3`
- **AND** differences in the approved fonts, font sizes, geometry, spacing, colors, borders, task-state presentation, or canvas layout SHALL fail acceptance unless explicitly specified by this change

#### Scenario: Modal footer is rendered
- **WHEN** the orchestration modal is open
- **THEN** no "保存编排" button SHALL be shown
- **AND** removing that action SHALL NOT add an implicit project-start action

### Requirement: Orchestration edits auto-save
Accepted orchestration edits SHALL persist automatically without a save action, while project start SHALL remain a separate explicit operation.

#### Scenario: A task is moved between stages
- **WHEN** an authorized user completes a valid drag or stage reassignment before project start
- **THEN** the new orchestration SHALL be persisted automatically
- **AND** the project SHALL remain unstarted

#### Scenario: A drag edit is accepted locally
- **WHEN** an authorized user completes a valid drag before project start
- **THEN** the orchestration workspace SHALL update the visible task arrangement immediately
- **AND** persistence SHALL continue in the background without requiring a manual save action

#### Scenario: Persistence rejects an edit
- **WHEN** an orchestration edit cannot be persisted
- **THEN** the interface SHALL NOT present the rejected arrangement as durably saved
- **AND** project start SHALL remain unavailable until the displayed arrangement and persisted arrangement agree

### Requirement: Stage numbering remains complete and contiguous
Every task in an editable marked project MUST have exactly one positive execution-stage number, and the set of occupied stage numbers SHALL remain contiguous beginning at 1.

#### Scenario: A new task is added
- **WHEN** a task is created from the orchestration workspace
- **THEN** it SHALL default to one stage after the current maximum occupied stage
- **AND** the user MAY move it to another valid stage before project start

#### Scenario: The last task leaves a stage
- **WHEN** moving or deleting a task empties an execution stage
- **THEN** that empty stage SHALL be removed
- **AND** every later stage SHALL be renumbered to preserve a contiguous sequence

#### Scenario: Multiple tasks share a stage
- **WHEN** two or more tasks have the same execution-stage number
- **THEN** the orchestration workspace SHALL represent them as a parallel group
- **AND** their task identities and ordering within the group SHALL remain stable across persistence and reload

#### Scenario: A task is dropped on the ordinary canvas
- **WHEN** a user drops a task on the blank pipeline canvas outside the explicit new-stage target
- **THEN** the task SHALL be assigned to the nearest existing stage
- **AND** the drop SHALL NOT create a new stage

#### Scenario: A task is dropped on the new-stage target
- **WHEN** a user drops a task onto the dashed new-stage target at the right edge of the pipeline
- **THEN** the task SHALL move to one stage after the current maximum occupied stage
- **AND** the visible stage numbers SHALL remain complete and contiguous after normalization

### Requirement: Explicit project start locks orchestration
Starting a project SHALL be an explicit project-level action separate from orchestration editing. A successful start SHALL lock the active pipeline against ordinary edits and SHALL begin stage 1.

#### Scenario: An owner starts a valid project
- **WHEN** an authorized project owner or manager explicitly starts a marked project whose tasks form a valid pipeline
- **THEN** the project SHALL enter execution
- **AND** ordinary task creation, deletion, and stage reassignment SHALL be locked
- **AND** every task in stage 1 SHALL be dispatched according to its supported executor semantics

#### Scenario: A user only edits orchestration
- **WHEN** an authorized user creates or rearranges tasks but does not invoke project start
- **THEN** the edits SHALL auto-save
- **AND** no task SHALL start because of those edits

### Requirement: Stages execute in order and tasks within a stage execute in parallel
The system SHALL make tasks eligible by execution stage. All dispatchable tasks in the current stage SHALL be started or dispatched together, and no task in a later stage SHALL start before every task in the current stage has reached an accepted terminal outcome.

#### Scenario: A stage becomes active
- **WHEN** the project starts or the preceding stage reaches accepted terminal outcomes
- **THEN** every dispatchable task in the new current stage SHALL be started or dispatched
- **AND** later-stage tasks SHALL remain ineligible

#### Scenario: One parallel task remains unfinished
- **WHEN** at least one task in the current stage has not completed or received an approved skip
- **THEN** the next stage SHALL remain locked

#### Scenario: A non-final stage finishes
- **WHEN** every task in the current stage completes or receives an approved skip
- **THEN** the next numbered stage SHALL become current automatically
- **AND** its tasks SHALL be started or dispatched without a per-task or per-stage manual-advance action

### Requirement: Exceptions pause advancement and skips require approval
A failed or blocked task SHALL pause advancement beyond its stage. The task's responsible actor MAY request a skip, but only the project owner or a manager with orchestration authority SHALL approve the skip as an accepted terminal outcome.

#### Scenario: A task fails or becomes blocked
- **WHEN** a current-stage task enters a failed or blocked state
- **THEN** automatic advancement SHALL pause at that stage
- **AND** no later-stage task SHALL start

#### Scenario: A responsible actor requests a skip
- **WHEN** the responsible actor submits a skip request with the task and reason
- **THEN** the task SHALL remain non-terminal for stage advancement until an authorized project owner or manager decides the request

#### Scenario: A skip is approved
- **WHEN** an authorized project owner or manager approves a pending skip request
- **THEN** the task SHALL count as an accepted terminal outcome for its stage
- **AND** advancement SHALL resume only when every other task in that stage also has an accepted terminal outcome

#### Scenario: A skip is rejected
- **WHEN** an authorized project owner or manager rejects a skip request
- **THEN** the task SHALL remain unresolved
- **AND** the pipeline SHALL remain paused at that stage

### Requirement: Paused projects can be re-orchestrated without rewriting completed history
An authorized project owner or manager SHALL be able to pause an executing project for re-orchestration. Active unfinished executions SHALL be terminated and returned to pending for a future from-scratch execution; completed tasks and their original stages SHALL remain immutable.

#### Scenario: Re-orchestration is requested during execution
- **WHEN** an authorized project owner or manager confirms pause and re-orchestration
- **THEN** every active unfinished task SHALL have its current execution terminated
- **AND** those tasks SHALL return to pending without treating partial progress as completion
- **AND** no new task SHALL be dispatched until the revised pipeline is explicitly resumed

#### Scenario: The revised pipeline is edited
- **WHEN** a paused project contains completed and unfinished tasks
- **THEN** completed tasks and their original stage numbers SHALL remain locked
- **AND** only unfinished tasks SHALL be movable
- **AND** unfinished stage numbers SHALL form a contiguous sequence after the last completed stage

#### Scenario: The revised pipeline resumes
- **WHEN** an authorized user resumes a valid revised pipeline
- **THEN** unfinished tasks in its first remaining stage SHALL execute from the beginning
- **AND** preserved execution history SHALL continue to show the terminated earlier attempts

### Requirement: Final stage completion completes the project
The project SHALL become completed automatically when every task in its final stage, and therefore every task in the pipeline, has completed or received an approved skip. Any required human acceptance SHALL be represented as an explicit task in the pipeline.

#### Scenario: The final stage reaches accepted terminal outcomes
- **WHEN** every final-stage task completes or receives an approved skip
- **THEN** the project SHALL automatically enter its completed state
- **AND** no separate project-completion or stage-advance action SHALL be required

#### Scenario: Human acceptance is required
- **WHEN** the project requires a human acceptance decision before completion
- **THEN** that acceptance SHALL be modeled as a task in an execution stage
- **AND** the project SHALL not complete until that task has an accepted terminal outcome

### Requirement: Task final results are recorded as default artifacts
Every task that reaches an accepted terminal outcome SHALL expose a default final-result artifact named `TASK_FINAL_RESULT.md` and a compact task-record index pointing to that artifact.

#### Scenario: A task completes without an explicit file deliverable
- **WHEN** a marked project task reaches an accepted terminal outcome
- **THEN** the task SHALL have `finalResult.status` set to `available`
- **AND** the canonical task directory SHALL contain `TASK_FINAL_RESULT.md`
- **AND** the Markdown file SHALL include the final conclusion, completed work, changed files or artifacts, verification, risks, and later-stage notes

#### Scenario: A task is skipped through orchestration approval
- **WHEN** an orchestration skip is approved as the task's accepted terminal outcome
- **THEN** the task SHALL have `finalResult.status` set to `skipped`
- **AND** downstream handoff indexes SHALL identify the task as skipped rather than completed

#### Scenario: Canonical project storage is rewritten
- **WHEN** the Markdown project store rewrites a project that contains task `finalResult` data
- **THEN** the store SHALL preserve the task-record final-result index
- **AND** regenerate `TASK_FINAL_RESULT.md` in the task's canonical directory

### Requirement: Later stages can discover previous-stage results
When a later orchestration stage starts, each task prompt SHALL include a compact index of prior task final results so the agent can discover upstream conclusions and artifacts without guessing storage locations.

#### Scenario: Stage 3 starts after stages 1 and 2 completed
- **WHEN** a stage 3 task execution prompt is built
- **THEN** the prompt SHALL include result indexes for stages 1 and 2
- **AND** each index item SHALL include task title, stage, status, summary, and `TASK_FINAL_RESULT.md` path

#### Scenario: A later-stage task depends on earlier work
- **WHEN** the later-stage agent needs context from an earlier task
- **THEN** the prompt SHALL instruct the agent to inspect the referenced result Markdown or artifact refs before relying on that prior work
- **AND** the system SHALL NOT inline every prior result body by default

