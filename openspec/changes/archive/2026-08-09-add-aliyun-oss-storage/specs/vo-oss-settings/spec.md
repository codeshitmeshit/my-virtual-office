## ADDED Requirements

### Requirement: OSS configuration is managed in the existing settings experience
The VO settings experience SHALL include an OSS configuration section for the connection endpoint, bucket, access-key identifier, and access-key secret. It MUST NOT expose a separate region field because the system derives the SDK-required region from the endpoint. The section MUST reuse the existing settings page and its authorization boundary rather than introducing a separate OSS administration page.

#### Scenario: Authorized settings user opens OSS settings
- **WHEN** a user who can manage the existing VO settings opens the settings page
- **THEN** the page presents the OSS configuration section within the existing experience
- **AND** the page does not present or require a separate region field
- **AND** the section reuses the existing settings styles and appears before the page-level save action
- **AND** it does not present bucket creation, deletion, or general OSS resource administration controls

#### Scenario: Authorized settings user opens OSS settings before configuration
- **WHEN** an authorized settings user opens the OSS settings and no active OSS configuration exists
- **THEN** the settings API returns a successful unconfigured projection
- **AND** the page presents an empty editable form without an operation-failure message
- **AND** no provider client or network request is created merely to render the empty state

#### Scenario: Unauthorized caller attempts to change OSS settings
- **WHEN** a caller that cannot manage the existing VO settings attempts to read or update OSS configuration
- **THEN** the system applies the existing settings authorization behavior and does not disclose or change the OSS configuration

### Requirement: OSS configuration is application-persisted without environment fallback
The system SHALL persist the active OSS configuration through the application-owned settings path. The system MUST NOT source OSS endpoint, bucket, or credentials from environment variables as either the primary configuration or a fallback. Region SHALL be derived internally from the persisted endpoint and SHALL NOT be an independently persisted or environment-sourced setting.

#### Scenario: Service restarts after configuration activation
- **WHEN** a validated OSS configuration has been activated and the VO service restarts
- **THEN** the same active configuration remains available through the application settings path without requiring environment variables

#### Scenario: OSS-like environment variables are present
- **WHEN** environment variables contain values that resemble OSS connection settings
- **THEN** those values do not create, replace, or override the application-owned active OSS configuration

### Requirement: Credential secrets are write-only at the settings boundary
The system MUST protect the persisted access-key secret and MUST NOT return its stored value through settings APIs or the settings page. After a secret is saved, the settings experience SHALL indicate only that a credential is configured, and changing the secret SHALL require a replacement value.

#### Scenario: Reload settings after saving credentials
- **WHEN** an authorized settings user reloads the OSS settings after a credential has been saved
- **THEN** the page and its backing API indicate that the secret is configured without returning the stored secret

#### Scenario: Replace a configured secret
- **WHEN** an authorized settings user submits a replacement access-key secret and the resulting configuration passes validation
- **THEN** the replacement becomes part of the active configuration and the previous secret is no longer used

#### Scenario: Observe settings failure output
- **WHEN** OSS configuration validation or persistence fails
- **THEN** the returned error and application logs omit the access-key secret and other credential material

### Requirement: Configuration must pass an explicit connection test before activation
The settings experience SHALL provide an explicit connection test that verifies the configured credentials can access the specified existing bucket. Before constructing the provider client, the backend MUST derive the required region from a supported standard Alibaba Cloud OSS regional endpoint. A configuration MUST NOT become active unless region derivation and the connection test both succeed, and VO MUST NOT create, delete, or reconfigure the bucket while testing.

#### Scenario: Region is derived from a standard endpoint
- **WHEN** an authorized settings user submits a standard Alibaba Cloud OSS regional endpoint containing an unambiguous region identifier
- **THEN** the backend derives the SDK region from that endpoint without requiring a region field in the request
- **AND** the derived region is used only as an internal provider-client value

#### Scenario: Endpoint does not contain a derivable region
- **WHEN** an authorized settings user submits an acceleration endpoint, custom CNAME, or another endpoint whose region cannot be derived deterministically
- **THEN** the configuration is rejected with a safe, actionable validation error before provider access
- **AND** the submitted configuration does not become active

#### Scenario: Connection test succeeds
- **WHEN** the submitted endpoint yields a region and the endpoint, bucket, and credentials can access the specified bucket
- **THEN** the system marks the tested configuration as eligible for activation without modifying the bucket

#### Scenario: Connection test fails
- **WHEN** authentication, connectivity, endpoint derivation, bucket existence, or bucket-access validation fails
- **THEN** the submitted configuration does not become active
- **AND** the user receives a safe, actionable failure category without credential disclosure

#### Scenario: Failed replacement preserves the active configuration
- **WHEN** an active OSS configuration exists and a proposed replacement fails its connection test
- **THEN** subsequent storage operations continue using the previously active configuration

### Requirement: Activated settings take effect for subsequent storage operations
After an eligible configuration is activated, the system SHALL use it for subsequent operations through the VO object-storage capability without requiring a process restart. Activation MUST be atomic from the perspective of new storage operations.

#### Scenario: Activate a tested replacement
- **WHEN** an authorized settings user activates a replacement configuration that passed its current connection test
- **THEN** storage operations started after activation use the replacement configuration
- **AND** no new operation observes a partial mixture of old and new configuration values
