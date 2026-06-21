# Phase 7 Artifact Management

## Background

Phase 7 already makes Virtual Office projects bind to a concrete local workspace and execute tasks through provider-neutral Project Execution. After execution and review, the user needs a project-level way to inspect what useful Markdown artifacts exist in that workspace, especially when agents produce requirement docs, reports, plans, guides, or acceptance notes.

The clarified request is to add artifact management inside the project experience, focused on Phase 7 result review rather than a general file browser. A later clarification adds that this capability should be shaped as a reusable artifact-management core and UI component because future meeting features may also need to manage meeting minutes, decisions, action-item documents, and agent-generated meeting materials.

## Target user

- A Virtual Office user managing a Phase 7 Project Execution project.
- The user is reviewing or accepting work produced by agents in a bound local workspace.
- Future meeting users who need the same artifact list and Markdown viewer pattern for meeting-generated documents.

## Product goal

Let the user open a project, see the Markdown artifacts available in that project's workspace, and view each Markdown artifact as both rendered preview and raw source.

This feature should support task result review and project-level recall without turning Virtual Office into a full file manager. It should be implemented as a reusable artifact-management capability with a Phase 7 project adapter, so future meeting features can reuse the list, source record, Markdown read, and viewer behavior with a meeting-specific adapter.

## Confirmed product decisions

- Primary scenario: task result acceptance and retrospective review.
- Artifact scope for this phase: show Markdown artifacts only.
- Other artifact types are out of scope for this phase and should not be listed.
- Markdown viewing must support rendered preview and raw source mode.
- Artifact management is project-level, and each artifact must show source information when Phase 7 execution evidence can identify the task and agent that generated or modified it.
- Artifact management should be a generic capability with scenario adapters. Phase 7 Project Execution is the first adapter; meetings are an expected later adapter.
- First-version success criterion: a user can see the project's Markdown artifact list and open Markdown content for viewing.

## In scope

1. Add a reusable artifact-management core that can list Markdown artifacts, read Markdown content, enforce path boundaries, and return source records without depending on Project Execution task-board details.
2. Add a reusable frontend artifact manager view/component that can display artifact lists, source records, preview/source tabs, empty states, and errors for different business contexts.
3. Add a Phase 7 Project Execution adapter that binds the generic artifact core to a project workspace.
4. Add a project-level artifact entry point for Project Execution projects.
5. List Markdown files from the project's bound workspace.
6. Exclude dependency, cache, VCS, and internal noise directories from the list.
7. Show useful metadata for each Markdown artifact, such as path, file name, size, and modified time.
8. Show source information when an artifact appears in task execution evidence or changed-file records, including source task, executor agent, provider kind, attempt ID, and evidence timestamp when available.
9. Let the user open a Markdown artifact from the list.
10. Provide rendered Markdown preview.
11. Provide raw Markdown source view.
12. Keep the view read-only in this phase.
13. Clearly mark artifacts with no matching Phase 7 execution evidence as unassociated rather than guessing their origin.
14. Preserve existing Project Execution execution, review, rework, acceptance, and board behavior.
15. Keep the extension point clear enough that a future meeting adapter can provide meetingId, meeting title, participant/agent source, and meeting artifact roots without duplicating the artifact list/viewer logic.

## Out of scope

- Listing non-Markdown artifacts such as images, PDFs, HTML, archives, logs, JSON, CSV, or office documents.
- Editing, renaming, deleting, uploading, moving, tagging, or approving artifacts.
- Download or export packaging.
- Full-text search across artifacts.
- Artifact version history or diff view.
- Strong task-to-artifact ownership guarantees when the file is not present in Phase 7 execution evidence.
- Inferring authorship from file content, timestamps alone, Git blame, or natural-language guesses.
- Cross-project artifact library.
- Implementing the meeting artifact adapter or meeting UI in this phase.
- Automatic Git commit, push, publish, or deploy.

## Product constraints

- Artifact management must only operate within the project's configured workspace.
- The feature must not expose arbitrary filesystem browsing.
- The user should understand when the feature is unavailable because no workspace is configured or the workspace is invalid.
- The artifact list should avoid overwhelming the user with unrelated Markdown files from dependencies or caches.
- Source information must be evidence-backed. If evidence does not identify the source task and agent, the artifact must be marked as unassociated.
- The generic artifact layer must not encode Project Execution task assumptions that would prevent a later meeting adapter from using it.

## Success criteria

The feature succeeds when a Phase 7 Project Execution user can:

1. Open a project with a valid workspace.
2. Open artifact management from that project.
3. See Markdown files that are likely project artifacts.
4. Identify each artifact by path, size, and modified time.
5. See the source task, executor agent, provider, attempt, and evidence time when the artifact is matched to Phase 7 evidence.
6. Open an artifact and switch between rendered preview and raw Markdown source.
7. Understand when a Markdown artifact is unassociated with any recorded Phase 7 task.
8. Reuse a generic artifact manager component/API shape from the Phase 7 project integration without duplicating the main list/read/viewer logic.
9. Refresh or reopen the project without losing normal Project Execution behavior.
