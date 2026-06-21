# Phase 7 Artifact Management Review

## Review conclusion

Reviewed with no blocking product or technical questions. The clarified requirement is narrow and fits the existing Phase 7 Project Execution model because projects already own a validated workspace binding and tasks already keep execution evidence.

The recommended delivery is a read-only Markdown artifact manager implemented as reusable artifact infrastructure plus a Phase 7 Project Execution adapter. It should list Markdown files in the bound workspace, show basic metadata, derive evidence-backed source records from existing task evidence, and provide a Markdown preview/source viewer. The reusable layer should be suitable for later meeting artifacts without implementing the meeting adapter in this phase.

## Product review

The product scope is coherent:

- The feature supports task acceptance and result review rather than generic document management.
- Limiting this phase to Markdown avoids unclear handling for images, PDFs, HTML, archives, logs, and data files.
- Preview plus raw source covers both normal reading and technical verification.
- Read-only behavior avoids introducing destructive or editorial workflows before artifact review is proven useful.
- A reusable artifact-management core is justified because meetings are likely to generate the same kind of Markdown outputs: minutes, decisions, action items, and agent-written summaries.

No further product clarification is required before checklist confirmation.

## Technical review

### Reusable artifact architecture

The implementation should separate:

- Artifact core: bounded Markdown discovery, safe path resolution, Markdown read, file metadata, and generic source-record shape.
- Context adapter: resolves the business context into allowed roots, source records, labels, and availability. The first adapter is Project Execution project artifacts.
- UI component/view: renders artifact list, source records, Markdown preview/source tabs, empty state, and errors without hardcoding Project Execution-specific assumptions.

For Phase 7, the context adapter maps a project to its validated workspace and maps task evidence into source records. A future meeting adapter should be able to map a meeting to its artifact directory or artifact collection and map meeting provenance into the same source-record display model.

### Workspace and access model

Project artifact management should be available only for projects with Project Execution enabled and a valid workspace. The workspace validation rules from Phase 7 should remain the source of truth.

The reusable artifact APIs must canonicalize paths and reject traversal or symlink escape attempts based on adapter-provided roots. The feature must not become a general filesystem browser.

### Artifact discovery

Discovery should scan only Markdown extensions:

- `.md`
- `.markdown`

The scan should skip noisy directories such as VCS metadata, dependencies, virtual environments, build caches, and test caches. It should also apply bounded result counts and depth limits so large repositories remain usable.

Only Markdown files should be displayed in this phase. Non-Markdown files should not appear as disabled rows, because the user explicitly narrowed the current scope to Markdown-only display.

### Markdown read behavior

Inline read should be limited to Markdown files inside the workspace. The response should include content, path, size, and truncation status when large files exceed the read limit.

Rendered preview can reuse the existing frontend Markdown rendering path where practical. Raw source should show escaped text and must not execute embedded HTML or scripts.

### Source records

Use a generic source record model with context-specific fields. For Phase 7, artifact source records can be inferred from task evidence:

- `evidence.changedFiles`
- attempt evidence changed files
- task title and task ID
- executor agent identity
- provider kind
- attempt ID
- evidence capture or attempt finish timestamp

The UI should show the source task and executor when there is an evidence match. If no match exists, it should explicitly mark the artifact as unassociated. The implementation should not infer authorship from timestamps alone, file content, Git blame, or language guesses.

For future meetings, the same display model can show meeting title, meetingId, agenda item, participant or agent, generated-at time, and source activity. This future adapter is out of scope, but the core shape should not block it.

### Compatibility

The feature should not modify project or task state merely by scanning or reading artifacts. Existing project CRUD, board drag/drop, Project Execution start/review/acceptance, workflow polling, report view, and templates should continue to work.

### Security and privacy

Main risks:

1. Path traversal or symlink escape from the workspace.
2. Accidentally listing Markdown files from dependency directories, producing noise or exposing irrelevant content.
3. Rendering untrusted Markdown as active HTML.
4. Reading very large files into the UI.

Mitigations:

- Use realpath checks against the validated workspace root for listing and reading.
- Skip known noisy directories and bound scan depth/results.
- Render Markdown through safe escaping or a trusted renderer configuration that does not execute scripts.
- Bound read size and mark truncated content.

## API shape recommendation

Exact names can follow current project route conventions. The needed product capabilities are:

- Generic capability: list Markdown artifacts for a business context.
- Generic capability: read one Markdown artifact by relative path or context-scoped artifact ID.
- Generic capability: include source records in the list response.
- Phase 7 adapter: expose the generic capability through project routes or project-scoped handlers.

All operations are read-only and must reject missing projects, disabled Project Execution, invalid workspaces, non-Markdown files, and paths outside the workspace.

## UI shape recommendation

In the project board toolbar, add a compact "Artifacts" / "产物" entry for Project Execution projects. Internally, use a reusable artifact manager view/component so later meeting pages can mount the same component with a meeting adapter.

The artifact view should include:

- Back button to return to the project board.
- Workspace path context.
- Markdown artifact list with path, size, modified time, and source record.
- Source record fields: task title, task ID, executor agent, provider kind, attempt ID, and evidence timestamp when matched.
- Clear unassociated state when no task evidence matches.
- Empty state for no Markdown artifacts.
- Error state for invalid workspace.
- Viewer area with Preview and Source tabs.
- Component options that allow the context label to be "Project" now and "Meeting" later without duplicating the viewer.

The first version does not need filters or search if the list is bounded and sorted by recent modified time.

## Test strategy

Testing should cover:

- Unit-level artifact scanning and safe path resolution.
- Unit-level adapter separation so core artifact logic can be exercised without a Project Execution project.
- API behavior for success, missing project, disabled Project Execution, invalid workspace, non-Markdown read, traversal read, and large-file truncation.
- Source record inference from execution evidence, including executor agent and provider kind.
- Browser-level artifact list and preview/source switching.
- Lightweight component reuse check that verifies the artifact view can render from a generic artifact payload rather than only from project-specific globals.
- Regression for existing Project Execution task execution and project CRUD.

## Non-blocking follow-ups

- Add filters or search if artifact lists become long.
- Add explicit artifact pinning/marking after the read-only model is validated.
- Add non-Markdown artifact display in a later phase if users need visual or packaged deliverables.
