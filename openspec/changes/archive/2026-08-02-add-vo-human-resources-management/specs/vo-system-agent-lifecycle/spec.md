## ADDED Requirements

### Requirement: Role-configured VO system Agent lifecycle
The system SHALL manage each VO-level system Agent through one reusable lifecycle boundary configured with a stable Agent ID, display identity, profile definition, provider requirements, assignment policy, meeting policy, and degraded-state policy, without embedding Archive Room or Human Resources business behavior in that boundary.

#### Scenario: A future VO system role is registered
- **WHEN** a caller supplies a valid system-Agent role definition
- **THEN** the lifecycle boundary SHALL apply the shared discovery, creation, profile, state, protection, and activity rules
- **AND** role-specific business behavior SHALL remain owned by the calling domain

#### Scenario: Role configurations coexist
- **WHEN** the archive manager and HR are both registered
- **THEN** each SHALL retain its own stable ID, profile, state, activity, assignment policy, and meeting policy
- **AND** an operation for one role SHALL NOT mutate the other role

### Requirement: Idempotent global Agent creation
The lifecycle boundary MUST discover an existing role instance before creation and MUST create at most one effective instance for each globally unique VO system role across repeated requests, concurrent requests, and service restarts.

#### Scenario: Required Agent is missing
- **WHEN** a lifecycle check finds no provider Agent matching the configured stable role
- **THEN** the system SHALL request creation once, synchronize the required profile, and persist the resulting Agent identity and auto-created status

#### Scenario: Creation is requested repeatedly
- **WHEN** repeated or concurrent lifecycle checks target the same system role
- **THEN** the system SHALL converge on one effective provider Agent and one authoritative lifecycle record
- **AND** duplicate successful instances SHALL NOT be exposed as valid role owners

#### Scenario: Service restarts after creation
- **WHEN** VO restarts after a system Agent was created
- **THEN** the lifecycle check SHALL rediscover and reuse that Agent rather than creating another instance

### Requirement: Versioned profile synchronization
The lifecycle boundary SHALL synchronize each system Agent's required profile files and communication skill from its role-specific versioned definition, repair missing or stale content, and report partial provider success as an error requiring repair.

#### Scenario: Existing profile is current
- **WHEN** the provider Agent and all required profile content match the configured version
- **THEN** lifecycle reconciliation SHALL retain the profile without reporting an update

#### Scenario: Profile is missing or stale
- **WHEN** a required profile file or communication skill is absent or older than the configured version
- **THEN** reconciliation SHALL repair it and record a profile activity with the resulting version

#### Scenario: Agent creation succeeds but profile synchronization fails
- **WHEN** the provider creates the Agent but a required profile or communication skill cannot be synchronized
- **THEN** the lifecycle state SHALL be `error` with the failure reason and Agent identity retained
- **AND** a later reconciliation SHALL be able to repair the partial state without creating a duplicate Agent

### Requirement: Observable lifecycle and pause state
Each system Agent SHALL expose an authoritative lifecycle view containing its role, provider identity, creation origin, current state, pause flag, last error, relevant timestamps, profile version, and bounded recent activity.

#### Scenario: User pauses a system Agent
- **WHEN** an authorized human pauses a running system Agent
- **THEN** its state SHALL become paused and new role-specific automatic work SHALL be skipped with a recorded reason
- **AND** its existing domain data SHALL remain readable

#### Scenario: User resumes a system Agent
- **WHEN** an authorized human resumes a paused system Agent
- **THEN** reconciliation SHALL verify the provider Agent and profile before returning the role to an available state

### Requirement: System-role protection policies
The system SHALL enforce each role's declared eligibility instead of treating all system Agents identically, and SHALL protect all configured VO system Agents from ordinary project assignment and unsupported deletion.

#### Scenario: A project assigns HR or the archive manager
- **WHEN** a project or task attempts to assign either system Agent as executor, reviewer, assignee, or project default Agent
- **THEN** the operation SHALL be rejected with a stable system-role error and no partial mutation

#### Scenario: A meeting selects a system Agent
- **WHEN** meeting eligibility is evaluated
- **THEN** the archive manager SHALL remain ineligible and HR SHALL be eligible according to their distinct role policies

#### Scenario: Caller attempts unsupported deletion
- **WHEN** a caller attempts to delete HR or the archive manager through an ordinary Agent or domain control surface
- **THEN** the system SHALL reject the operation and direct the caller to the supported pause control

### Requirement: Failure isolation and degraded reads
Provider discovery, creation, profile, or control failures MUST NOT make the owning domain or unrelated VO workflows unavailable, and each domain SHALL be able to present existing data with a clear degraded lifecycle state.

#### Scenario: Provider is unavailable
- **WHEN** a provider call fails or times out during lifecycle reconciliation
- **THEN** the lifecycle record SHALL expose an error without discarding the last known Agent identity or domain data
- **AND** Archive Room, Human Resources, projects, and meetings SHALL retain their otherwise available behavior

### Requirement: Archive manager compatibility during extraction
Migration to the shared lifecycle boundary MUST preserve the archive manager's existing ID, profile, automatic creation, status, pause/resume, activity, assignment exclusion, meeting exclusion, deletion protection, maintenance behavior, and degraded-read behavior.

#### Scenario: Existing archive manager is reconciled after migration
- **WHEN** VO starts with an archive manager created by the previous implementation
- **THEN** the shared lifecycle SHALL reuse and, if needed, repair that Agent without changing its public identity or Archive Room state

#### Scenario: Archive Room regression suite runs
- **WHEN** lifecycle extraction is verified locally
- **THEN** all applicable pre-change archive-manager characterization and Archive Room regression scenarios SHALL pass without relaxed assertions

### Requirement: Mandatory lifecycle verification gates
The lifecycle change SHALL NOT be considered verified until deterministic local unit and regression tests pass and the integrated archive-manager and HR paths are exercised on a development machine with a real OpenClaw environment.

#### Scenario: Local environment has no real OpenClaw
- **WHEN** lifecycle behavior is tested locally
- **THEN** tests SHALL use injected deterministic provider fakes for success, failure, timeout, partial success, duplicate, concurrent, pause, resume, repair, and restart cases
- **AND** the test suite SHALL NOT require a live OpenClaw service

#### Scenario: Development-machine acceptance is performed
- **WHEN** implementation is otherwise complete
- **THEN** the verification evidence SHALL include real OpenClaw creation, rediscovery, restart, profile repair, pause/resume, role isolation, meeting eligibility, assignment protection, provider failure, and archive-manager regression results
- **AND** missing or failed development-machine evidence SHALL block test-result confirmation
