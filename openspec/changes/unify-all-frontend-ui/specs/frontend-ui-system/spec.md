## ADDED Requirements

### Requirement: Canonical semantic UI foundation
Every repository-owned frontend surface SHALL use the Figma page `00 · SYSTEM UI STANDARD · AI START HERE` as the source of truth for semantic colors, typography hierarchy, spacing, radii, focus treatment, and interaction states. The implementation SHALL expose one shared semantic token foundation and SHALL NOT introduce a competing feature-local global design system.

#### Scenario: A frontend surface resolves foundation values
- **WHEN** a migrated page, panel, card, overlay, dialog, form, status, or action is rendered
- **THEN** its system-level colors, typography, spacing, and radii resolve through the shared semantic foundation
- **AND** equivalent semantics do not resolve to unrelated feature-local hard-coded values

#### Scenario: A domain visual needs specialized presentation
- **WHEN** a surface renders domain-specific material such as the office pixel-art scene, a project pipeline canvas, an avatar, a chart, or public-site artwork
- **THEN** the domain visual MAY retain the presentation required to communicate its content
- **AND** surrounding navigation, controls, overlays, actions, dialogs, and feedback SHALL still use the canonical system semantics

#### Scenario: Product UI contains Chinese and Latin text
- **WHEN** repository-owned DOM UI renders Chinese, Latin letters, numbers, symbols, technical values, or mixed-language content
- **THEN** all text resolves through the same locally hosted Noto Sans SC variable font family
- **AND** no entry point depends on a remote web font or a feature-local pixel, system, or monospace family
- **AND** canvas-drawn office artwork remains the only documented typography exception

### Requirement: Shared component and action semantics
Equivalent frontend controls SHALL use shared visual and interaction semantics for buttons, navigation items, inputs, selects, text areas, toggles, cards, status badges, modal shells, dialogs, close controls, toasts, inline alerts, banners, and notification items. Primary, secondary, danger, close, delete, clear, remove, save, test, and navigation actions MUST retain the distinct meanings documented by the canonical UI standard.

#### Scenario: Equivalent controls appear on different surfaces
- **WHEN** two frontend surfaces render controls with the same semantic role and state
- **THEN** the controls use the same component contract for dimensions, typography, color, border, focus, hover, active, loading, error, and disabled presentation
- **AND** feature identity does not silently change the action's semantic tone

#### Scenario: A localized navigation entry includes a semantic emoji
- **WHEN** the Human Resources toolbar entry is rendered or the interface language changes
- **THEN** the existing Human Resources role emoji remains visible beside the localized label
- **AND** the decorative emoji is hidden from assistive technology while the localized text remains the accessible name
- **AND** the existing entry handler and navigation boundary remain unchanged

#### Scenario: Close and destructive actions are presented
- **WHEN** a non-destructive close action and an irreversible delete action are rendered
- **THEN** the close action uses the canonical neutral close treatment
- **AND** the delete action uses the canonical danger treatment and its existing confirmation behavior

#### Scenario: A form control changes state
- **WHEN** an input, select, text area, or toggle becomes focused, invalid, disabled, loading, or successfully validated
- **THEN** the corresponding canonical state is visible through text and component styling
- **AND** color alone is not required to understand an error or disabled state

### Requirement: Complete frontend surface adoption
The UI system migration SHALL cover every repository-owned frontend entry point and every frontend module loaded by those entry points, including frontend files already modified or newly added in the working tree when this change begins. No surface SHALL be excluded merely because it predates the system standard or belongs to an in-progress feature change.

#### Scenario: The main Virtual Office application is audited
- **WHEN** reviewers traverse the office chrome, sidebar, chat and browser panels, settings, Agent Management, Human Resources, personal assets, meetings, projects and orchestration, archive room, human decisions, skills, MCP registry, and their dialogs and feedback
- **THEN** every reachable frontend state is either aligned with the canonical UI system or has an explicit documented domain-visual exception

#### Scenario: Standalone and public frontends are audited
- **WHEN** reviewers traverse `setup.html`, `models.html`, `cron.html`, and the `website/` frontend at supported viewports
- **THEN** their layout chrome, controls, forms, navigation, dialogs, and feedback use the canonical UI system
- **AND** no standalone entry point remains on an undocumented legacy component system

