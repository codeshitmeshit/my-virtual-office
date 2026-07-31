## Why

Virtual Office has already introduced a shared XML formatter, but HR, meeting, project, workflow, and archive business prompt builders can still call that low-level formatter directly. That keeps prompt structure, locale handling, trusted/untrusted boundaries, output schemas, and provider response expectations scattered across business modules.

The product needs a higher-level common bridge entry point so business lines submit structured business dictionaries and receive provider-ready prompts and parser-ready output contracts without assembling prompt documents themselves.

## What Changes

- Introduce a business prompt bridge capability above the existing XML formatter.
- Require migrated business prompt builders to submit structured dictionaries to a bridge promotion/preprocessing layer instead of directly calling the low-level formatter.
- Centralize locale, source metadata, trusted instruction rules, untrusted business data boundaries, attachments/history context, provider output requirements, and output schema placement.
- Provide bridge APIs for rendering business prompt documents and, where applicable, for sending them through provider adapters and parsing/validating provider replies.
- Migrate known provider-visible business prompt families in stages: HR reporting/introduction/assessment, meeting prompts, project execution/workflow/task-final-result prompts, archive refinement/context prompts, MCP guide generation, and skill organization prompts.
- Keep the low-level formatter as an internal rendering primitive used by the bridge layer, not as the normal public entry point for business modules.
- Preserve existing prompt intent, domain section names, parser expectations, public route behavior, and UI behavior unless a task explicitly documents a deliberate change.
- Add static and runtime tests proving migrated business modules no longer directly assemble provider-visible prompt XML through the low-level formatter.

## Capabilities

### New Capabilities

- `business-prompt-bridge-routing`: Defines the higher-level bridge entry point for business prompt construction, migration requirements, output validation expectations, and compatibility constraints.

### Modified Capabilities

- None.

## Impact

- Affects provider-visible prompt builders under `app/services`, `app/server_services`, and legacy compatibility functions in `app/server.py`.
- Affects tests that inspect prompt shape for HR, meetings, projects/workflows, archive room, MCP usage guide generation, skill organization, and Agent/provider bridge delivery.
- Does not intentionally change public HTTP route schemas, persisted HR/project/meeting/archive data schemas, UI rendering, provider result schemas, or user-visible copy.
- May introduce focused bridge modules and compatibility wrappers so existing call sites can migrate incrementally without exposing the low-level formatter to business code.
