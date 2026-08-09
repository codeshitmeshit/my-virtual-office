## ADDED Requirements

### Requirement: Backend modules can store and explicitly restore OSS objects
The system SHALL provide a backend-only storage capability that allows a VO integration to save a material to Alibaba Cloud OSS and explicitly restore the saved bytes on demand. The capability MUST NOT expose public or signed object URLs and MUST NOT start an automatic or background restore.

#### Scenario: Save and explicitly restore a material
- **WHEN** an authorized backend integration saves a material and later explicitly requests restoration using the returned object identifier
- **THEN** the capability returns bytes identical to the saved content together with the stored object's basic metadata
- **AND** no restore occurs before the explicit request

#### Scenario: No direct browser access is issued
- **WHEN** a backend integration saves or inspects an object
- **THEN** the capability returns an internal object reference rather than a public or signed download URL

### Requirement: Object identifiers are isolated by integration
The system SHALL scope stored objects to the calling integration so that one integration cannot read, overwrite, delete, inspect, or enumerate another integration's objects merely by reusing its object identifier. End-user ownership and authorization decisions MUST remain the responsibility of the calling integration.

#### Scenario: Integration accesses its own object
- **WHEN** an integration requests an operation on an object in its own scope
- **THEN** the capability evaluates the operation within that integration's isolated namespace

#### Scenario: Integration attempts cross-scope access
- **WHEN** an integration supplies an object identifier belonging to a different integration scope
- **THEN** the capability rejects the operation without returning the other integration's content or metadata

### Requirement: Storage operations have deterministic overwrite and delete semantics
The system SHALL allow a caller to test existence, inspect metadata, list objects in its scope, overwrite an existing object identifier, and explicitly delete an object. Saving new content to an existing object identifier MUST replace the previously readable content, and a successful explicit deletion MUST make the object unavailable through this capability without providing module-level recovery.

#### Scenario: Overwrite an existing object
- **WHEN** an integration saves new content using an existing object identifier in its own scope
- **THEN** a subsequent restore returns the new content and current metadata rather than the previous content

#### Scenario: Delete an existing object
- **WHEN** an integration explicitly deletes an existing object in its own scope
- **THEN** subsequent existence, restore, and metadata operations report that the object is absent
- **AND** the capability offers no recovery action for the deleted content

#### Scenario: List scoped object metadata
- **WHEN** an integration lists objects in its own scope
- **THEN** the capability returns only objects in that scope with identifiers and basic metadata including size and content type when available

### Requirement: Large materials are transferred without a small application limit
The system SHALL support materials up to the applicable Alibaba Cloud OSS object limits without imposing a smaller fixed VO file-size limit. Saving and restoring a large material MUST use bounded-memory transfer behavior rather than requiring the complete material to be held in application memory at once.

#### Scenario: Transfer a material larger than the in-memory working buffer
- **WHEN** an integration saves and explicitly restores a material larger than the configured transfer buffer
- **THEN** the complete material is transferred successfully in bounded-memory increments
- **AND** the restored bytes match the original content

### Requirement: Provider failures are explicit and secret-safe
The system MUST report Alibaba Cloud OSS authentication, connectivity, missing-object, and provider-operation failures through stable failure categories. A failed operation MUST NOT be reported as successful, and failure results and logs MUST NOT contain access credentials or complete material content.

#### Scenario: Provider rejects a save
- **WHEN** Alibaba Cloud OSS rejects or cannot complete a save request
- **THEN** the capability returns a categorized failure and does not return a successful object result

#### Scenario: Restore target does not exist
- **WHEN** an integration explicitly restores an object that is absent from its scope
- **THEN** the capability returns a stable not-found result without exposing provider credentials or another scope's object information

### Requirement: Storage requires an active validated configuration
The system SHALL execute OSS object operations only with the currently active configuration established by the VO OSS settings capability.

#### Scenario: No validated configuration is active
- **WHEN** a backend integration requests an object operation before any OSS configuration has been validated and activated
- **THEN** the capability rejects the request with a stable configuration-unavailable failure and sends no object request to Alibaba Cloud OSS
