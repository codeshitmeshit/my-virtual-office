## Purpose

Define the shared HTTP handling, service isolation, compatibility, and management-token interaction guarantees established by the first project-service extraction.

## Requirements

### Requirement: Shared HTTP response behavior
The system SHALL provide one shared HTTP response path for JSON success responses, JSON error responses, request identifiers, and common security headers used by migrated routes.

#### Scenario: Migrated route returns a successful JSON response
- **WHEN** a migrated route completes successfully
- **THEN** the shared response path SHALL emit the route's existing status code and JSON payload
- **AND** the response SHALL include the configured common security headers and a request identifier

#### Scenario: Migrated route returns a client error
- **WHEN** request parsing or validation fails for a migrated route
- **THEN** the shared response path SHALL emit the route's compatible client-error status and a structured JSON error
- **AND** the response SHALL not expose secrets, stack traces, or internal filesystem paths

#### Scenario: Migrated route raises an unexpected error
- **WHEN** an unexpected exception escapes the migrated service boundary
- **THEN** the HTTP layer SHALL return a structured server error with a request identifier
- **AND** the underlying exception SHALL be recorded in server logs with sensitive values redacted

### Requirement: Bounded JSON request handling
The system MUST reject malformed or oversized JSON requests before invoking a migrated service operation, using an explicit request-size limit and consistent client-error responses.

#### Scenario: Request contains malformed JSON
- **WHEN** a migrated JSON endpoint receives a body that cannot be decoded as JSON
- **THEN** the system SHALL return a compatible 400-class JSON error
- **AND** the project service SHALL not be invoked

#### Scenario: Request exceeds the configured limit
- **WHEN** a migrated JSON endpoint receives a body larger than the configured request-size limit
- **THEN** the system SHALL return HTTP 413
- **AND** the project service SHALL not be invoked

### Requirement: Explicit service boundary
The pilot project operation SHALL receive explicit validated inputs and explicit dependencies, and SHALL return a structured result or a defined business failure without reading HTTP handler state or writing an HTTP response.

#### Scenario: Service is called outside the HTTP handler
- **WHEN** a test invokes the pilot project service with valid inputs and test dependencies
- **THEN** the service SHALL complete without constructing an HTTP handler or network server
- **AND** its result SHALL be assertable as application data

#### Scenario: Service reports a business failure
- **WHEN** the pilot operation encounters a defined business condition such as a missing project or invalid execution state
- **THEN** the service SHALL return or raise the defined business failure
- **AND** the HTTP layer SHALL map it to the endpoint's existing status and response semantics

### Requirement: Project execution pilot extraction
The change SHALL extract exactly one bounded project execution operation as the pilot, while reusing existing persistence, workspace-safety, provider, and state-transition logic rather than duplicating those behaviors.

#### Scenario: Pilot operation succeeds
- **WHEN** a client invokes the selected project execution endpoint with a valid request
- **THEN** the HTTP handler SHALL parse and validate the protocol input and delegate business orchestration to the pilot service
- **AND** the externally observable result SHALL match the behavior before extraction

#### Scenario: Existing safety gate blocks execution
- **WHEN** an existing workspace, reviewer, concurrency, or state safety gate rejects the pilot operation
- **THEN** the extracted path SHALL preserve that rejection and its externally observable response
- **AND** it SHALL not start provider execution or perform an invalid state transition

### Requirement: API and data compatibility
The change MUST NOT intentionally alter public route paths, accepted request fields, response JSON fields, status-code semantics, persistence formats, SSE events, WebSocket behavior, frontend calls, or provider protocols.

#### Scenario: Existing API contract suite runs after extraction
- **WHEN** the focused API contract and project execution regression tests are run
- **THEN** all previously supported pilot-route request and response scenarios SHALL remain valid

#### Scenario: Existing persisted project data is loaded
- **WHEN** the application starts with project data written before this change
- **THEN** the migrated operation SHALL read and update that data without a migration or schema rewrite

### Requirement: Incremental and reversible migration
The pilot extraction SHALL be independently reviewable and reversible, and SHALL not require later roadmap changes for the application to remain functional.

#### Scenario: Only the first change is deployed
- **WHEN** the HTTP foundation and pilot service change is deployed without the later project, meeting, or provider changes
- **THEN** all non-pilot routes SHALL continue using their existing implementation
- **AND** the application SHALL remain fully operable

#### Scenario: Pilot extraction is reverted
- **WHEN** the pilot implementation commit is reverted before any persistence-format change
- **THEN** the previous route implementation SHALL be restorable without data repair

### Requirement: Virtual Office management token dialog
The frontend SHALL request a missing or expired management token through a Virtual Office styled modal dialog rather than the browser-native prompt, and SHALL preserve session-only token handling.

#### Scenario: Protected request requires a token
- **WHEN** `managementFetch` receives HTTP 403 and no accepted token is available
- **THEN** the frontend SHALL display a branded modal with a password input, explanatory text, cancel action, and confirm action
- **AND** the token SHALL not be displayed as plain text

#### Scenario: User confirms a token
- **WHEN** the user enters a non-empty token and confirms the modal or presses Enter
- **THEN** the frontend SHALL store the token in `sessionStorage` and retry the original request with `X-VO-Management-Token`

#### Scenario: User cancels token entry
- **WHEN** the user activates cancel, closes the modal, clicks its backdrop, or presses Escape
- **THEN** the modal SHALL close, restore the previously focused element, and the protected request SHALL fail without being retried

#### Scenario: Server rejects the entered token
- **WHEN** the retried request still returns HTTP 403
- **THEN** the frontend SHALL remove the rejected token from `sessionStorage`
- **AND** it SHALL preserve the existing invalid-token error behavior
