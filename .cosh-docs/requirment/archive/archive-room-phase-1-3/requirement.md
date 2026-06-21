# Archive Room Phase 1-3 Requirement

## Background

The full Archive Room product has been clarified as an independent first-level Virtual Office module that turns project activity, task results, important context, and artifacts into durable project archives. This sub-requirement covers only Phase 1 through Phase 3 so implementation and acceptance can proceed in a smaller, independently testable scope.

Phase acceptance is an implementation and checklist organization method only. Archive Room itself does not need to provide a built-in phase acceptance workflow in this sub-requirement.

## Scope

### Phase 1: Archive Data Foundation

Goal: establish durable archive records under existing VO storage.

Included:

- Define durable project archive files under `VO_STATUS_DIR`.
- Store project overview data, confidence levels, source references, stale flags, pending confirmation counters, and artifact metadata.
- Derive initial archive data from existing project and task records where available.
- Keep source references to raw project/task/chat/meeting data instead of duplicating full raw history.
- Ensure archive data survives server restart.

### Phase 2: Archive Room Main Navigation And Project Overview

Goal: make Archive Room visible and useful as a first-level app module.

Included:

- Add "档案室" as a first-level main application entry.
- Build the Archive Room project overview list.
- Show project status metrics: project name, current status, task count, completion rate, risk count, pending confirmation count, active AI, last updated time, and artifact count when available.
- Default ordering prioritizes risk and pending confirmation, then recent update.
- Show empty state when there are no projects or no archive data.
- Show only a minimal archive management AI placeholder state, such as "后续阶段启用" or "未接入". Phase 1-3 must not auto-create, pause, resume, or operate the archive management AI.

### Phase 3: Project Archive Detail And Artifact Preview

Goal: let humans inspect one project's archive and artifacts.

Included:

- Add project archive detail view reachable from the overview.
- Show current state, goals or summary, key decisions, risks and blockers, long-lived rules, onboarding/context summary, and source/timeline references when available.
- Show a human-readable standard onboarding package that users can view and copy. It prepares for future AI onboarding but does not provide automatic AI loading in Phase 1-3.
- Show task artifacts and associated files with metadata. Phase 1-3 only covers artifacts explicitly associated with a project or task, such as task reports, test results, delivery documents, and associated files.
- Support preview behavior for common artifact types:
  - Documents readable or openable.
  - Images previewable.
  - Videos playable when browser-supported.
  - Audio playable when browser-supported.
  - Other attachments downloadable or openable.
- Show source references and confidence level for important archive entries.

## Non-Goals

- Archive management AI lifecycle, auto-creation, pause/resume, active maintenance status, and maintenance records. These belong to later phases. Phase 1-3 may show only a minimal future-state placeholder.
- Event-triggered整理, startup inspection, daily inspection, and important chat classification. These belong to later phases.
- AI automatic onboarding, AI onboarding API, AI context query API, and archive manager reminders to execution AI. These belong to later phases.
- Pending-confirmation approval workflow beyond displaying counts or existing data.
- Built-in Phase acceptance inside Archive Room.
- Replacing the existing Projects module, task workflow, chat logs, meeting history, or provider-native histories.
- Rich preview for every binary, archive, or proprietary file format.
- Treating every project workspace file, chat attachment, or meeting attachment as an artifact without explicit project/task association.

## Users

- Human project owner or operator who needs to see project status and artifacts.
- New or active AI agents are important future users, but Phase 1-3 only prepares the archive data and human-facing views.

## Product Rules

- Archive Room is a first-level module, not only a project detail tab.
- Phase 1-3 must use durable storage under `VO_STATUS_DIR`.
- Archive entries should be high-signal summaries and metadata, not a full dump of every conversation.
- Important archive entries should carry confidence level:
  - Confirmed fact.
  - AI inference.
  - Pending confirmation suggestion.
- Source references are required when an entry is derived from another record and the source is available.
- Stale or outdated context should be retained and marked instead of silently removed.
- Artifact preview must respect allowed storage roots and must not expose arbitrary local files.

## Success Criteria

- Humans can open Archive Room from the main app.
- Humans can see all projects in a project overview and quickly identify risk, pending confirmation, recent update, and artifact availability.
- Humans can open one project archive and inspect key context plus task artifacts.
- Humans can view and copy a standard onboarding package, but Phase 1-3 does not validate automatic AI onboarding.
- Common media artifacts, including video and audio, are usable from Archive Room when browser-supported.
- Archive records survive service restart.
- Existing project, task, chat, and meeting flows continue to work.
