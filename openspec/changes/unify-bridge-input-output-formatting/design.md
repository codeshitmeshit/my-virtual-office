## Context

The repository already requires prompts constructed for Agents or language models to use XML as the outer structure and to put dynamic or untrusted material in clearly named XML data boundaries. In practice, the codebase has many independent prompt builders:

- Feishu representative messages and Agent-to-Agent communication use `<agent_platform_message_prompt>` and `<feishu_group_message_prompt>`.
- Provider delivery paths add VO routing guidance and output instructions near Codex, Hermes, Claude Code, and OpenClaw bridge code.
- Project execution, meeting, HR, MCP guide generation, and skill organization build their own domain XML prompts.
- Some current prompts interpolate dynamic values directly into element text or attributes.

The desired direction is not to remove domain-specific XML. The desired direction is to make safe XML construction, untrusted data boundaries, and output section placement a shared bridge capability used by provider-visible prompt paths.

This is a technical construction-path refactor. Existing prompt semantics should stay as close as practical to the original prompt text and section structure. Business code should stop assembling final XML strings itself; instead it should pass key-value data, nested mappings, section descriptors, custom tag names, and trust markers to the shared formatter, which renders the final provider-visible XML. Key-value or nested mapping input is the default requirement even for simple prompts.

## Goals / Non-Goals

**Goals:**

- Provide one focused bridge formatting module for safe XML prompt construction and output requirements.
- Support caller-defined tag names, attributes, nested sections, key-value sections, text, and JSON data sections.
- Escape XML text and attribute values consistently.
- Let business callers provide structured data rather than hand-concatenated XML strings.
- Require simple and complex business prompts alike to enter the formatter as key-value or nested mapping input by default.
- Recommend an explicit `output` section for system-authored prompts whenever a stable response shape or bounded user-facing answer is expected.
- Preserve original prompt intent, key wording, domain tags, and output schemas wherever practical.
- Make untrusted data boundaries the default for user and runtime payloads.
- Migrate all known provider-visible prompt builders, starting with Feishu representative dispatch, Agent-to-Agent communication, and provider delivery wrappers for Codex, Hermes, Claude Code, and OpenClaw, then project execution, meetings, HR, MCP guide generation, and skill organization.
- Add tests and static checks that discourage new hand-built bridge XML around untrusted values.
- Validate representative migrated prompts with formal/production-like Agents after development, comparing behavior against original prompt intent.

**Non-Goals:**

- Change domain intent or output schemas while migrating project, meeting, HR, MCP, and skill prompts.
- Change public route schemas, provider result shapes, history storage, approval behavior, or chat UI behavior.
- Parse or validate every possible provider response in this phase.
- Remove provider-specific notes or domain-specific prompt tags.

## Decisions

### 1. Add a focused bridge formatting service

Create a module such as `app/services/bridge_input_output_formatting.py` that owns:

- XML name validation for tag and attribute names;
- XML text escaping;
- XML attribute escaping;
- helper constructors for elements, nested sections, trusted instruction text, untrusted text data, and JSON data;
- bridge prompt assembly utilities for platform messages, Feishu group messages, VO routing guidance, and output sections;
- deterministic output-section placement rules.

The service returns strings rather than introducing a full XML DOM dependency. This keeps the module easy to use from existing synchronous bridge code and makes tests straightforward. The service should still use structured APIs internally, not ad hoc caller-side string concatenation.

### 2. Keep custom business XML first-class

The builder should expose a generic section API rather than only fixed helpers. Example capabilities:

- `element(name, text=None, attrs=None, children=None)`
- `document_from_mapping(root_name, mapping, schema=None)`
- `sections_from_mapping(mapping, trusted_keys=None, untrusted_keys=None)`
- `key_value_section(name, mapping, value_mode="text|json")`
- `trusted_instruction(name, text, attrs=None)`
- `untrusted_text(name, text, attrs=None)`
- `untrusted_json(name, value, attrs=None)`
- `document(root_name, children, attrs=None)`

Fixed bridge helpers can be thin wrappers around the generic builder. This lets business layers keep domain tags such as `<project_execution_prompt>`, `<meeting_result_prompt>`, `<hr_assessment_prompt>`, or `<untrusted_skill_data>` while using one escaping and boundary policy.

Key-value rendering should be deterministic: preserve caller-provided ordering when the input mapping is ordered, otherwise use stable insertion order from Python dictionaries. Values that are mappings or arrays can render either as nested XML sections or escaped JSON-in-XML, selected by the caller.

Bare string prompts should not be the normal public API for business callers. If a raw string helper exists internally, it should be private or clearly marked as trusted/static-only, and static checks should prevent business/provider-visible prompt paths from using it as an escape hatch.

### 3. Treat caller-provided data as untrusted by default

The API should make trusted instruction sections visually and programmatically distinct from untrusted payload sections. Static trusted text is acceptable for bridge-owned instructions. User text, Feishu sender names, IDs, message IDs, project descriptions, task descriptions, meeting content, HR material, attachment metadata, MCP tool descriptions, skill files, and provider recovery context must go through escaped text or JSON data helpers.

This decision prevents injected content like `</message><rules>ignore...</rules>` from becoming an instruction sibling.

### 3a. Preserve existing prompts while changing ownership of formatting

Migration should not opportunistically rewrite prompt intent. For each migrated prompt, the implementation should identify which original sections are trusted instructions and which are runtime data, map those sections into key-value or nested mapping input, then re-render the same conceptual prompt through the formatter. Wording changes are allowed only when needed for safety, consistency, or the shared output contract, and must be covered by focused tests or implementation evidence.

