# VO Project Template Editing Next Phase

## Current State

Project templates are currently reusable snapshots, not editable product objects.

- Built-in templates can be listed and used, but not changed.
- User templates can be saved from an existing project, used to create a project, or deleted.
- Agent-created reusable and recurring templates are immutable version snapshots.
- There is no template editor UI and no API for updating an existing template in place.

This is intentional for the current direct-authoring phase because immutable versions keep recurrence and historical project provenance stable. However, the product experience is incomplete: users reasonably expect a template to be something they can create and edit directly.

## Next Phase Goal

Turn project templates into first-class editable objects while preserving version safety for existing projects and recurrences.

The next phase should support:

- Creating a new template directly from the UI, without first creating a normal project.
- Editing template metadata such as title, description, tags, and intended project type.
- Editing columns in a template, including add, rename, reorder, recolor, and delete.
- Editing task blueprints in a template, including title, details, acceptance criteria, priority, column, responsible actor, executor actor, and reviewer policy.
- Managing template versions so existing project instances and recurring schedules remain pinned to the version they were confirmed against.
- Letting users decide whether a change updates a draft/new version, publishes a new version, or remains unpublished.
- Allowing Agent-authored reusable or recurring templates to be opened in the same editor after creation.

## Product Semantics

Templates should become editable sources, while published template versions remain immutable.

- A template is the editable container users see in the UI.
- A template version is an immutable snapshot used by project creation and recurrence.
- Editing a template should not silently change existing projects.
- Editing a template should not silently change active recurring schedules unless the user explicitly updates the schedule to a new version.
- Creating a project from a template should record the exact `templateId` and `version`.
- Agent-created templates should be labeled with their source proposal and authoring Agent, but should still be editable by trusted users.

## Required UX

The template surface should include:

- A template list with built-in, user-created, and Agent-created labels.
- A create-template flow for an empty template or a template copied from an existing project.
- A template detail/editor page.
- A visible published version number and unpublished-change state.
- A publish-new-version action with a diff/summary confirmation.
- A create-project-from-template action.
- A delete/archive action with appropriate safeguards.

For Agent-created reusable or recurring templates, the UI should make clear whether the current edited template version is the one used by a recurrence.

## Required Backend Changes

Likely backend work:

- Add template create/update endpoints for editable template containers.
- Add explicit publish-version endpoint that snapshots the editable template into immutable `projectTemplateVersions`.
- Add read APIs for template detail, versions, and version diff/summary.
- Add validation for actor references, reviewer policy, columns, task blueprints, recurrence compatibility, and workspace/execution settings.
- Add migration/compatibility handling for existing legacy `templates` and `projectTemplateVersions`.
- Keep existing template instantiation and recurrence pinned-version behavior compatible.

## Open Questions

- Should built-in templates become editable copies, or remain read-only with a "duplicate" action?
- Should template edits require management authentication only, or can scoped Agent grants propose template changes?
- Should recurring schedules auto-suggest upgrading to a newer template version, or require manual discovery?
- Should a template support multiple project types, or should each template have one intended type?

