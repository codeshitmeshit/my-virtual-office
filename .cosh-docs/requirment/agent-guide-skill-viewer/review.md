# Review: Agent Guide Skill Viewer

## Review Status

Status: reviewed.

The product scope is clear enough to generate a checklist. This phase is limited to read-only viewing of VO built-in exposed skills through an Agent Guide modal with category filtering.

## Product Review

### Clear Points

- The feature is an ability index, not a recommendation engine.
- The displayed scope is limited to built-in VO skills that are exposed by the current Virtual Office instance.
- Information cards are the desired display unit.
- Category filtering is in scope; keyword search is not.
- The center modal is preferred over adding another narrow right-sidebar section.
- Existing Skills Library remains the editable skill management surface.

### Risks And Boundaries

- If the modal shows every globally installed Codex skill, it will violate the user's scope.
- If the modal ranks, recommends, or selects skills for a task, it will overlap with `skill-turial`.
- If the modal is editable, it may confuse users with the existing Skills Library.
- If the source of truth is duplicated manually, the guide can drift from the actual exposed VO skills.

## Technical Review

Technical review found no blocking issue for creating the checklist.

Relevant current surfaces:

- The bottom toolbar lives in `app/index.html`.
- A center modal pattern already exists for Skills Library, meetings, projects, archive room, and agent detail views.
- The Skills Library modal currently uses `skills-library-modal` and related styles in `app/style.css`.
- VO built-in skills are listed in `skills/catalog.md`.
- Built-in skill files exist under `skills/*/SKILL.md`.
- Frontend localization keys already exist in `app/locales/zh.json` and `app/locales/en.json`.

Implementation topics to handle:

- Add a new toolbar button without disturbing existing toolbar layout.
- Add a new read-only Agent Guide modal, visually related to existing modals but distinct from the editable Skills Library.
- Provide stable category filters.
- Ensure cards include name, purpose, triggering / applicable scenarios, and category.
- Determine a VO-owned source for exposed built-in skills:
  - preferred: derive from `skills/catalog.md` or a small VO-owned manifest.
  - acceptable for first phase: static data colocated with the frontend if kept strictly limited to the VO built-in exposed list.
- Avoid loading user-created Skills Library items into the Agent Guide.
- Preserve existing skill editing, agent modal skill panels, and Skills Library behavior.

## Decision

Generate `checklist.md` and wait for user confirmation before creating `todolist.md`.
