## ADDED Requirements

### Requirement: Personal asset onboarding is manually triggered as a Skill
The system SHALL provide a personal asset onboarding Skill that starts only when the owner manually invokes it. The system MUST NOT require or provide a dedicated page-level onboarding wizard.

#### Scenario: Owner manually invokes onboarding
- **WHEN** the owner explicitly invokes the personal asset onboarding Skill
- **THEN** the Skill starts a conversational collection flow
- **AND** the personal asset UI remains a management surface rather than becoming the conversation host

#### Scenario: Owner opens personal assets without invoking the Skill
- **WHEN** the owner opens the personal asset page
- **THEN** the system shows persisted information and management actions
- **AND** it does not automatically start onboarding questions

### Requirement: Onboarding supports progressive collection, skipping, and later continuation
The Skill SHALL progressively collect basic information, occupation and direction, interests, chat preferences, goals, and optional sensitive items. The owner SHALL be able to answer, skip, correct, or stop at any step and later invoke the Skill again to continue or append information.

#### Scenario: Owner skips a question
- **WHEN** the owner chooses not to answer the current onboarding question
- **THEN** the Skill continues without inventing a value
- **AND** the skipped field remains available for a later invocation

#### Scenario: Owner stops partway through onboarding
- **WHEN** the owner ends the Skill before all topics are covered
- **THEN** already confirmed entries remain persistable
- **AND** a later manual invocation can continue without requiring a new page workflow

#### Scenario: Owner appends information later
- **WHEN** the owner invokes the Skill after an initial profile exists and provides a new item
- **THEN** the Skill proposes an append or targeted update
- **AND** it preserves unrelated profile entries

#### Scenario: Skill discovers existing profile scope
- **WHEN** the owner manually invokes the Skill to continue or append information
- **THEN** the Skill may read a value-free authoritative profile outline containing revision and entry metadata
- **AND** sensitive labels are redacted and no entry value or management credential is returned

### Requirement: Skill persistence requires explicit owner confirmation
The Skill SHALL summarize proposed creates, updates, sensitivity classifications, and skips before changing the authoritative personal asset profile. It MUST persist only the entries the owner explicitly confirms.

#### Scenario: Owner confirms proposed entries
- **WHEN** the Skill presents a summary and the owner confirms selected entries
- **THEN** the confirmed entries are written through the authoritative personal asset persistence capability
- **AND** the Skill reports the resulting saved scope

#### Scenario: Owner corrects the summary
- **WHEN** the owner changes a proposed value or sensitivity classification before confirmation
- **THEN** the Skill updates the proposal and asks for confirmation again
- **AND** no superseded value is persisted

#### Scenario: Owner cancels confirmation
- **WHEN** the owner declines the proposed changes
- **THEN** the authoritative profile remains unchanged

### Requirement: Onboarding does not grant Agent sensitive access
The Skill SHALL allow the owner to classify an entry as sensitive during onboarding, but it MUST NOT create a standing Agent authorization or bypass HUMAN DECISIONS.

#### Scenario: Skill saves a sensitive entry
- **WHEN** the owner confirms an entry classified as sensitive
- **THEN** the entry is persisted with that classification
- **AND** any later Agent read still follows the HUMAN DECISIONS sensitive-access path
