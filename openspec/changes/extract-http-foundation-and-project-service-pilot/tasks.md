## 1. Characterize the Existing Pilot Contract

- [x] 1.1 Add focused characterization tests for the current workspace-validation handler covering success, missing project, invalid workspace, submitted-path precedence, project mutation, persistence calls, and unchanged response payload/status semantics; run only the new focused tests.
- [x] 1.2 Add HTTP-boundary characterization tests for the pilot route covering valid JSON, malformed JSON, scalar JSON, oversized body, and the existing route path; run only the pilot HTTP contract tests and record any intentional behavior gap against the confirmed spec before implementation.

## 2. Introduce the Shared HTTP Boundary

- [x] 2.1 Generalize the existing bounded JSON reader for an explicit size limit and object-only validation while preserving the management endpoint behavior; add focused tests for 400, 408, and 413 outcomes.
- [x] 2.2 Add shared JSON result/error response helpers with `Content-Type`, `Content-Length`, request identifier, `X-Content-Type-Options: nosniff`, sanitized unexpected-error handling, and redacted logging; adopt them only in the focused helper tests and existing management response path, then run those tests.

## 3. Extract the Project Execution Pilot Service

- [x] 3.1 Create `app/services/__init__.py` and `app/services/project_execution.py` with an immutable `ServiceResult` and a workspace-validation operation that accepts explicit load, save, validate, and clock dependencies without importing `server.py`.
- [x] 3.2 Add direct service tests covering success, missing project, invalid workspace, submitted-path precedence, one save per completed validation path, persistence failure propagation, validator failure propagation, and the absence of HTTP/server construction.

## 4. Migrate the Pilot Route

- [x] 4.1 Change only `POST /api/projects/{projectId}/project-execution/workspace/validate` to use the bounded reader, extracted service, and shared response helpers while preserving the current route, payloads, statuses, project fields, and storage format.
- [x] 4.2 Run the pilot HTTP contract tests and relevant project execution tests; compare success and error responses with the task 1 characterization evidence and fix only migration-caused differences.

## 5. Remove the Obsolete Wrapper

- [x] 5.1 Remove `_handle_project_execution_workspace_validate` only after no route or test references remain, and add or update a static dependency check proving `app/services/project_execution.py` does not import `server.py` or depend on `OfficeHandler`.
- [x] 5.2 Run focused service, HTTP, workspace validation, project execution, and merged-change regression tests; record commands, results, failures, and any unverified browser/provider/SSE/WebSocket paths for the final validation gate.

## 6. Document the Accepted Boundary

- [x] 6.1 Update the relevant architecture/developer documentation with the route-versus-service responsibility boundary, explicit dependency convention, compatibility guarantees, deferred global CORS/bind/auth work, and the requirement that later phases do not treat the pilot as a complete project-domain architecture.
- [x] 6.2 Re-run `openspec validate extract-http-foundation-and-project-service-pilot --strict` and verify the implementation, focused evidence, documentation, and completed task checklist remain traceable to every confirmed `http-service-boundary` scenario.

## 7. Replace the Native Management Token Prompt

- [x] 7.1 Add a Promise-based Virtual Office management-token modal in `app/i18n.js` with password masking, confirm/cancel/backdrop/Enter/Escape behavior, focus restoration, and unchanged `sessionStorage` retry semantics; add narrowly scoped styles and Chinese/English dialog strings.
- [x] 7.2 Add focused frontend tests for rendering, keyboard behavior, cancellation, successful retry, and rejected-token cleanup; run the relevant static/UI checks and repeat the protected-action browser acceptance through `./start.sh`.
