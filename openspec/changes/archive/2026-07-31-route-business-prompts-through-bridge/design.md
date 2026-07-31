## Context

See `proposal.md` for motivation and `specs/business-prompt-bridge-routing/spec.md` for behavior requirements. The current codebase already has a low-level XML formatter (`bridge_input_output_formatting`) and a bridge-specific promotion path for Agent/platform delivery prompts. The remaining gap is that business prompt modules can still import the low-level formatter directly and construct provider-visible prompt documents themselves.

The migration must respect existing prompt semantics because downstream code and Agents rely on domain-specific tags, strict JSON schemas, and recognizable output sections. The main architectural change is therefore not a new provider protocol; it is a boundary change: business modules provide structured business input to a common bridge facade, and the bridge owns promotion, XML rendering, and reply validation setup.

## Goals / Non-Goals

**Goals:**

- Establish a common business prompt bridge API above the low-level XML formatter.
- Make migrated business prompt modules pass structured dictionaries with domain, operation, locale, instructions, untrusted data, output requirements, and validation policy.
- Keep the low-level formatter private to bridge implementation modules for migrated provider-visible business prompt paths.
- Migrate prompt families incrementally while preserving prompt intent, domain tags, output schemas, public behavior, and parser compatibility.
- Add static coverage so future provider-visible business prompts cannot bypass the bridge without an explicit exception.
- Provide enough bridge-normalized output classification for migrated callers to distinguish valid output, malformed output, incomplete work, and provider failure.

**Non-Goals:**

- Replace provider adapters or change provider transport APIs.
- Change persisted HR, meeting, project, archive, or skill data schemas.
- Redesign UI rendering or public HTTP response contracts.
- Force all prompt families into one domain root tag; domain-specific XML structures remain allowed behind the bridge.
- Claim provider quality improvements without formal or production-like validation evidence.

## Decisions

### 1. Add a business bridge facade above the existing formatter

Create a focused service layer, tentatively `services.business_prompt_bridge`, that owns the public business prompt construction API. It accepts a structured mapping such as:

- `domain`: stable domain key such as `hr.daily_report`, `meeting.result`, `project.execution`, or `archive.refine`.
- `operation`: concrete operation inside the domain.
- `locale`: required working language or output language.
- `target`: provider/Agent context when known.
- `instructions`: trusted static system-authored rules.
- `data`: untrusted business payloads.
- `history` / `attachments`: optional untrusted context.
- `output`: schema, strictness, format, and fallback expectations.
- `validation`: parser or post-processing policy.
- `sections`: optional domain-specific rendered section descriptors when a prompt needs stable legacy tag names.

The facade promotes that input into an internal bridge prompt document, then delegates XML rendering to the existing low-level formatter. Business modules no longer call `bridge_input_output_formatting.render_document` directly for migrated provider-visible prompt text.

Alternative considered: keep each business module on the low-level formatter and add more static checks. That preserves less code churn now, but it does not solve the product problem: business layers still own prompt envelope policy and output schema placement.

### 2. Preserve domain-specific prompt structure through bridge templates

The bridge should support domain adapters/templates rather than one universal XML root. HR can keep `hr_*` domain roots, meeting prompts can keep meeting-specific sections, and project execution can preserve the sections parser behavior depends on. Each adapter maps a structured business input dictionary to bridge-owned section descriptors.

This avoids breaking parser expectations and Agent prompt-following patterns while still moving XML assembly ownership into the bridge.

Alternative considered: replace all business prompts with one generic `<business_prompt>` root. That would simplify the bridge implementation, but it risks degrading established prompt behavior and would require broader downstream parser and test updates.

### 3. Split migration by prompt family

Migrate in small prompt-family slices:

1. Inventory and guardrails.
2. HR reporting/introduction/assessment.
3. Meeting prompts.
4. Project execution/workflow/task-final-result.
5. Archive/MCP/skill organization.
6. Validation and formal provider evidence.

Each slice keeps compatibility tests close to the moved prompt family and records intentional wording or shape changes.

Alternative considered: one large migration. That would reduce temporary compatibility wrappers, but it would make regressions difficult to isolate across HR, meetings, projects, and archive workflows.

### 4. Treat reply parsing as bridge-owned setup, not necessarily one parser

The bridge should classify expected output and provide helper APIs for strict JSON extraction, text-shape validation, and failure classification. Domain-specific object construction can remain in business modules initially, but migrated paths must consume either a bridge-normalized valid output or a bridge-classified validation failure.

This keeps parsing behavior compatible while starting to centralize output contract enforcement. Fully moving every domain parser into the bridge is intentionally out of scope for the first migration unless a prompt family already has no domain-specific parser dependency.

Alternative considered: make the bridge return final business domain objects for all domains immediately. That would overreach and couple the bridge to HR, meetings, projects, and archive object models.

### 5. Keep compatibility wrappers but make them temporary and visible

Existing business functions can keep their public names while delegating to the bridge. This limits call-site churn and lets tests continue targeting familiar function names. However, static coverage must distinguish wrappers that delegate to the bridge from business functions that still call the low-level formatter directly.

Temporary exceptions must include owner area, reason, risk, and planned migration condition.

## Risks / Trade-offs

- **[Compatibility] Prompt shape drift can change Agent behavior** -> Preserve domain roots and key section names, add focused prompt-shape tests, and record intentional wording changes per migrated family.
- **[Parser correctness] Output schema movement can break downstream parsing** -> Keep output requirements final, migrate one prompt family at a time, and run existing parser tests plus malformed-output tests.
- **[Security] Business payloads may be accidentally marked trusted** -> Bridge API defaults dynamic `data`, `history`, and `attachments` to untrusted; tests include XML-breaking injection payloads.
- **[Coverage] Static checks may produce false positives for UI HTML, docs, tests, or bridge internals** -> Scope checks to provider-visible prompt modules and maintain an explicit exception inventory.
- **[Migration churn] Direct imports of the low-level formatter are common in existing prompt modules** -> Use compatibility wrappers and focused adapters to reduce unrelated refactors.
- **[Validation gap] Formal provider environments may not be available for every provider** -> Record unavailable providers as gaps and avoid claiming behavior improvement without evidence.

## Migration Plan

1. Inventory direct low-level formatter usage and classify each site as bridge implementation, business prompt, test, doc, UI, or temporary exception.
2. Add the business bridge facade, data model helpers, output policy helpers, and coverage tests.
3. Migrate HR prompt builders first because HR currently drove the need and has focused tests for daily reporting, information completion, and assessment.
4. Migrate meeting prompt builders and preserve JSON result contracts.
5. Migrate project/workflow/task-final-result prompt builders and preserve existing checklist/final-result output behavior.
6. Migrate archive/MCP/skill organization prompt builders and preserve existing parsing and UI behavior.
7. Tighten static coverage to fail direct business imports of the low-level formatter outside bridge internals and documented exceptions.
8. Run focused regression tests and record formal/production-like provider validation or unavailable-provider gaps.

Rollback strategy: because public function names can remain as wrappers, a prompt family can be reverted by changing that wrapper back to its previous implementation while keeping the bridge facade present. Static checks should allow rollback only as a documented temporary exception.

## Open Questions

None blocking. The exact module/function names can be refined during implementation as long as the bridge boundary and OpenSpec requirements remain satisfied.
