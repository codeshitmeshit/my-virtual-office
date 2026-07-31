## Purpose

Ensure migrated provider-visible prompt builders are invoked through their authoritative bridge-backed service modules, not through lingering `server.py` private compatibility wrappers.

## ADDED Requirements

### Requirement: Runtime prompt call sites use authoritative service entry points
The system SHALL route migrated provider-visible prompt construction through the owning bridge-backed prompt or service module at runtime. Runtime code MUST NOT call a legacy `server.py` private compatibility wrapper when an equivalent authoritative service function exists.

#### Scenario: Provider delivery prompt is built
- **WHEN** a provider bridge prepares a provider-visible message envelope
- **THEN** the runtime call site invokes the Agent platform prompt formatting path or its owning bridge service directly
- **AND** it does not depend on a `server.py` private compatibility wrapper for prompt construction

#### Scenario: Project execution prompt is built
- **WHEN** a project execution or review flow prepares a provider-visible prompt
- **THEN** the runtime call site invokes `services.project_execution_prompt_formatting` or the owning project service directly
- **AND** split service hydration does not replace that authoritative implementation with a legacy `server.py` prompt wrapper

#### Scenario: Workflow prompt is built
- **WHEN** a workflow task, review, rework, or project-context prompt is prepared
- **THEN** the runtime call site invokes `services.workflow_prompt_formatting` or the owning workflow service directly
- **AND** it does not route through an obsolete `server.py` private compatibility wrapper

#### Scenario: Archive context prompt is built
- **WHEN** archive context or archive refinement prompt content is prepared
- **THEN** the runtime call site invokes `services.archive_prompt_documents` or the owning archive service directly
- **AND** no duplicate legacy `server.py` prompt builder remains authoritative

### Requirement: Server prompt ownership is extracted when needed
The system SHALL avoid adding new prompt-wrapper ownership or orchestration logic to `app/server.py`. When removing or redirecting a compatibility wrapper requires non-trivial runtime coordination, that coordination SHOULD be moved into a focused service module instead of remaining in the monolith.

#### Scenario: Wrapper cleanup touches active runtime orchestration
- **WHEN** a `server.py` private prompt wrapper is still connected to active provider, project, workflow, archive, or agent creation runtime logic
- **THEN** the implementation evaluates whether that ownership can be moved to a focused service module in the same task
- **AND** it extracts the ownership when the extraction is scoped, behavior-preserving, and covered by focused tests

#### Scenario: Extraction would exceed safe scope
- **WHEN** moving runtime ownership out of `server.py` would require broad route, persistence, or provider lifecycle redesign beyond wrapper cleanup
- **THEN** the wrapper cleanup may leave a thin `server.py` delegate temporarily
- **AND** the change records the reason, risk, and later extraction condition

### Requirement: Obsolete private compatibility wrappers are removed
The system SHALL remove private compatibility wrappers after their runtime and test call sites have migrated. A wrapper MAY remain only when a current runtime boundary requires the historical private name and no direct service entry point can be safely substituted in the same change.

#### Scenario: Wrapper has no runtime callers
- **WHEN** static search and tests show a private compatibility wrapper has no runtime callers
- **THEN** the wrapper is removed
- **AND** tests are updated to exercise the authoritative service function instead of the removed wrapper

#### Scenario: Wrapper still has a required runtime caller
- **WHEN** a wrapper still has a required runtime caller that cannot be migrated safely in the current task
- **THEN** the wrapper remains a thin delegate with no prompt assembly logic
- **AND** the change records the caller, reason, risk, and removal condition

### Requirement: Tests assert service ownership
Tests that verify migrated prompt rendering SHALL target the owning bridge-backed service modules unless the behavior under test is specifically a public HTTP/provider integration path. Existing tests that currently import `server._*` private prompt wrappers MUST be migrated to the new authoritative functions when they are prompt-rendering tests rather than server integration tests.

#### Scenario: Prompt unit test is updated
- **WHEN** a test only validates prompt rendering, escaping, output schema placement, or section shape
- **THEN** it imports the focused prompt/service module directly
- **AND** it does not import `server._*` private compatibility wrappers

#### Scenario: Existing server-private prompt test is migrated
- **WHEN** an existing test currently calls a `server._*` private prompt wrapper only to inspect prompt text
- **THEN** the test is changed to call the authoritative prompt/service module function
- **AND** the wrapper is removed if no runtime integration path still requires it

#### Scenario: Integration test remains at server level
- **WHEN** a test validates a public route, provider dispatch integration, or compatibility hydration behavior
- **THEN** it MAY exercise `server.py`
- **AND** it still asserts that prompt construction is delegated to the authoritative bridge-backed path

### Requirement: Public behavior remains compatible
The wrapper removal SHALL preserve existing public behavior and provider-facing contracts.

#### Scenario: Regression suite runs
- **WHEN** focused provider delivery, project execution, workflow, archive, and prompt static coverage tests run after wrapper removal
- **THEN** public route behavior, provider payload shape, prompt output contracts, parsing expectations, and persisted data semantics remain compatible
- **AND** no business or support prompt module directly calls the low-level XML formatter
