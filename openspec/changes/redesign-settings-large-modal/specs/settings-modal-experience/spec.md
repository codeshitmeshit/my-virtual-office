## ADDED Requirements

### Requirement: Large settings modal shell
The Virtual Office web UI SHALL present the existing settings experience in a large modal suitable for dense administrator workflows instead of the current compact side panel. The modal SHALL provide a stable header, category navigation region, settings content region, and persistent action region while remaining visually subordinate to the office workspace behind it.

#### Scenario: Open settings from the existing entry point
- **WHEN** the user activates the existing Settings and Help menu control
- **THEN** the system displays the large settings modal over the current office workspace
- **AND** the modal begins loading the same saved settings sources used by the current settings UI

#### Scenario: Close settings without invoking an action
- **WHEN** the user activates the modal's existing close affordance without invoking a save, test, import, export, or reset action
- **THEN** the modal closes according to the current settings dismissal behavior
- **AND** the system does not introduce a new save, discard, or confirmation semantic

### Requirement: Task-oriented settings navigation
The modal SHALL organize the existing settings into clear task-oriented categories for connections and Agents, office configuration, display preferences, tools and browser integration, notifications, storage, and advanced actions. Category navigation SHALL change only the presented group and SHALL NOT itself persist configuration or invoke a business action.

#### Scenario: Navigate between categories
- **WHEN** the user selects any settings category
- **THEN** the modal displays the corresponding existing settings controls and actions
- **AND** no save, test, activation, import, export, or reset action is invoked by navigation alone

#### Scenario: Preserve edited field values while navigating
- **WHEN** the user changes a field and navigates to another category before invoking its existing save action
- **THEN** returning to the original category shows the field value held by the current modal session
- **AND** the category switch does not unexpectedly reset the visible form

### Requirement: Complete settings-control parity
The large modal SHALL retain every setting, conditional field, configured-state indicator, help entry, and action available in the current settings UI. Each retained control SHALL remain reachable exactly once through the modal's category structure.

#### Scenario: Existing configuration fields remain available
- **WHEN** an administrator reviews all modal categories
- **THEN** the administrator can access the current OpenClaw, Hermes, native Agent provider, office, display, API usage, PC performance, browser, weather, Feishu notification, Feishu Chat, OSS, and meeting settings

#### Scenario: Existing utility and destructive actions remain available
- **WHEN** an administrator opens the advanced-actions category
- **THEN** the existing export, import, setup-wizard, and full-reset actions remain available
- **AND** their current confirmation and result behavior is preserved

#### Scenario: Conditional settings remain conditional
- **WHEN** the user changes an existing enablement toggle that currently reveals or hides dependent settings
- **THEN** the modal reveals or hides the same dependent controls under the same condition

### Requirement: Existing action behavior compatibility
The redesign SHALL preserve the observable business behavior, save timing, activation rules, and persistence boundaries of every existing settings action. Visual restructuring SHALL NOT silently convert a saving action into a read-only action or combine independent transactions into the global save operation.

#### Scenario: Global settings save preserves its current scope
- **WHEN** the user invokes the global settings save action
- **THEN** the same ordinary configuration and browser-local preference domains are saved as in the current UI
- **AND** the same live UI effects and success or failure outcomes remain observable

#### Scenario: Independent integration actions remain independent
- **WHEN** the user saves or activates an integration that currently has its own action, including Feishu notification, Feishu Chat, or OSS configuration
- **THEN** that action remains independent of the global settings save
- **AND** its result is reported within the corresponding integration card

#### Scenario: Test action retains current side effects
- **WHEN** the user invokes an existing connection or integration test from the large modal
- **THEN** the test performs the same validation, saving, activation, or read-only behavior as the corresponding action in the current UI
- **AND** the redesigned label or nearby help text does not imply that the action is side-effect free when it is not

#### Scenario: Immediate preference action retains current behavior
- **WHEN** the user changes a preference that currently applies immediately, including language or font scale
- **THEN** the preference continues to apply and persist at the same point in the interaction

### Requirement: Clear action and status presentation
The modal SHALL present configured, disabled, loading, success, error, and destructive states with clear text and consistent visual hierarchy. Presentation changes SHALL improve comprehension without changing the underlying action result.

#### Scenario: Action is in progress
- **WHEN** an existing settings action is awaiting completion
- **THEN** the corresponding card visibly communicates that the action is in progress
- **AND** repeated activation is prevented where the current action cannot safely run concurrently

#### Scenario: Action succeeds
- **WHEN** an existing settings action completes successfully
- **THEN** the corresponding card or modal action region displays a clear success result
- **AND** any current configured-state or live-view update remains visible

#### Scenario: Action fails
- **WHEN** an existing settings action fails
- **THEN** the corresponding card displays a readable failure result without exposing secrets
- **AND** unrelated settings categories remain usable

#### Scenario: Global save result remains perceptible
- **WHEN** the global save is pending, succeeds, fails at the service, fails on the network, or exceeds its timeout
- **THEN** the fixed footer reports the matching real state and prevents duplicate pending submission
- **AND** success or failure remains visible until the next attempt without closing the modal

#### Scenario: Global save reaches one persistence authority
- **WHEN** the browser submits ordinary settings or an internal settings workflow persists setup configuration
- **THEN** the request reaches the config runtime service as the only server-side persistence implementation
- **AND** a disk-write or runtime-refresh failure cannot be returned as a successful save

### Requirement: Administrator-focused information density
The modal SHALL prioritize efficient scanning for administrators and advanced users while keeping labels, help text, statuses, and actions readable at supported desktop viewport sizes. The UI SHALL use established Virtual Office typography, colors, spacing, and control styling.

#### Scenario: Review a dense category
- **WHEN** a category contains multiple provider or integration cards
- **THEN** card titles, field groups, status regions, and primary actions remain visually distinguishable without overlapping or clipped content

#### Scenario: Use a narrower supported desktop viewport
- **WHEN** the modal is displayed at a supported narrower desktop viewport
- **THEN** category navigation and settings content remain accessible
- **AND** no required action is hidden outside an unreachable clipped region

### Requirement: Approved design and interaction traceability
The implemented modal SHALL be traceable to approved Figma frames covering the high-fidelity screen, numbered interactions, and persistence boundaries. The approved interaction and persistence frames SHALL describe the compatibility behavior in this specification rather than unapproved target semantics.

#### Scenario: Review the implementation against Figma
- **WHEN** the large modal is ready for visual acceptance
- **THEN** reviewers can compare it with direct links to the approved screen, interaction-overview, and persistence frames
- **AND** visual verification shows no placeholder text, clipped text, missing controls, or undocumented interactive elements

#### Scenario: Figma proposal conflicts with confirmed compatibility scope
- **WHEN** an earlier Figma annotation proposes a save, test, activation, or close behavior that differs from the current UI
- **THEN** the annotation is revised before it is treated as implementation authority
- **AND** the confirmed OpenSpec behavior remains the source of truth

## Non-goals

- Adding, removing, or renaming settings capabilities.
- Adding configuration history, version comparison, rollback, or audit-log product features.
- Changing server-side API contracts, configuration file formats, local-storage keys, or secret-storage policy.
- Removing current persistence side effects from test actions.
- Introducing a new dirty-close confirmation or a new automatic-save model.
- Refactoring unrelated office, Agent, notification, browser, storage, or server functionality.
