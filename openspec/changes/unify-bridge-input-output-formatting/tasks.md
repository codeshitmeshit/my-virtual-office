## 1. Shared Formatting Module

- [x] 1.1 Add a focused bridge input/output formatting service with safe XML name validation, text escaping, attribute escaping, custom element construction, untrusted text sections, untrusted JSON sections, output-section final ordering, and document assembly.
- [x] 1.2 Add deterministic key-value and nested mapping rendering APIs as the default business prompt input path, including support for simple prompts represented as named fields rather than bare prompt strings.
- [x] 1.3 Remove or replace the existing separate Agent output contract path for migrated prompts by representing output requirements as an `output` key/section rendered last.
- [x] 1.4 Add unit tests for escaping, invalid XML names, custom business tags, key-value rendering, nested sections, JSON data boundaries, output-section final ordering, and injection strings that attempt to close instruction tags.

## 2. Bridge Path Migration

- [x] 2.1 Migrate Feishu group message and platform Agent message wrappers to the shared formatter without changing public source metadata or visible history behavior.
- [x] 2.2 Migrate Codex, Hermes, Claude Code, and OpenClaw provider delivery wrappers to the shared formatter for both input prompt construction and `output` section rendering.
- [x] 2.3 Migrate compatibility bridge fallbacks or prove they hydrate to authoritative formatter-backed handlers before normal use.
- [x] 2.4 Add or update focused bridge tests for Feishu representative dispatch, VO Agent-to-Agent communication, Codex, Hermes, Claude Code, OpenClaw, and provider route hydration.

## 3. Business Prompt Migration

- [x] 3.1 Migrate project execution, project review, and project rework prompt builders to pass structured key-value data into the shared formatter while preserving their original domain XML structure and output schemas.
- [x] 3.2 Migrate meeting advisory, meeting result, meeting turn, and related meeting prompt builders to pass structured key-value data into the shared formatter while preserving expected JSON output contracts.
- [x] 3.3 Migrate HR assessment/introduction, MCP usage guide generation, and skill organization prompt builders to pass structured key-value data into the shared formatter while preserving business-specific tags and schemas.

## 4. Guardrails and Documentation

- [x] 4.1 Add static checks so new provider-visible bridge/business prompt code cannot hand-build known XML wrappers around untrusted values.
- [x] 4.2 Produce a tracked inventory of provider-visible prompt sites covered by the shared formatter, plus any intentionally unsupported exceptions with reason and risk.
- [x] 4.3 Document how business code should map its previous XML prompt semantics into key-value or nested mapping input, including how to create custom XML tags and content, when to use trusted instruction sections versus untrusted data boundaries, why bare prompt strings are not the default path, and why system-authored prompts should include `output` whenever stable reply shape is expected.
- [x] 4.4 Update `AGENTS.md` with the shared prompt formatter rule so future provider-visible prompt work defaults to key-value formatter input, untrusted data boundaries, and final `output` sections for system-authored prompts that need stable replies.

## 5. Verification

- [x] 5.1 Run focused Python tests for the formatter, provider bridge delivery, Agent-to-Agent communication, Feishu representative dispatch, provider service boundaries, project execution prompts, meeting prompts, HR prompts, MCP guide prompts, and skill organization prompts.
- [x] 5.2 Run focused JavaScript/static checks for route hydration, bridge/module boundary expectations, and prompt formatter coverage.
- [x] 5.3 Run formal/production-like Agent validation for representative migrated prompt families, comparing migrated prompt behavior against original prompt intent and recording prompt-following, output compliance, answer quality, regressions, improvements, and unavailable-provider gaps.
- [x] 5.4 Run strict OpenSpec validation and record the command/result with prompt coverage evidence, including output-section coverage or intentional omissions for migrated system prompts and formal Agent validation notes.
