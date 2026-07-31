## Why

Virtual Office currently lets many business and provider bridge paths build their own XML prompts and output instructions. Those hand-built prompts repeat concepts such as role, task, context, message metadata, output sections, and untrusted input boundaries, but they do not consistently escape XML text, attributes, or user-controlled values. This makes prompt injection harder to reason about, makes provider behavior inconsistent, and leaves each new business feature to reinvent the same input and output rules.

The product needs to promote input prompt construction and output requirements into a shared bridge formatting capability. Business layers must still be able to express their own domain-specific XML tags and content, but dynamic or untrusted values must pass through one common formatting module before a prompt reaches Codex, Hermes, Claude Code, OpenClaw, or another Agent bridge.

This is a technical refactor: business prompt semantics should stay as close as practical to the existing original prompts, while the construction mechanism changes. Instead of business code hand-concatenating prompt strings, business code must pass structured key-value data, section descriptors, and domain tag names to the shared module; the module then renders the final XML prompt for the target Agent. Even the simplest prompt should be represented as key-value input rather than a bare prompt string.

## What Changes

- Add a shared bridge input/output formatting capability that owns safe XML element construction, attribute escaping, text escaping, JSON-in-XML data boundaries, and output sections.
- Support business-defined XML tag names, attributes, nested sections, key-value sections, and content through validated builder APIs instead of requiring every business layer to use one fixed prompt template.
- Require business callers to provide prompt inputs as key-value or nested mapping data by default, even for simple prompts, so the shared formatter remains the single XML assembly point.
- Preserve existing prompt intent and wording wherever practical during migration; the refactor should primarily replace manual string concatenation with structured input to the formatter.
- Treat user text, Feishu payloads, Agent-to-Agent messages, project/task state, meeting data, HR material, MCP/skill material, attachments metadata, and provider recovery context as untrusted unless the caller explicitly marks a bridge-owned instruction section as trusted.
- Route bridge inputs through the shared module: Feishu representative Agent dispatch, VO Agent-to-Agent communication, Codex/Hermes/Claude Code/OpenClaw provider delivery boundaries, and existing business prompt builders that produce provider-visible XML for project execution, meetings, HR, MCP guide generation, and skill organization.
- Retire the separate output-contract module/concept. Business callers express output requirements as an `output` key or section in the same structured formatter input.
- When the formatter sees an `output` section, it renders that section as the final top-level section of the prompt so the Agent receives output requirements last and consistently.
- System-authored interaction prompts should include an `output` section by default whenever the system expects a stable reply shape, follow-up action, parser-compatible response, or bounded user-facing answer. User-provided natural-language content remains untrusted input data, not an output section.
- Add static and focused runtime tests that fail when bridge paths hand-build unsafe XML around untrusted values or bypass the shared formatter for provider-visible input/output contracts.
- Update repository agent instructions so future prompt construction follows the shared key-value formatter and `output` section rules by default.
- Add post-development validation with formal/production-like Agents to compare migrated prompts against the original prompt behavior, checking whether prompt following, output stability, and task success are preserved or improved.
- Preserve public chat, history, project, meeting, HR, and provider route behavior while changing only the internal prompt construction path.

## Capabilities

### New Capabilities

- `bridge-input-output-formatting`: Defines the shared bridge input prompt builder, customizable XML section support, untrusted data boundary rules, output section ordering, migration scope, and compatibility requirements.

### Modified Capabilities

None.

## Impact

- Affects provider-visible prompt construction and output contract injection in shared chat/Agent bridges.
- Initial implementation may be split into reviewable tasks, but final acceptance for this change requires all known provider-visible prompt builders and output requirement builders to use the shared module or to be listed as an intentionally unsupported exception with a documented reason and static guard.
- Business callers should stop assembling full XML prompt strings directly and instead pass structured key-value data, trusted instruction sections, untrusted data sections, and custom tag names into the shared formatter. Raw string prompt input is not the default path and requires an explicit, reviewed exception.
- No public HTTP route, persisted history schema, provider result schema, or user-visible reply contract is intentionally broken.
- Acceptance evidence should include automated tests plus formal Agent validation notes for representative migrated prompts; improvement claims require observed evidence, while neutral/no-regression results are acceptable for this technical refactor.
