# Agent Guide Skill Viewer

## Background

The Virtual Office UI already exposes a bottom toolbar and a right-side control panel for common office actions such as projects, archive room, browser, meetings, and the skills library. The user wants to add a new bottom-toolbar button named "Agent Guide" near the current toolbar area shown in the screenshot.

The intent is to let users view the VO built-in skills that are currently exposed by this Virtual Office instance. This is not a skill recommendation feature. Skill recommendation should be handled separately in the VO `skill-turial` capability.

## Target Users

- Primary user: a Virtual Office operator who wants to quickly inspect what built-in VO skills are available.
- Secondary user: an agent workflow maintainer who needs a visible, user-facing index of the skills exposed by the current VO runtime.

## Product Goal

Add a clear "Agent Guide" entry in the VO UI so users can browse the built-in and exposed VO skills in a readable modal without needing to inspect local files or agent configuration manually.

## Current Product Decisions

The following choices have been clarified by the user:

- This phase only supports viewing skills.
- The feature must not recommend skills.
- Skill recommendation belongs in VO `skill-turial`, not in this Agent Guide entry.
- Each skill should be shown as an information card.
- Each information card should include:
  - skill name.
  - purpose or short usage description.
  - triggering / applicable scenarios.
  - category.
- The displayed scope is the VO built-in exposed skills.
- The entry should open a center modal, not a narrow right-sidebar section.
- The modal should support category filtering.
- The modal does not need keyword search in this phase.

## Proposed Scope

### In Scope

- Add an "Agent Guide" button to the bottom toolbar.
- Open a center modal when the button is clicked.
- Show only VO built-in exposed skills.
- Use information cards for skills.
- Provide category filters for browsing.
- Show enough description for users to understand when a skill applies.
- Keep this feature read-only.
- Preserve existing Skills Library behavior and meaning.

### Out of Scope

- Skill recommendation.
- Task-to-skill matching.
- Search by keyword.
- Editing, adding, deleting, or uploading skills from this modal.
- Managing user-created skills.
- Showing all Codex skills installed outside the VO built-in exposed skill set.
- Triggering an agent run directly from a skill card.
- Changing `skill-turial` behavior.

## Source Of Truth

The current local VO instance already documents the built-in skill source of truth in `skills/catalog.md`.

At the time this requirement is created, the exposed VO built-in skills are:

- `vo-operating-guidelines`
- `vo-agent-communication`
- `vo-codex-communication`
- `vo-browser-control`
- `vo-agent-workspace`
- `vo-project-workflow`
- `vo-meeting-execution`

Implementation should avoid hardcoding unrelated global Codex skill directories into this feature. If the implementation reads from local files, it should read from the VO built-in exposed skill source or an equivalent VO-owned manifest.

## Constraints

- The UI should remain compact and scannable in the existing pixel-style VO interface.
- The feature should not make users believe it is choosing the best skill for their task.
- The modal should be read-only and clearly distinct from the existing editable Skills Library.
- Category filtering should help browsing without becoming a recommendation system.
- The feature should not expose internal-only, debug-only, or unavailable skills.
- Existing toolbar buttons, the Skills Library modal, and agent skill editing should not regress.

## Non-Goals

- A complete agent capability marketplace.
- A global Codex skill browser.
- A skill execution launcher.
- A replacement for the Skills Library.
- A replacement for `skill-turial`.

## Open Notes

- Product spelling note: the user referred to `skill-turial`; implementation and copy should follow the actual existing VO naming if it differs.
