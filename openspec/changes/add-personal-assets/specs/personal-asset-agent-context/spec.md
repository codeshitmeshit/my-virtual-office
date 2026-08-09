## ADDED Requirements

### Requirement: Agents read personal assets only through a controlled task-scoped capability
The system SHALL provide a controlled capability for an authorized Agent to request only the personal asset entries relevant to its current VO task. The system MUST NOT inject the complete personal asset profile into every Agent prompt by default.

#### Scenario: Agent requests relevant non-sensitive context
- **WHEN** an authorized Agent identifies a concrete task need for selected non-sensitive personal asset entries
- **THEN** the capability returns only the permitted entries relevant to that request
- **AND** unrelated profile entries are omitted

#### Scenario: Agent requests the full profile without a task need
- **WHEN** an Agent requests all personal assets without a concrete task-scoped purpose
- **THEN** the system rejects or narrows the request
- **AND** it does not disclose the complete profile by default

### Requirement: Sensitive Agent reads are decided by HUMAN DECISIONS
The system SHALL route an Agent request for sensitive personal asset information to the existing HUMAN DECISIONS request lifecycle. Personal assets MUST NOT maintain a second authorization state, authorization screen, or independent decision history.

#### Scenario: Sensitive read requires a decision
- **WHEN** an Agent requests one or more entries classified as sensitive
- **THEN** the system creates a task-scoped HUMAN DECISIONS request containing the requested scope, purpose, requesting Agent, and expiry semantics
- **AND** no sensitive value is disclosed before an approving terminal decision

#### Scenario: Sensitive read is approved
- **WHEN** HUMAN DECISIONS records an approving terminal result for the active request
- **THEN** the capability discloses only the approved scope to the requesting task
- **AND** the approval does not become an unrestricted standing grant

#### Scenario: Sensitive read is rejected or expires
- **WHEN** HUMAN DECISIONS rejects or expires the request
- **THEN** the system discloses no sensitive value
- **AND** the affected Agent continues without relying on that information or reports that the task cannot safely continue

### Requirement: Agent access is auditable and disclosure-safe
The system SHALL create a durable, sanitized usage record for each successful Agent disclosure and each sensitive-access decision result. Records MUST identify the requesting Agent, task context, disclosed entry scope, timestamp, and outcome without copying secrets or full sensitive values.

#### Scenario: Agent receives personal asset context
- **WHEN** the system successfully discloses personal asset entries to an Agent
- **THEN** exactly one corresponding usage record is persisted
- **AND** the record describes scope rather than duplicating the disclosed values

#### Scenario: Sensitive request is denied
- **WHEN** a sensitive request reaches a rejecting or expired terminal result
- **THEN** the decision outcome is traceable through HUMAN DECISIONS
- **AND** it is not recorded as a successful disclosure

### Requirement: Agents may use approved personal assets as decision context
The system SHALL allow an Agent to use lawfully disclosed personal asset context when evaluating project plans, recommendations, or VO priorities, while preserving the decision and access boundaries of the source entries.

#### Scenario: Agent evaluates a project recommendation
- **WHEN** an Agent has received relevant approved personal asset context for the current task
- **THEN** it may use that context to rank or explain project options
- **AND** it does not expose the underlying personal values in unrelated outputs

