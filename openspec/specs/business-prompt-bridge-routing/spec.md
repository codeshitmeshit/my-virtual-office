## Purpose

Ensures Virtual Office business prompt builders use a common bridge entry point so provider-visible prompts, output schemas, and reply validation are constructed consistently without exposing low-level XML rendering to business modules.

## ADDED Requirements

### Requirement: Business prompts route through the common bridge
The system SHALL provide a common business prompt bridge for provider-visible prompts produced by Virtual Office business modules. Migrated business modules MUST submit structured business input to the bridge and MUST NOT directly call the low-level XML formatter to produce provider-visible prompt text.

#### Scenario: HR builds a provider prompt
- **WHEN** an HR flow prepares a daily report request, agent introduction request, assessment request, assessment summary request, or related provider-visible prompt
- **THEN** the HR flow submits structured business input to the common business prompt bridge
- **AND** the provider-visible prompt is rendered by the bridge rather than directly by HR code

#### Scenario: Meeting builds a provider prompt
- **WHEN** a meeting flow prepares advisory, turn, result, targeted-question, or decision-related provider-visible prompt content
- **THEN** the meeting flow submits structured business input to the common business prompt bridge
- **AND** the provider-visible prompt is rendered by the bridge rather than directly by meeting code

#### Scenario: Project or workflow builds a provider prompt
- **WHEN** a project execution, workflow review, workflow rework, task-final-result, or related project prompt is prepared for an Agent or language model
- **THEN** the project/workflow flow submits structured business input to the common business prompt bridge
- **AND** the provider-visible prompt is rendered by the bridge rather than directly by project/workflow code

#### Scenario: Archive or support business flow builds a provider prompt
- **WHEN** archive refinement, archive context, MCP guide generation, skill organization, or another support business flow prepares provider-visible prompt content
- **THEN** that flow submits structured business input to the common business prompt bridge
- **AND** the provider-visible prompt is rendered by the bridge rather than directly by the business flow

### Requirement: Business bridge input has stable semantic sections
The common business prompt bridge SHALL accept a structured input shape that separates domain, operation, locale, target provider context, trusted system instructions, untrusted business data, optional history or attachment context, output requirements, and validation policy.

#### Scenario: Business submits prompt input
- **WHEN** a migrated business module asks the bridge to build a provider-visible prompt
- **THEN** it passes a dictionary or equivalent structured mapping with named semantic sections
- **AND** the bridge promotes that input into a provider-ready prompt document with explicit trusted and untrusted boundaries

#### Scenario: Locale is required
- **WHEN** a business flow needs Chinese or another specific working language
- **THEN** the business input includes a locale or language requirement
- **AND** the bridge renders that language requirement as trusted system-authored instruction, not as untrusted user data

#### Scenario: Business data is dynamic
- **WHEN** business data contains user text, Agent output, Feishu payloads, HR evidence, meeting transcript material, project/task state, archive materials, skill content, MCP material, or attachments
- **THEN** the bridge treats that data as untrusted unless the caller explicitly marks static system-authored instruction text as trusted
- **AND** the untrusted data cannot close or replace trusted instruction or output sections

### Requirement: Output contracts are bridge-owned
The common business prompt bridge SHALL own output-section rendering and reply validation setup for migrated business prompts. Business modules SHALL describe the expected output as structured bridge input and SHALL NOT append independent provider-visible output contract blocks.

#### Scenario: Business prompt expects JSON
- **WHEN** a migrated business flow expects parser-compatible JSON
- **THEN** the business input supplies the expected schema, strictness, and fallback/error handling rules through the bridge output section
- **AND** the rendered output requirements appear as the final top-level output section of the provider-visible prompt

#### Scenario: Business prompt expects narrative text
- **WHEN** a migrated business flow expects Markdown or natural-language text with bounded shape
- **THEN** the business input supplies the required text shape and limits through the bridge output section
- **AND** the bridge records enough validation policy for the caller to distinguish valid text, malformed output, and incomplete work

#### Scenario: Provider reply is consumed
- **WHEN** a migrated business flow receives a provider reply for a bridge-built prompt
- **THEN** the flow consumes a bridge-normalized output or a bridge-classified validation failure
- **AND** the business flow does not parse raw provider output in a way that bypasses the bridge output contract for the migrated path

### Requirement: Low-level formatter remains internal to bridge rendering
The low-level XML formatter SHALL remain available as the bridge rendering primitive, but migrated business prompt modules SHALL NOT import or invoke it as their normal provider-visible prompt construction path.

#### Scenario: Static coverage checks migrated business prompts
- **WHEN** prompt coverage checks inspect migrated business modules
- **THEN** direct low-level formatter calls for provider-visible prompt construction fail unless the path is listed as an explicit temporary exception
- **AND** each exception includes owner area, reason, risk, and planned migration condition

#### Scenario: Bridge implementation renders XML
- **WHEN** the common business prompt bridge internally renders a provider-visible prompt
- **THEN** it may invoke the low-level XML formatter
- **AND** that invocation is not considered a business-layer bypass

### Requirement: Migration preserves behavior and evidence
The migration SHALL preserve existing provider-visible prompt intent, domain-specific section names where downstream behavior depends on them, output schemas, public route behavior, persisted data schemas, and UI behavior unless a task explicitly documents a deliberate compatibility change.

#### Scenario: A prompt family is migrated
- **WHEN** a prompt family is moved from direct formatter calls to the common business prompt bridge
- **THEN** focused tests verify the prompt-visible domain structure, output schema expectations, escaping, and public behavior that downstream consumers depend on
- **AND** the migration evidence records any intentional wording, section, or parsing changes

#### Scenario: Validation runs after migration
- **WHEN** migrated business prompt paths are ready for acceptance
- **THEN** focused regression tests run for HR, meetings, project/workflow, archive, MCP guide, and skill organization prompt families
- **AND** unavailable formal provider validation is recorded as a gap rather than claimed as an improvement
