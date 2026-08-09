## Why

The current settings experience presents a large number of administrator-oriented options in a compact side panel, making configuration groups, action boundaries, and status feedback difficult to scan. A larger, structured modal can improve comprehension and navigation while preserving the settings behavior that existing users already rely on.

## What Changes

- Replace the compact settings side panel with a large modal designed for dense administrator and advanced-user workflows.
- Organize all existing settings into clear task-oriented categories and module cards with stable header, navigation, content, and footer regions.
- Improve the visual hierarchy and presentation of field help, configured states, loading states, test results, save results, and destructive actions.
- Preserve every existing settings control, capability, business result, save boundary, activation rule, and observable side effect.
- Preserve the current hybrid save model: ordinary settings use the existing global save action, while integrations that already provide independent actions continue to do so.
- Preserve current immediate interactions such as language and font-size changes, as well as current test, import, export, reset, setup-wizard, and close behavior.
- Update the Figma specification so that its interaction and persistence boards describe this compatibility boundary rather than proposing new save or dismissal semantics.
- Add focused interaction and visual regression coverage for the large modal and its existing settings actions.

No settings capability is added or removed, and this change is not intended to alter server-side configuration contracts.

## Capabilities

### New Capabilities

- `settings-modal-experience`: Defines the large settings modal, task-oriented navigation, preservation of all existing settings actions, behavior-compatibility requirements, and visual acceptance expectations.

### Modified Capabilities

None. The repository currently has no settings-experience capability whose requirements need a delta, and existing backend capability requirements are not changed.

## Impact

- Affected surface: the main Virtual Office web settings entry point, settings markup, styling, client-side presentation state, and settings-focused tests.
- Design impact: the existing Figma large-modal, interaction-overview, and persistence frames must be aligned with the confirmed compatibility scope.
- API and persistence impact: existing endpoints, local-storage keys, server-side files, save timing, and test side effects remain unchanged.
- Dependency impact: no new external dependency is expected.
- Compatibility: existing users must retain access to every current setting and receive the same observable result from each action.
