## Why

`app/server.py` currently combines HTTP protocol handling with project execution business orchestration, making changes difficult to isolate and test. Establishing a minimal HTTP foundation and extracting one real project-service slice will validate a repeatable modularization pattern before broader service extraction.

## What Changes

- Centralize JSON request reading, JSON/error responses, request identifiers, and common security headers behind shared HTTP handler helpers.
- Introduce a minimal service contract for explicit inputs, structured outputs, and typed business failures without adopting a new web framework or dependency-injection container.
- Extract one bounded project execution operation from `OfficeHandler` into a project service pilot while reusing existing storage and provider functions.
- Add service-level tests and API contract regression coverage proving that the selected route preserves its path, request, status, and response semantics.
- Replace the browser-native management-token prompt with a Virtual Office styled, keyboard-accessible password dialog while preserving management authentication and session-only token storage.
- Keep SSE, WebSocket, persistence formats, frontend calls, provider behavior, and unrelated routes unchanged.

## Capabilities

### New Capabilities

- `http-service-boundary`: Defines the compatibility and isolation requirements for shared HTTP handling and the first extracted project service boundary.

### Modified Capabilities

None.

## Impact

- Primary code: `app/server.py`, a small new service module near existing application code, and focused tests under `tests/`.
- Public API: no intentional path, payload, status-code, response-schema, SSE, or WebSocket changes.
- Data and dependencies: no persistence migration and no new web framework or runtime dependency.
- Follow-up: provides the proven boundary required by the later project, meeting, and provider extraction changes.
