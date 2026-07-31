## ADDED Requirements

### Requirement: Bridge input formatting is a shared capability
The system SHALL provide one shared bridge input formatter for provider-visible prompts that are constructed by Virtual Office. Bridge callers MUST use this formatter instead of manually concatenating XML around untrusted values.

#### Scenario: A bridge builds a provider prompt
- **WHEN** a bridge path prepares a message for Codex, Hermes, Claude Code, OpenClaw, or another Agent provider
- **THEN** the prompt is constructed through the shared bridge input formatter
- **AND** trusted instructions, source metadata, untrusted user content, and output requirements are represented as distinct XML sections

#### Scenario: A future bridge adds a prompt
- **WHEN** new bridge code needs to construct provider-visible XML prompt content
- **THEN** it uses the shared bridge input formatter
- **AND** static checks fail if it hand-builds known bridge prompt envelopes around untrusted values

#### Scenario: Repository instructions describe prompt construction rules
- **WHEN** developers or agents read the repository-level agent instructions
- **THEN** the instructions require provider-visible prompt construction to use the shared key-value formatter by default
- **AND** they describe the rule that system-authored prompts should include an `output` section when stable reply shape is expected

### Requirement: Existing provider-visible business prompts use the shared formatter
Known Virtual Office business prompts that are sent to an Agent or language model SHALL be constructed through the shared bridge formatter. This includes current project execution, project review/rework, meeting advisory/result/turn, HR assessment/introduction, MCP usage guide, skill organization, Feishu, and Agent-to-Agent prompt builders unless a prompt is explicitly documented as an unsupported exception.

#### Scenario: Current prompt inventory is checked
- **WHEN** bridge formatting checks inspect the repository
- **THEN** every known provider-visible prompt builder is either constructed through the shared formatter or appears in an explicit exception inventory
- **AND** exceptions include the reason, risk, owner area, and planned migration condition

#### Scenario: A legacy prompt remains after migration
- **WHEN** a legacy hand-built provider-visible prompt remains without an exception entry
- **THEN** the formatting checks fail
- **AND** the change is not considered complete

### Requirement: Business layers can define custom XML structure safely
The formatter SHALL support business-defined XML tag names, attributes, nested sections, key-value sections, and text or JSON content while validating tag and attribute names and escaping all dynamic values. The formatter MUST NOT force all business prompts into one fixed schema.

Business callers SHALL provide prompt inputs as key-value or nested mapping data by default, including simple prompts. The formatter is the single owner of assembling that structured data into provider-visible XML.

#### Scenario: A business prompt uses domain-specific tags
- **WHEN** a project, meeting, HR, MCP, skill, Feishu, or Agent communication flow needs a domain-specific XML section name
- **THEN** the caller can create that section through the formatter with validated tag names and escaped attributes
- **AND** the resulting XML preserves the business-specific structure needed by the Agent

#### Scenario: A business prompt passes key-value data
- **WHEN** a business flow has structured prompt inputs such as role, task, context, rules, output schema, project data, meeting data, or HR data
- **THEN** the caller can pass those inputs as key-value or nested mapping data to the formatter
- **AND** the formatter renders the corresponding XML sections without the business code concatenating XML strings

#### Scenario: A simple prompt is formatted
- **WHEN** a business flow has only a simple instruction or message
- **THEN** the caller still passes a key-value input such as a root tag and one or more named fields
- **AND** the formatter renders the XML prompt without accepting a bare provider-visible prompt string as the normal path

#### Scenario: A caller wants to pass raw prompt text
- **WHEN** a caller attempts to bypass key-value formatting with raw provider-visible prompt text
- **THEN** the path is rejected unless it is an explicit documented exception
- **AND** the exception is covered by prompt inventory and static checks

#### Scenario: A caller supplies an invalid XML name
- **WHEN** a caller attempts to create a tag or attribute name that is not a valid safe XML name for this formatter
- **THEN** the formatter rejects the name before producing provider-visible prompt text
- **AND** the caller receives a deterministic error that does not include unbounded prompt content

### Requirement: Untrusted data is isolated and escaped
The formatter MUST treat dynamic user, Agent, Feishu, project, meeting, HR, skill, MCP, attachment, recovery, and provider payload material as untrusted unless explicitly provided as trusted static instruction text. Untrusted data MUST be placed inside named data boundaries and escaped so it cannot close, replace, or create instruction elements.

#### Scenario: User text contains XML-breaking content
- **WHEN** user-controlled text contains strings such as closing tags, nested instructions, angle brackets, quotes, or control characters
- **THEN** the formatted prompt keeps that text inside the intended untrusted data section
- **AND** the text cannot create a sibling instruction section or override the output contract

#### Scenario: JSON payload is embedded in XML
- **WHEN** structured untrusted data is clearest as JSON
- **THEN** the formatter embeds it inside a clearly named XML data boundary
- **AND** any XML-sensitive characters in the serialized JSON are escaped before delivery

### Requirement: Migration preserves original prompt semantics
The migration SHALL preserve existing provider-visible prompt intent, domain tags, output schema expectations, and key instruction wording wherever practical. The primary change is the construction path: business code maps the original XML semantics into key-value or nested mapping input for the formatter instead of hand-building XML strings.

