## Why

The Skills Library needs a low-maintenance way to place newly created and imported skills into useful categories without introducing a separate organization lifecycle. Reusing the Virtual Office's existing archive manager keeps classification authority and activity history in one established system while preserving a simple category-based user experience.

## What Changes

- Add an immutable `默认标签` category that receives newly created and imported skills.
- Add owner-only smart organization that asks the existing archive manager to process only skills currently in `默认标签`.
- Organize skills into one primary purpose category, with optional auxiliary tags, and allow the archive manager to create a category when no general category is semantically appropriate.
- Allow the Virtual Office owner to correct one skill's primary category at a time.
- Surface running, completed, partially failed, unavailable, and disabled conditions without adding organization lifecycle fields to skills.
- Keep successfully organized skills in their destination categories while failed skills remain discoverable in `默认标签` for manual correction.
- Require the archive manager to create an ordinary category when the purpose is clear but no existing category matches, and expose a safe reason for genuine classification failures.
- Write one summary activity to the archive manager's existing activity log for each organization run.
- Keep the Skills Library separate from the MCP Registry and omit unsupported workspace concepts from the UI.

## Capabilities

### New Capabilities

- `skill-library-organization`: Defines category semantics, owner and archive-manager responsibilities, smart organization behavior, manual correction, result presentation, and archive-manager activity logging.

### Modified Capabilities

None.

## Impact

- Skills Library modal, category navigation, skill detail controls, and localized copy.
- Skills Library persistence and HTTP/service contracts for category metadata and organization actions.
- Existing archive-manager lifecycle, mutual-exclusion behavior, and activity log integration.
- Authorization checks for Virtual Office owner-only mutations.
- Automated service, API-contract, UI-state, and acceptance coverage for category and organization scenarios.
