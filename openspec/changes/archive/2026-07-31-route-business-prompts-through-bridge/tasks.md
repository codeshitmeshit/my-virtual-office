## 1. Inventory and Bridge Foundation

- [x] 1.1 Create a provider-visible business prompt inventory that classifies current low-level formatter uses as bridge internals, migrated business prompts, tests/docs/UI, or temporary exceptions with owner, reason, risk, and migration condition.
- [x] 1.2 Implement the common business prompt bridge facade with structured input fields for domain, operation, locale, target, trusted instructions, untrusted data, history, attachments, output requirements, validation policy, and domain-specific sections.
- [x] 1.3 Add bridge facade tests for locale rendering, trusted vs untrusted boundaries, XML-breaking data, JSON output contracts, final output ordering, and validation failure classification setup.
- [x] 1.4 Add static coverage checks that fail migrated business prompt modules that directly call the low-level XML formatter for provider-visible prompt construction outside bridge internals and documented exceptions.

## 2. HR Prompt Migration

- [x] 2.1 Migrate HR daily report and agent introduction prompt builders to submit structured input through the common business prompt bridge while preserving existing domain sections and Chinese output requirements.
- [x] 2.2 Migrate HR assessment and assessment summary prompt builders to the common business prompt bridge while preserving JSON schemas, scoring language requirements, and malformed-output handling.
- [x] 2.3 Run focused HR prompt and parser regressions covering daily report rendering, self-assessment presence, introduction completion, assessment JSON validation, Chinese assessment wording, and injection escaping.

## 3. Meeting Prompt Migration

- [x] 3.1 Migrate meeting advisory, turn, result, targeted-question, and decision prompt builders to the common business prompt bridge while preserving expected JSON contracts and meeting-specific section names.
- [x] 3.2 Update meeting prompt tests to verify bridge-owned output sections, trusted/untrusted boundaries, malformed result handling, and compatibility with existing meeting workflow state transitions.

## 4. Project and Workflow Prompt Migration

- [x] 4.1 Migrate project execution prompt construction to the common business prompt bridge while preserving archive context, artifact run instructions, meeting action phases, checklistUpdates output, and task final result requirements.
- [x] 4.2 Migrate workflow review, workflow rework, and workflow task prompt builders to the common business prompt bridge while preserving current output parsing and user-visible workflow behavior.
- [x] 4.3 Migrate task final result and prior-stage result prompt helpers to bridge-owned output and data boundaries without changing final result artifact semantics.
- [x] 4.4 Run focused project/workflow regressions covering project execution prompt shape, checklist updates, final result output, prior-stage context, workflow review/rework parsing, and route hydration compatibility.

## 5. Archive, MCP, and Skill Prompt Migration

- [x] 5.1 Migrate archive refinement and archive context prompt builders to the common business prompt bridge while preserving archive-specific sections, JSON payload boundaries, and UI-facing behavior.
- [x] 5.2 Migrate MCP usage guide generation and skill organization prompt builders to the common business prompt bridge while preserving existing strict output expectations and redaction behavior.
- [x] 5.3 Run focused archive/MCP/skill regressions covering archive refine, archive context, MCP guide prompts, skill organization prompts, output validation, and injection escaping.

## 6. Coverage, Validation, and Evidence

- [x] 6.1 Tighten prompt inventory and static coverage so remaining business direct-formatter uses are either eliminated or recorded as explicit temporary exceptions.
- [x] 6.2 Run focused regression suites for bridge facade, HR, meetings, project/workflow, archive, MCP, skill organization, provider delivery, Agent-to-Agent communication, and legacy route hydration.
- [x] 6.3 Record formal or production-like Agent validation for representative migrated prompt families, including unavailable-provider gaps and avoiding improvement claims without evidence.
- [x] 6.4 Run strict OpenSpec validation and record final implementation evidence with changed files, command results, prompt coverage status, known risks, and remaining exceptions.
