## ADDED Requirements

### Requirement: Skills Library organization boundaries
The system SHALL present skill organization as part of the Skills Library and SHALL keep the Skills Library separate from the MCP Registry.

#### Scenario: Owner opens the Skills Library
- **WHEN** the Virtual Office owner opens the Skills Library
- **THEN** the header presents smart organization, skill creation, and skill import actions
- **AND** the interface does not present a browse-MCP action

#### Scenario: Skills Library terminology is rendered
- **WHEN** the Skills Library renders organization and source information
- **THEN** it does not present a team-space concept as the scope or owner of the library
- **AND** locally managed skills identify their source as the local Skills Library

### Requirement: Category-only organization model
The system SHALL represent organization through a skill's category placement and SHALL NOT add intake, library, or organization lifecycle fields such as pending, stored, unorganized, or organized.

#### Scenario: Skill organization is inspected
- **WHEN** a user views or queries a skill
- **THEN** its organization is determined from its primary category
- **AND** no separate organization lifecycle value is required

### Requirement: Primary categories and auxiliary tags
Each skill SHALL have exactly one primary category and MAY have auxiliary tags. Users MAY add auxiliary tags, while the archive manager SHALL retain final authority to correct, merge, or remove ordinary categories and tags.

#### Scenario: Skill has classification metadata
- **WHEN** a classified skill is returned
- **THEN** it has exactly one primary category
- **AND** it may have zero or more auxiliary tags

#### Scenario: User-added tag conflicts with archive governance
- **WHEN** the archive manager determines that a user-added tag is incorrect, duplicative, or obsolete
- **THEN** the archive manager may correct, merge, or remove that tag

### Requirement: Immutable default category
The system SHALL provide a system category named `默认标签`. The system MUST NOT allow `默认标签` to be renamed, merged, or deleted.

#### Scenario: Owner attempts to modify the default category
- **WHEN** the owner attempts to rename, merge, or delete `默认标签`
- **THEN** the system rejects the operation
- **AND** the category remains available

### Requirement: New skill intake
The system SHALL assign every newly created or imported skill to `默认标签` without introducing an intermediate intake state.

#### Scenario: Skill is created
- **WHEN** a user successfully creates a skill
- **THEN** the skill's primary category is `默认标签`

#### Scenario: Skill is imported
- **WHEN** a user successfully imports a skill
- **THEN** the skill's primary category is `默认标签`

### Requirement: Purpose-based category governance
The system SHALL provide the general purpose categories `开发与测试`, `协作与文档`, `项目与流程`, `运维与诊断`, and `知识与内容`. The archive manager MAY create an ordinary category when a skill clearly does not belong to any existing category and SHALL have final authority over the meaning of ordinary categories.

#### Scenario: Skill matches a general category
- **WHEN** the archive manager determines that a skill clearly matches an existing general category
- **THEN** it assigns that existing category as the skill's primary category

#### Scenario: Skill does not match an existing category
- **WHEN** the archive manager determines that a skill clearly falls outside all existing categories
- **THEN** it may create an ordinary category with an appropriate purpose
- **AND** it assigns the skill to that new category

### Requirement: Archive-manager smart organization
The system SHALL use the existing archive-room archive manager to organize skills and SHALL limit each run to skills whose current primary category is `默认标签`.

#### Scenario: Smart organization begins
- **WHEN** the owner starts smart organization while the archive manager is available and idle
- **THEN** the existing archive manager processes every skill currently in `默认标签`
- **AND** it does not reprocess skills in any other category

#### Scenario: Archive manager is unavailable
- **WHEN** the owner attempts smart organization and the existing archive manager is unavailable
- **THEN** the system rejects the request with a visible error
- **AND** it does not substitute another agent

### Requirement: Owner-only category mutations
The system SHALL restrict smart organization and manual primary-category changes to the Virtual Office owner.

#### Scenario: Owner changes organization
- **WHEN** the Virtual Office owner starts smart organization or manually changes a skill's primary category
- **THEN** the system permits the operation when all other preconditions are satisfied

