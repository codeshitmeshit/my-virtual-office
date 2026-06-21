# Archive Room Phase 4 Requirement

## Background

Archive Room Phase 1-3 has been accepted and archived. The product now has a first-level Archive Room entry, durable project archive records, project overview/detail views, onboarding packages, explicit task artifact visibility, source references, and document/image/video/audio preview.

The full Archive Room product also requires a global archive management AI. Phase 4 focuses only on the lifecycle, identity, visibility, controls, and degraded behavior of that AI. It does not attempt to deliver full automatic archive maintenance, event-triggered整理, daily inspections, AI context query, or confirmation governance.

## Goal

Make the global OpenClaw-based archive management AI real, visible, controllable, and safe to operate.

Users should be able to understand whether the archive manager exists, whether it was automatically created, whether it is idle/working/paused/error, and what recent lifecycle actions happened. If creation fails, Archive Room must remain usable in a read-only degraded mode.

## Users

- Human project owner or operator using Archive Room.
- Human operator watching the Virtual Office main office and agent list.
- Future execution AI agents, indirectly, because the archive manager must have a stable identity before later AI-to-AI reminders and context workflows are added.

## Product Decisions

- The archive manager is one global OpenClaw agent, not one agent per project.
- Default user-facing name: `档案管理员`.
- The agent should be dual-visible:
  - Archive Room shows the global archive manager status and controls.
  - The main office also shows it as a real Agent so the system is transparent.
- If the archive manager does not exist, Phase 4 should automatically create it and show `已自动创建`.
- The agent cannot be deleted from Archive Room. Users can pause and resume it.
- When paused, the office still shows the agent, with a paused state rather than hidden or offline.
- The agent is not a general execution AI:
  - It should not be assignable to normal project tasks.
  - It may chat only about archive-related topics, with clear user-facing feedback when a request is out of scope.
- The agent's prompt/persona files must be explicit and product-controlled:
  - `agent.md`, identity, soul, and prompt-related files must describe its archive-management role, work style, personality boundaries, and output discipline.
  - Its normal work output must be strict, structured, and machine-recognizable so Virtual Office can parse, persist, and render it.
  - Free-form prose may be used only where the receiving VO surface expects human-readable explanation; actionable maintenance output should use controlled fields and stable labels.
- Pause means no proactive archive maintenance, but users may still manually trigger one整理 for the currently open project.
- Manual整理 in Phase 4 is limited to the current project and does not imply event-triggered, startup, daily, or all-project maintenance.
- Recent maintenance activity should be shown as a short log, including creation, auto-creation, start, pause, resume, manual整理, and failures.

## Scope

### Included

- Detect whether the global archive manager agent exists.
- Automatically create the archive manager when missing.
- Display archive manager status in an Archive Room top-level status bar:
  - missing
  - auto-created
  - idle
  - working / 整理中
  - paused
  - error
- Show a lightweight project-detail notice when the manager is paused, explaining archive freshness may not update automatically.
- Provide pause and resume controls.
- Provide current-project manual整理 control.
- Record recent lifecycle and maintenance activity.
- Keep Archive Room project overview/detail/artifact views read-only usable if manager creation or manager actions fail.
- Make the archive manager visible in the main office as a real agent.
- Prevent or clearly block normal project task assignment to the archive manager.
- Restrict direct chat with the archive manager to archive-related topics, with clear feedback for out-of-scope requests.
- Define and validate archive manager prompt/persona files, including `agent.md`, identity, soul, work style, personality boundaries, and structured output rules.
- Ensure archive manager operational output is controlled enough for VO to recognize, process, persist, and render.

### Out Of Scope

- Event-triggered整理 after task completion, meeting end, blocker, state change, or conflict. This belongs to Phase 5.
- Startup inspection and daily inspection. These belong to Phase 5.
- Important chat classification and user-marked important chat processing. These belong to Phase 5.
- AI onboarding API, AI context query API, and execution AI reminders. These belong to Phase 6.
- Pending confirmation queue, rule approval/rejection workflow, and confirmed-fact overwrite governance. These belong to Phase 7.
- Full maintenance diff, complete observability log stream, or detailed archive-quality scoring.
- Deleting the archive manager from Archive Room.
- Assigning the archive manager as a normal execution/review agent for project tasks.

## Success Criteria

- A missing archive manager is automatically created and surfaced as `已自动创建`.
- Users can see the global archive manager status from Archive Room without opening a project.
- Users can pause and resume the manager.
- Paused state is visible both in Archive Room and the main office.
- Users can manually trigger one整理 for the current project.
- Recent lifecycle/maintenance records are visible.
- Creation/action failure does not break Archive Room; existing archives remain readable.
- The archive manager is visible as a real Agent but protected from normal task assignment and non-archive chat usage.
