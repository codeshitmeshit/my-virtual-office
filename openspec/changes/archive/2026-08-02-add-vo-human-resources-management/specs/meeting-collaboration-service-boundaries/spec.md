## MODIFIED Requirements

### Requirement: Agent occupancy and restoration safety
Meeting services SHALL preserve participant eligibility, archive-manager exclusion, explicit HR eligibility, occupancy ownership, pre-meeting status snapshots, concurrent occupancy protection, and restoration of each Agent's prior state after every terminal or recovery path. HR participation SHALL use ordinary meeting semantics and SHALL NOT by itself create or modify a Human Resources performance assessment.

#### Scenario: Meeting occupies eligible Agents
- **WHEN** a meeting starts with eligible participants, including HR when selected
- **THEN** each participant SHALL be marked occupied by that meeting only after its prior state is recorded
- **AND** another incompatible meeting SHALL not claim the same Agent concurrently

#### Scenario: Archive manager is selected
- **WHEN** a meeting request or executable meeting attempts to include the archive manager
- **THEN** participant validation SHALL preserve the existing archive-manager exclusion and stable rejection semantics

#### Scenario: HR participates in a meeting
- **WHEN** HR is selected as an otherwise eligible meeting participant
- **THEN** HR SHALL participate through the ordinary preparation, turn, summary, occupancy, and restoration lifecycle
- **AND** HR attendance SHALL NOT automatically create a performance event or assessment for any participant

#### Scenario: Meeting terminates or is recovered
- **WHEN** a meeting completes, is cancelled, fails, times out, or is recovered after restart
- **THEN** each participant SHALL be released only if the meeting still owns its occupancy
- **AND** its recorded pre-meeting state SHALL be restored without overwriting a newer owner