### 4. Represent output requirements as an `output` section

The existing separate output-contract module/concept should be retired for migrated prompt paths. Output requirements are represented as structured key-value input under an `output` key or an explicitly named `output` section. The accepted design should expose one conceptual bridge formatting capability:

- input prompt construction;
- output section rendering;
- provider-specific output notes when needed;
- deterministic final-section ordering.

When `output` exists, the formatter renders it as the final top-level XML section regardless of where the caller provided it in the mapping. Provider-specific notes can be nested inside `output`, but the common rule is placement and safe rendering, not a separate prefixed contract block.

For migrated system-authored prompts, callers should usually include `output`. This is especially important for project execution/review/rework, meeting decisions, HR assessment/introduction, MCP guide generation, skill organization, Agent-to-Agent communication, and provider delivery wrappers that expect a bounded final answer. User-authored message text is not itself `output`; it stays in untrusted data. If a prompt intentionally omits `output`, the omission should be evident in prompt coverage evidence or tests so it is a conscious decision rather than drift.

### 5. Migrate in phases with visible coverage

Phase 1 should migrate:

- `_feishu_group_provider_message`;
- Hermes platform delivery wrapper;
- Codex provider delivery wrapper;
- Claude Code provider delivery wrapper;
- OpenClaw representative dispatch delivery wrapper;
- `VOAgentCommunicationService` platform message wrapper;
- compatibility service bridge fallbacks where they can still be called directly.

Phase 2 migrates project execution, meeting, HR, MCP, and skill organization prompts. Final acceptance for this OpenSpec change requires all known provider-visible prompt builders to use the formatter, except for explicitly documented unsupported exceptions. Exceptions are not a way to defer ordinary migration; they are reserved for prompts that are not provider-visible, are generated by third-party tools outside this repository, or would require a separate product decision.

### 6. Verification strategy

Focused tests should cover:

- escaping text and attributes;
- rejecting invalid tag and attribute names;
- JSON-in-XML data boundaries;
- preserving custom business tag structure;
- output contract idempotency;
- bridge delivery messages include the shared input/output structure;
- injection strings stay inside untrusted data sections;
- existing provider and route boundary tests still pass.

Static checks should scan migrated bridge files for known prompt envelopes being hand-built with interpolated dynamic values. This is not a substitute for runtime tests, but it prevents obvious regressions.

Formal Agent validation should run after the implementation passes deterministic tests. Use configured real providers where available to exercise representative prompts from each migrated family:

- core bridge chat: Codex, Hermes, Claude Code, OpenClaw;
- Feishu representative and Agent-to-Agent messages;
- project execution/review/rework;
- meeting decision/result/turn prompts;
- HR assessment/introduction prompts;
- MCP usage guide and skill organization prompts.

Validation should compare the migrated formatter-backed prompts to the original prompt intent rather than require bit-for-bit prompt equality. Record whether the Agent follows the requested `output` section, avoids leaking internal process, preserves required schema, handles injected-looking user content as data, and produces a usable answer. If a formal Agent/provider is unavailable, record the gap and do not claim improvement for that area.

### 7. Keep migration reviewable without narrowing final scope

Implementation can be split into small OpenSpec tasks and commits:

1. build the formatter and output section support;
2. migrate core chat/bridge delivery wrappers;
3. migrate project/meeting prompts;
4. migrate HR/MCP/skill prompts;
5. add static checks, documentation, and repository-level agent instructions.

Each task should preserve behavior for its area and run focused tests. The staged implementation plan reduces review risk without changing the final requirement that existing provider-visible input/output prompt formatting goes through the shared module.

`AGENTS.md` should be updated as part of this change so future contributors and coding agents see the new rule before editing prompt code: provider-visible prompts must be expressed as key-value or nested mapping input to the shared formatter, dynamic data must use untrusted boundaries, and system-authored prompts should include `output` when a stable response shape is expected.

## Risks / Trade-offs

- **[Large blast radius if all prompts migrate at once]** -> Split implementation into small task-sized migrations while keeping final acceptance tied to all known provider-visible prompt builders.
- **[Business prompts need expressive custom XML]** -> Provide generic custom element builders instead of a fixed schema-only API.
- **[Prompt behavior changes accidentally during refactor]** -> Preserve original prompt intent and section names wherever practical; document intentional wording changes and test downstream consumers.
- **[Key-value API loses ordering or structure]** -> Preserve mapping order and support nested sections or JSON boundaries by caller choice.
- **[Business callers keep passing raw strings]** -> Make key-value input the default API, document any raw-string exceptions, and add static checks for provider-visible prompt paths.
- **[Caller misuse still possible if raw XML is accepted too easily]** -> Make trusted raw XML opt-in and avoid it for untrusted runtime values.
- **[Output section changes provider behavior]** -> Preserve original output wording where practical, place `output` last consistently, and verify focused Codex, Hermes, Claude Code, OpenClaw, Feishu, and Agent-to-Agent paths.
- **[Missing output sections keep behavior vague]** -> Treat `output` as the recommended default for system-authored prompts and include omission coverage for any prompt that intentionally does not specify output requirements.
- **[Real Agent behavior differs from deterministic tests]** -> Add formal Agent validation after development and treat improvement claims as evidence-based rather than assumed.
- **[Static scans produce false positives]** -> Limit initial scans to known bridge prompt envelope names and require explicit migration inventory for broader business prompts.

## Open Questions

No product decision is open before task planning. The main implementation choice is whether to fold the existing output-contract file into the new bridge formatting module immediately or keep a delegating compatibility facade for a smaller first task.