#### Scenario: Non-owner changes organization
- **WHEN** a non-owner attempts to start smart organization or manually change a skill's primary category
- **THEN** the system rejects the operation without changing skill categories

### Requirement: Organization mutual exclusion and empty-state prevention
The system SHALL prevent duplicate or concurrent archive-manager work by disabling smart organization whenever the archive manager is running any archive or skill organization task. The system SHALL also disable smart organization when `默认标签` contains no skills.

#### Scenario: Archive manager is busy
- **WHEN** the archive manager is running an archive or skill organization task
- **THEN** the smart organization action is visibly disabled
- **AND** no organization request is queued or started

#### Scenario: Default category is empty
- **WHEN** `默认标签` contains no skills
- **THEN** the smart organization action is visibly disabled
- **AND** the interface explains that no skills need organization

### Requirement: Direct and partially successful organization
The system SHALL apply each successful category assignment directly without an undo operation. A failed skill SHALL remain in `默认标签` while successful skills from the same run SHALL remain in their destination categories.

#### Scenario: Organization succeeds for all skills
- **WHEN** the archive manager successfully classifies every processed skill
- **THEN** each skill is moved directly to its destination category
- **AND** the system does not offer an undo action

#### Scenario: Organization partially fails
- **WHEN** the archive manager classifies some processed skills successfully and fails to classify others
- **THEN** successful skills are moved to their destination categories
- **AND** failed skills remain in `默认标签`
- **AND** successful assignments are not rolled back

### Requirement: Lightweight result presentation
The system SHALL present organization progress and outcomes through a lightweight marker at the top of the Skills Library and SHALL NOT require a detailed success report in the Skills Library.

#### Scenario: Organization is running
- **WHEN** skill organization is in progress
- **THEN** the top marker identifies the archive manager as organizing skills

#### Scenario: Organization completes successfully
- **WHEN** all processed skills are classified successfully
- **THEN** the top marker indicates that organization completed
- **AND** the marker remains until dismissed or replaced by the next organization result

#### Scenario: Organization partially fails
- **WHEN** one or more processed skills fail classification
- **THEN** the top marker displays the number of failed skills
- **AND** failed skills are visibly identified in `默认标签`

#### Scenario: Owner opens a partial-failure marker
- **WHEN** the owner activates the partial-failure marker
- **THEN** the Skills Library selects `默认标签`
- **AND** it shows only skills that failed classification

### Requirement: Manual correction of failed classifications
The system SHALL allow the owner to change one skill's primary category at a time. The outstanding failure count SHALL decrease after each correction and SHALL transition to a resolved marker when all failed skills have been corrected.

#### Scenario: Owner corrects one failed skill
- **WHEN** the owner changes a failed skill from `默认标签` to another primary category
- **THEN** the skill moves to the selected category
- **AND** the outstanding failure count decreases by one

#### Scenario: Owner corrects the final failed skill
- **WHEN** the owner corrects the last outstanding failed skill
- **THEN** the top marker indicates that all failed items have been handled

#### Scenario: Owner selects multiple skills for correction
- **WHEN** the owner attempts to change multiple skills as one initial-release operation
- **THEN** the interface requires the skills to be changed individually
- **AND** it does not provide batch or drag-and-drop classification

### Requirement: Archive-manager activity summary
The system SHALL append one terminal summary activity to the existing archive-manager activity log for every attempted skill organization run, using the existing completed or failed activity semantics. The archive manager's current state SHALL communicate that work is running. The Skills Library SHALL NOT introduce a separate organization log.

#### Scenario: Organization run is recorded
- **WHEN** a skill organization run reaches a completed or failed outcome
- **THEN** the archive manager's existing activity history contains one summary record for that run
- **AND** the record communicates the applicable completed or failed outcome

#### Scenario: Organization run is active
- **WHEN** a skill organization run is still active
- **THEN** the archive manager's current state communicates that organization is running
- **AND** the terminal summary record is not appended before an outcome exists

#### Scenario: User views the Skills Library
- **WHEN** the Skills Library presents the latest organization outcome
- **THEN** it does not present a separate detailed organization-log interface
