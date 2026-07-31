# Task 6.1 Final Prompt Formatter Coverage

Date: 2026-07-31

## Current Direct Formatter Scan

Command:

- `rg "bridge_input_output_formatting|prompt_formatter\.render_document|prompt_format\.render_document|bridge_prompt_formatter\.render_document" app/server.py app/server_services app/services -g '*.py' -n`

Remaining runtime direct formatter use is limited to:

- Bridge internals:
  - `app/services/business_prompt_bridge.py`
  - `app/services/agent_platform_prompt_formatting.py`
  - `app/services/bridge_input_output_formatting.py`
- Support/profile documents:
  - `app/services/agent_workspace_documents.py`
  - `app/services/hermes_profile_documents.py`
- Legacy compatibility exception:
  - `app/server.py`

All split service and focused business prompt helper modules migrated in this
change are no longer direct low-level formatter callers.

## Static Coverage State

`tests/test_prompt_formatter_static.py` now allows only:

- Bridge internal direct formatter files.
- Support/profile document exceptions.
- The single legacy `app/server.py` compatibility exception.

The temporary business prompt exception allowlist has been reduced to
`app/server.py` only. HR, meeting, project execution, workflow, archive, MCP,
skill organization, and provider skill sync modules have been removed from the
temporary exception set after migration and focused validation.

## Remaining Exception Rationale

`app/server.py` still contains legacy compatibility prompt builders for multiple
business areas. Authoritative split services have been migrated, and tests for
route/module split continue to cover delegation boundaries. Removing all legacy
server prompt code is larger than this bridge migration because `server.py`
also contains unrelated dirty worktree changes and compatibility definitions.
The final static coverage keeps this exception explicit instead of silently
allowing new service/module direct calls.
