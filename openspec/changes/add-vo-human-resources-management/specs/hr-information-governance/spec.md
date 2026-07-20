## ADDED Requirements

### Requirement: Audience-specific Human Resources disclosure
The system SHALL derive Human Resources responses from one authoritative record while enforcing distinct full, public, and self/audit views according to the caller AI ID trusted within the VO interaction boundary.

#### Scenario: Human or HR reads an Agent record
- **WHEN** the authenticated VO human or HR requests Human Resources information
- **THEN** the response MAY include the full profile, raw and normalized reports, full assessments, detailed evidence, sensitive improvement feedback, and authorized audit history

#### Scenario: Ordinary Agent reads another Agent
- **WHEN** an ordinary Agent uses the controlled query surface for a different Agent
- **THEN** the response SHALL include only name, public introduction, AI ID, availability, public work summary, and workload level
- **AND** it SHALL omit raw reports, detailed evidence, sensitive improvement feedback, and internal HR judgment

### Requirement: Controlled cross-Agent query surface
Ordinary Agents MUST use the designated Human Resources query capability to inspect another Agent's permitted information, and direct access to full records or another Agent's restricted view SHALL be rejected.

The controlled Agent query surface SHALL trust VO-internal Agent interactions: it SHALL require an originless loopback request, the Human Resources action header, and a self-declared AI ID that resolves to a currently active directory Agent. It SHALL NOT require a bearer grant or restrict access by Provider kind. Access records are operational, best-effort records of that declared VO identity rather than cryptographic identity attestations.

#### Scenario: Agent performs a permitted lookup
- **WHEN** a registered Agent requests another Agent by stable AI ID through the controlled capability
- **THEN** the system SHALL return the audience-filtered public view and record the access atomically with the successful disclosure

#### Scenario: Any registered Provider performs a permitted lookup
- **WHEN** an active OpenClaw, Hermes, Codex, Claude Code, or other registered VO Agent declares its own stable AI ID through the controlled query headers
- **THEN** the same public or self projection SHALL be available without Provider-specific credential delivery
- **AND** an unknown, inactive, browser-originated, or non-loopback request SHALL still be rejected

#### Scenario: Agent bypasses the controlled capability
- **WHEN** an Agent attempts to read storage, a human-only endpoint, a raw report, detailed evidence, or sensitive feedback belonging to another Agent
- **THEN** the system SHALL reject the request without disclosing restricted content

### Requirement: Cross-Agent access logging
Every successful ordinary-Agent read of another Agent's Human Resources information SHALL create a durable access record containing viewer AI ID, viewed AI ID, timestamp, permitted information scope, request source, and result, while HR and human reads SHALL NOT create such a record.

#### Scenario: Agent views another Agent
- **WHEN** an ordinary Agent receives another Agent's permitted Human Resources view
- **THEN** exactly one corresponding access record SHALL be persisted

#### Scenario: HR or human views an Agent
- **WHEN** HR or the authenticated VO human reads any Agent record
- **THEN** no cross-Agent access record SHALL be created for that read

#### Scenario: Rejected read occurs
- **WHEN** a caller is denied restricted information
- **THEN** the system SHALL NOT record the event as a successful view
- **AND** security diagnostics MAY retain a separate sanitized denial event

### Requirement: Scoped audit-log visibility
The complete cross-Agent access history SHALL be visible to HR and the authenticated VO human, while a viewed Agent SHALL see only records where it is the target and ordinary Agents SHALL NOT see unrelated access records.

#### Scenario: Viewed Agent checks its access history
- **WHEN** an Agent requests access history about itself
- **THEN** it SHALL receive records identifying which Agent viewed it, when, and what public scope was returned

#### Scenario: Ordinary Agent requests unrelated history
- **WHEN** an Agent requests access records for which it is neither the authorized HR nor the viewed target
- **THEN** the request SHALL be rejected or return no records

### Requirement: Safe audit and Human Resources retention
Human Resources responses and access records SHALL avoid secrets and raw credentials, preserve historical traceability across Agent rename or deactivation, and prevent silent destructive replacement.

#### Scenario: Agent is renamed or deactivated
- **WHEN** a historical report, assessment, or access record is read after identity state changes
- **THEN** it SHALL remain associated with the stable AI ID and retain the historical display context
