<!-- cosh-dashboard-control {"mode":"continuous","sequence":1,"mode_updated_at":"2026-08-09T16:34:45+08:00"} -->

## MODIFIED Requirements

### Requirement: Figma-aligned orchestration workspace
The project-management orchestration workspace MUST retain the approved workflow composition represented by full-screen frame `147:2` and modal `148:3`, including its dimensions, pipeline canvas, task grouping, directional relationships, and absence of the bottom "保存编排" action. The canonical Figma page `00 · SYSTEM UI STANDARD · AI START HERE` SHALL be authoritative for global typography hierarchy, semantic colors, shared controls, icons, dialogs, action semantics, focus states, and feedback presentation when those system rules differ from the earlier feature-specific frames.

#### Scenario: Orchestration modal is rendered
- **WHEN** an authorized user opens orchestration for a project
- **THEN** the modal retains the approved header, explanatory notice, pipeline canvas, task cards, parallel groups, directional relationships, and dimmed project-page composition
- **AND** shared controls, action tones, icons, dialog chrome, focus states, and feedback use the canonical system UI standard

#### Scenario: Visual acceptance is performed
- **WHEN** the implementation is rendered at the feature reference viewport
- **THEN** visual verification SHALL compare workflow geometry and canvas composition with frames `147:2` and `148:3`
- **AND** visual verification SHALL compare global tokens, shared components, action semantics, and feedback with the canonical system UI standard
- **AND** an intentional domain-layout exception MUST be documented rather than implemented as a competing global style

#### Scenario: Modal footer is rendered
- **WHEN** the orchestration modal is open
- **THEN** no "保存编排" button SHALL be shown
- **AND** removing that action SHALL NOT add an implicit project-start action

