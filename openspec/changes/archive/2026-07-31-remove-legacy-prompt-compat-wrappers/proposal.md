## Why

The previous prompt bridge migration moved provider-visible prompt construction behind common bridge-backed helpers, but several legacy private function names still remain as compatibility wrappers in `app/server.py` and split service modules. Some runtime paths and tests still call those wrapper names instead of the authoritative prompt/service functions.

Keeping wrapper names after the bridge migration makes ownership harder to reason about: a future change may accidentally reintroduce prompt logic into a compatibility function, hydration may obscure which implementation is authoritative, and tests may keep depending on `server._*` private helpers instead of the service boundary.

## What Changes

- Replace runtime call sites that invoke legacy prompt compatibility wrapper names with direct calls to the authoritative bridge-backed functions or owning service modules.
- Remove `app/server.py` private compatibility wrappers that are no longer used by runtime code.
- Update tests that only validate prompt rendering to import and exercise the owning prompt/service module instead of `server._*` private wrappers.
- Extract prompt-wrapper-adjacent runtime ownership from `app/server.py` into focused modules when direct wrapper removal would otherwise leave orchestration logic in the monolith or make `server.py` more coupled.
- Keep a compatibility wrapper only when an existing runtime boundary genuinely requires the historical name; such wrappers must be thin delegates, documented, and covered by a removal condition.
- Ensure split service hydration cannot cause `server.py` legacy prompt helpers to override authoritative service implementations.
- Preserve public HTTP routes, provider payload schemas, prompt semantics, output schemas, persistence formats, and UI behavior.

## Capabilities

### New Capabilities

- `prompt-service-entrypoint-ownership`: Defines direct ownership for migrated prompt builders and the removal policy for legacy private compatibility wrappers.

### Modified Capabilities

- None.

## Impact

- Affects private Python entry points in `app/server.py`, `app/server_services/*`, and prompt helper tests.
- May introduce or extend focused service modules to reduce `app/server.py` ownership where wrapper cleanup touches still-active runtime logic.
- Does not intentionally change provider-visible prompt content beyond wrapper removal, nor public route schemas, persisted data, provider result schemas, or UI behavior.
- Reduces legacy `server.py` coupling by making prompt call sites depend on focused bridge-backed modules.