#### Scenario: A legacy prompt is migrated
- **WHEN** a current provider-visible prompt is migrated to the shared formatter
- **THEN** the migrated prompt maps the original XML sections into structured key-value or nested mapping input
- **AND** the migrated prompt keeps the original business intent, required output schema, and domain-specific sections unless the OpenSpec change explicitly documents a deliberate wording change
- **AND** tests cover the prompt features that downstream parsing or Agent behavior depends on

#### Scenario: A migration changes wording intentionally
- **WHEN** a migration intentionally changes prompt wording, section names, or output contract details
- **THEN** the change is documented in the implementation evidence
- **AND** focused tests prove the affected consumer still behaves correctly

### Requirement: Output requirements are formatted as the final output section
The system SHALL represent output requirements through an `output` key or section in the shared bridge formatter input. The system MUST NOT require a separate output-contract module or a separately prefixed output contract block for migrated prompt paths.

System-authored interaction prompts SHOULD include an `output` section by default whenever the system expects a stable reply shape, follow-up action, parser-compatible response, or bounded user-facing answer. User-provided natural-language input remains untrusted input data and MUST NOT be reclassified as an output section merely because it asks for an answer.

#### Scenario: A provider bridge supplies output requirements
- **WHEN** a provider bridge or business prompt supplies an `output` key or section
- **THEN** the formatter renders it as the final top-level XML section of the provider-visible prompt
- **AND** the section describes the required response format, strictness, disclosure limits, and blocker behavior as structured key-value content

#### Scenario: A system interaction expects a strict reply
- **WHEN** a Virtual Office system prompt expects JSON, XML, Markdown sections, a decision, a follow-up action, or any parser-compatible response
- **THEN** the business caller supplies that requirement through an `output` section
- **AND** the formatter renders the `output` section last

#### Scenario: A user message asks for an answer
- **WHEN** a user message contains natural-language instructions about the desired answer
- **THEN** the message remains inside an untrusted input/data section
- **AND** only system-authored output requirements are rendered as the prompt's `output` section

#### Scenario: A caller provides output before other sections
- **WHEN** a caller's key-value input contains `output` before role, task, context, rules, or data sections
- **THEN** the formatter preserves the other section ordering as much as practical
- **AND** moves the rendered `output` section to the final top-level position

#### Scenario: No output section is supplied
- **WHEN** a prompt does not require explicit output instructions and is explicitly allowed to omit them
- **THEN** the formatter does not invent a separate output contract block
- **AND** the omission is visible to coverage checks for migrated provider-visible system prompts

### Requirement: Migrated bridge behavior remains compatible
The migration to shared input/output formatting SHALL preserve existing public behavior for chat, Feishu, Agent-to-Agent communication, provider delivery, history, approvals, cancellations, terminal outcomes, and provider result normalization.

#### Scenario: Existing bridge regressions run
- **WHEN** focused tests for Codex, Hermes, Claude Code, OpenClaw, Feishu representative dispatch, Agent-to-Agent communication, Provider boundaries, and route hydration run after migration
- **THEN** public request/response fields, history attribution, source metadata, conversation IDs, approval behavior, and terminal outcomes remain compatible

#### Scenario: Business prompt regressions run
- **WHEN** focused tests for project execution, meetings, HR, MCP guide generation, and skill organization run after migration
- **THEN** their expected output schemas, prompt-visible domain structure, and public behavior remain compatible
- **AND** untrusted business data cannot close or replace trusted instruction sections

### Requirement: Formal Agent validation compares migrated prompt behavior
After implementation, representative migrated prompts SHALL be exercised with formal or production-like Agents where the environment allows it. The validation MUST compare the migrated formatter-backed prompt behavior against the original prompt intent and record whether output stability, instruction following, and task success are preserved or improved.

#### Scenario: Formal Agent validates migrated bridge prompts
- **WHEN** the migrated bridge prompts are ready for acceptance testing
- **THEN** formal Agents are used to exercise representative Codex, Hermes, Claude Code, OpenClaw, Feishu, and Agent-to-Agent prompt flows where configured and available
- **AND** the evidence records prompt-following quality, output-section compliance, user-visible answer quality, and any regressions or improvements

#### Scenario: Formal Agent is unavailable
- **WHEN** a required formal Agent or provider environment is unavailable
- **THEN** the validation evidence records the missing environment and the affected scenarios
- **AND** the implementation does not claim quality improvement for that provider without evidence

#### Scenario: Improvement is claimed
- **WHEN** the change claims that migrated prompts improve behavior over the original prompts
- **THEN** the claim is backed by formal Agent observations or comparable before/after evidence
- **AND** the evidence identifies the prompt family and the observed improvement category

### Requirement: Formatting diagnostics are bounded and content-free
The shared formatter SHALL expose enough diagnostics to identify formatter use, rejected names, output-section reordering, and migration coverage without logging prompt text, user replies, reasoning text, credentials, approval contents, or unrestricted filesystem paths.

#### Scenario: Formatting fails
- **WHEN** the formatter rejects invalid structure or cannot serialize an input
- **THEN** the error identifies the category and offending field name where safe
- **AND** it does not include the full prompt, untrusted data payload, credentials, or large filesystem paths

#### Scenario: Migration coverage is checked
- **WHEN** bridge formatting checks run
- **THEN** they report which provider-visible bridge paths use the shared formatter
- **AND** they do not expose prompt contents