#### Scenario: In-progress frontend work is migrated
- **WHEN** a frontend file contains uncommitted or newly added work that is part of another active change
- **THEN** the migration preserves that work's current behavior and incorporates its rendered UI into the canonical system
- **AND** the migration does not revert, duplicate, or replace its backend-facing behavior

### Requirement: Frontend-only behavior compatibility
The migration MUST preserve existing observable workflows, key DOM integration contracts, event handling, API calls, request and response shapes, persistence timing, loading and retry behavior, and business state transitions. It SHALL NOT require a backend route, service, storage, protocol, configuration-format, provider, SSE, or WebSocket change.

#### Scenario: A migrated action is invoked
- **WHEN** a user invokes an existing save, test, activate, retry, import, export, reset, delete, close, or navigation action after migration
- **THEN** the same frontend handler and backend-facing contract are invoked at the same interaction boundary
- **AND** the visual migration does not add, remove, combine, or reorder business side effects

#### Scenario: A visual migration would require backend work
- **WHEN** a proposed UI adjustment cannot be implemented without changing a backend contract or business state machine
- **THEN** that adjustment is excluded from this change
- **AND** the existing behavior remains available with a canonical visual treatment

### Requirement: Responsive, keyboard, and readable presentation
Every migrated frontend surface SHALL remain readable and operable at its supported desktop and narrow viewport sizes. Interactive elements SHALL expose visible keyboard focus, meaningful disabled and loading states, and the existing accessible name and status semantics; modal and overlay migrations SHALL preserve supported Escape, backdrop, focus-entry, and focus-return behavior.

#### Scenario: A migrated surface is rendered at a narrow viewport
- **WHEN** the viewport reaches a supported narrow layout
- **THEN** required content and actions remain reachable without clipped or overlapping text
- **AND** navigation and scroll regions do not trap required controls outside an inaccessible area

#### Scenario: Chat header actions compete with status content
- **WHEN** the chat header shows the optional compact-context action together with Agent and connection status text
- **THEN** compact, new-session, move, and close actions remain visible as one fixed-size borderless icon-control group
- **AND** Agent and status copy truncates before any required action is clipped
- **AND** the existing action handlers and persistence boundaries remain unchanged

#### Scenario: A keyboard user operates a migrated workflow
- **WHEN** the user navigates controls with the keyboard and opens or closes a supported dialog
- **THEN** visible focus follows the active control and the existing keyboard behavior remains functional
- **AND** closing the dialog returns focus according to the existing workflow contract

### Requirement: Unified feedback presentation
Transient and persistent frontend feedback SHALL use the canonical feedback types and semantic tones. Success, information, warning, and error feedback SHALL have consistent structure, placement, duration or persistence rules, stacking behavior, accessible announcement, and optional action treatment appropriate to its type.

#### Scenario: Multiple transient results occur
- **WHEN** more than one transient frontend result is emitted within the stacking window
- **THEN** the results are presented through the shared feedback boundary without overwriting unrelated feedback
- **AND** each result remains distinguishable by text and semantic tone

#### Scenario: An error requires continued user attention
- **WHEN** an action fails and the user must read details, correct input, or retry
- **THEN** the result uses a persistent toast, inline alert, banner, or dialog appropriate to the workflow rather than an automatically disappearing success-style message
- **AND** sensitive configuration values are not exposed in the feedback

### Requirement: Repeatable UI-system acceptance
The change SHALL provide repeatable evidence that all frontend entry points and representative interaction states conform to the canonical UI standard without regressing their behavior. Acceptance MUST cover static enforcement, focused frontend interaction tests, supported viewport checks, and reviewable screenshots for the major surfaces.

#### Scenario: Static UI-system validation runs
- **WHEN** the frontend validation suite inspects migrated source files
- **THEN** it detects undefined semantic UI variables, prohibited competing global tokens, unsupported component-state omissions, and newly introduced inline presentation that bypasses the shared system
- **AND** documented domain-visual exceptions remain distinguishable from violations

#### Scenario: Visual acceptance is performed
- **WHEN** representative desktop and narrow screenshots are compared with the canonical Figma standard and approved feature-specific composition references
- **THEN** reviewers find no clipped text, overlap, placeholder content, inconsistent action semantics, missing states, or undocumented system-level visual deviations
- **AND** existing feature-specific layout references remain authoritative only where they do not conflict with the canonical UI standard
