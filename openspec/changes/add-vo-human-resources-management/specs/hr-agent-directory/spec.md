## ADDED Requirements

### Requirement: Globally unique HR role
The system SHALL establish `HR` as one globally unique VO system Agent before HR-owned Agent discovery, introduction, reporting, or assessment work is attempted. Its stable provider ID SHALL remain `hr`, while its human-visible name SHALL be canonically rendered as uppercase `HR` across creation, lifecycle, directory, and management projections.

#### Scenario: Human Resources is opened without HR
- **WHEN** no valid HR provider Agent exists
- **THEN** the system SHALL reconcile the HR role through the shared system-Agent lifecycle
- **AND** HR-owned work SHALL begin only after HR is available

#### Scenario: HR is unavailable
- **WHEN** HR is paused, missing, or in error
- **THEN** existing Human Resources data SHALL remain readable
- **AND** new HR-authored introductions and assessments SHALL NOT be fabricated

#### Scenario: Provider or legacy state reports mixed-case HR name
- **WHEN** the stable HR identity is discovered or loaded with a display name such as `Hr` or `hr`
- **THEN** Human Resources projections and directory synchronization SHALL normalize the visible name to `HR`
- **AND** future HR creation requests SHALL use `HR` as the provider display name without changing stable ID `hr`

### Requirement: Authoritative Agent identity records
HR SHALL maintain one durable record per discoverable Agent keyed by stable AI ID, with the three core business fields of Agent name, Agent introduction, and AI ID plus status and provenance metadata needed for lifecycle decisions.

#### Scenario: New Agent is discovered
- **WHEN** HR encounters an AI ID absent from the directory
- **THEN** HR SHALL create one pending-introduction record containing its observed name, AI ID, availability, discovery time, and source

#### Scenario: Agent changes its name
- **WHEN** the same AI ID is discovered under a new name
- **THEN** HR SHALL update the current name while retaining reports, assessments, access history, and prior identity provenance under the same Agent record

#### Scenario: Duplicate discovery occurs
- **WHEN** multiple discovery sources report the same AI ID
- **THEN** HR SHALL merge the observation into the authoritative record rather than creating a duplicate person record

### Requirement: Directory coverage and HR self-exclusion
The directory SHALL cover discoverable system, project, and externally connected Agents, while HR itself SHALL be represented as a system role for discovery but excluded from ordinary daily-report and performance-assessment populations.

#### Scenario: Multiple Agent kinds are discovered
- **WHEN** VO reports eligible system, project, and external Agents
- **THEN** HR SHALL maintain records for each kind with its observed availability and source

#### Scenario: HR appears in provider discovery
- **WHEN** the provider lists HR among Agents
- **THEN** HR SHALL NOT schedule a daily-report request or performance assessment for itself

### Requirement: Inactive Agent history
HR SHALL preserve records for offline, disabled, deleted, or unreachable Agents, mark their current state, and stop new daily collection and assessment until they become eligible again.

#### Scenario: Active Agent becomes inactive
- **WHEN** discovery determines that an Agent is offline, disabled, deleted, or otherwise ineligible
- **THEN** HR SHALL retain its introduction, reports, assessments, and access history
- **AND** future daily cycles SHALL skip it with a traceable reason

#### Scenario: Inactive Agent returns
- **WHEN** the same AI ID becomes eligible again
- **THEN** HR SHALL reactivate the existing record and resume future HR workflows without losing history

### Requirement: HR-coordinated Agent introductions
HR SHALL ask a newly discovered or materially stale Agent to describe its identity and responsibilities, preserve the raw answer, and publish a concise introduction attributed to HR coordination without inventing an answer when the Agent does not respond.

#### Scenario: Agent answers the introduction request
- **WHEN** a pending Agent supplies a self-description
- **THEN** HR SHALL retain the original response, publish a concise introduction, and record source and update timestamps

#### Scenario: Agent does not answer
- **WHEN** the introduction request reaches its completion policy without a response
- **THEN** the record SHALL remain `introduction_pending`
- **AND** HR SHALL NOT generate an unsupported role description

#### Scenario: Agent role materially changes
- **WHEN** HR detects a material conflict between the published introduction and newer Agent-provided information
- **THEN** HR SHALL request clarification and preserve the previous introduction until a supported replacement is recorded

#### Scenario: Human requests completion of missing information
- **WHEN** the authenticated human invokes `补充信息`
- **THEN** HR SHALL asynchronously ask every currently available non-HR Agent whose introduction text is missing for its identity and responsibilities
- **AND** an Agent that already has introduction text, is unavailable, or is HR itself SHALL NOT receive a redundant request
- **AND** a previously received raw response awaiting HR summarization SHALL be summarized without asking that Agent again
- **AND** one Agent's failure or non-response SHALL NOT block other eligible introductions

### Requirement: Global Agent-directory skill
The system SHALL expose one repository-owned Agent-directory skill through the current VO instance's built-in `/skills` catalog. The skill SHALL direct every Provider to the controlled information-query capability for each visible Agent's name, concise introduction, AI ID, availability, and permitted work information, and SHALL NOT be copied or installed into individual Agent workspaces.

#### Scenario: Agent needs a collaborator
- **WHEN** an Agent invokes the directory skill
- **THEN** it SHALL receive the current safe roster needed to distinguish available Agent roles
- **AND** it SHALL NOT receive full reports, private evidence, or sensitive improvement feedback

#### Scenario: Any Provider discovers the built-in skill
- **WHEN** an OpenClaw, Hermes, Codex, Claude Code, or other connected Agent reads the current VO skill catalog
- **THEN** `/skills/vo-agent-directory/SKILL.md` SHALL be advertised as the same authoritative built-in skill
- **AND** no Provider-specific workspace installation SHALL be required to discover or read it

#### Scenario: Directory changes
- **WHEN** HR adds, reactivates, deactivates, or updates an Agent record
- **THEN** subsequent governed directory API queries SHALL return the current safe data without rewriting or redistributing the built-in `SKILL.md`

### Requirement: Directory provenance and repair
Every HR-authored directory mutation SHALL retain its source, actor, time, and result so that incomplete or conflicting Agent information can be diagnosed and repaired.

#### Scenario: Discovery or introduction processing fails
- **WHEN** one Agent's directory update fails
- **THEN** HR SHALL record the failure against that Agent without corrupting the previous valid record or blocking other Agent updates
