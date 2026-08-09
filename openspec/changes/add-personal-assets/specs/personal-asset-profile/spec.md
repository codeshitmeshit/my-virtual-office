## ADDED Requirements

### Requirement: Personal asset profile supports built-in and extensible information
The system SHALL provide one authoritative personal asset profile for the authenticated VO owner. The profile SHALL support current investment or fund focus, occupation, interests, chat preferences, VO focus direction, office goals, and owner-defined additional entries without requiring a product release for each new category.

#### Scenario: Owner creates built-in profile information
- **WHEN** the owner adds occupation, interests, chat preferences, VO direction, office goals, or current investment focus
- **THEN** the system persists each item under the owner's personal asset profile
- **AND** the saved values remain available after service restart

#### Scenario: Owner appends an unmodeled item
- **WHEN** the owner adds a new information item that is not covered by a built-in category
- **THEN** the system persists it as an extensible personal asset entry with an owner-visible label and value
- **AND** existing entries remain unchanged

### Requirement: Owner controls the personal asset lifecycle
The system SHALL allow the owner to create, view, update, append, and delete personal asset entries. The system MUST preserve unrelated entries during partial updates and MUST reject malformed or conflicting writes without silently replacing the authoritative profile.

#### Scenario: Owner updates one entry
- **WHEN** the owner edits one saved personal asset entry
- **THEN** the system persists the new value for that entry
- **AND** all unrelated entries retain their previous values

#### Scenario: Owner deletes an entry
- **WHEN** the owner confirms deletion of a personal asset entry
- **THEN** the entry is removed from the active profile
- **AND** the deletion does not remove other entries

#### Scenario: Invalid write is submitted
- **WHEN** a create or update request violates the accepted profile contract or targets a stale conflicting version
- **THEN** the system rejects the write with a stable error
- **AND** the last valid profile remains authoritative

### Requirement: Personal asset UI is limited to management and confirmation
The VO control panel SHALL provide a personal asset entry and SHALL present only the profile overview, create/edit experience, and pending-suggestion confirmation experience. The personal asset UI MUST NOT include a guided onboarding page or a sensitive-read authorization page.

#### Scenario: Owner opens personal assets
- **WHEN** the owner activates the personal asset navigation entry
- **THEN** the system displays the persisted profile overview using the established VO visual language
- **AND** the owner can enter the create/edit experience from that page

#### Scenario: Suggested information awaits confirmation
- **WHEN** an Agent or supported workflow proposes a change to the owner's personal assets
- **THEN** the proposal appears as a pending suggestion
- **AND** it does not change the authoritative profile until the owner accepts it

#### Scenario: Owner looks for onboarding or authorization in personal assets
- **WHEN** the owner uses the personal asset pages
- **THEN** no page-level onboarding wizard is presented
- **AND** no sensitive Agent-read authorization controls are presented

### Requirement: Personal asset entries expose an owner-managed sensitivity classification
The system SHALL allow each personal asset entry to carry an owner-visible sensitivity classification used by Agent access policy. Changing the classification SHALL NOT itself grant an Agent access or create a HUMAN DECISIONS result.

#### Scenario: Owner marks an entry as sensitive
- **WHEN** the owner changes an entry classification to sensitive
- **THEN** subsequent Agent reads of that entry require the sensitive-access decision path
- **AND** the personal asset page does not create or store an authorization decision

