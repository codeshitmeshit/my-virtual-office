# Archive Room Phase 6 Requirement

## Background

Archive Room Phase 1-5 has established the module, project archive browsing, artifact preview, archive manager lifecycle, event-triggered maintenance, scheduled inspection, important message intake, maintenance records, and basic pending confirmation data.

The remaining Phase 6 problem is that archive data is still too mechanical. A human can see summaries and entries, but may not understand what the archive is for, what information is inside it, what will be added later, or how humans and AI agents should use it. New AI agents also need project-specific onboarding and task context, not generic archive text.

## Goal

Make project archive data useful to humans and AI agents.

Phase 6 should let a human open a project archive and quickly understand the project identity, archive purpose, available information, missing information, and practical uses. It should also let AI agents obtain concise, source-backed, project-characterized onboarding and task context without reading all raw chat history.

## Target Users

- Human project owner or reviewer opening Archive Room to understand project status, artifacts, risks, and handoff readiness.
- Newly added AI agent that needs a standard project onboarding context.
- Execution AI working on a specific task that needs relevant project and task context.
- Archive manager that prepares reminders about conflicts, stale context, or missing context for execution AI.

## Clarified Product Decisions

- Phase 6 serves both humans and AI. Human readability and AI onboarding are both success criteria.
- The archive detail first screen should combine project identity, archive purpose, archive completeness, and available actions.
- "What is in this archive" should be organized both by content type and by usage purpose:
  - Content type: basic information, tasks, artifacts, decisions, risks, meetings, important messages, pending confirmations.
  - Usage purpose: human acceptance, handoff, execution tracking, risk governance, AI onboarding, and AI context query.
- AI onboarding should prioritize task-level dynamic context. It should start from the current task's goals, dependencies, decisions, risks, and artifacts, then add project background.
- Phase 6 does not add a free-form human "ask Archive Room" UI. Human-facing work focuses on readable information maps. AI context query is an internal/system-facing capability.
- Archive manager reminders are graded:
  - Ordinary missing context appears when AI requests context.
  - Severe conflicts can proactively remind execution AI.
- Same AI working on different projects should receive different project-characterized context. This context should reflect project-specific business background, goals, confirmed rules, user preferences, decision style, important history, risks, and artifacts.
- Project-characterized context must not rewrite the AI's global identity, safety boundaries, or general tool rules.

## Scope

### Human-Readable Archive Introduction

- Add an archive introduction section to project archive detail.
- Explain what this project archive is for.
- Explain what information is currently available in the archive.
- Explain what information will be added in future maintenance.
- Explain how humans and AI agents can use it.
- Avoid generic marketing copy. The section should reflect the current project's actual data.

### Project Basic Information

- Show project basic information before mechanical summaries.
- Include project name, description, status, task progress, recent update time, long-term maintenance state, active AI or participants when available, artifact count, pending confirmation count, and major source types.
- Missing fields should display "暂无" / "未记录" style copy, not imply confirmed absence.

### Archive Information Map

- Show what content types are present or missing.
- Show archive usage purposes:
  - human review and acceptance
  - handoff
  - AI onboarding
  - task execution context
  - risk or stale context governance
  - artifact browsing
- Show archive completeness or readiness in a product-readable way, without pretending that inferred content is confirmed.

### Standard AI Onboarding Package

- Provide a standard project onboarding package.
- Include project goal, current state, key rules, current task context when available, key decisions, risks/blockers, related archive index, artifacts, source references, and missing/uncertain context.
- The package should be concise and structured enough to copy or feed into another AI.

### Task-Level AI Context

- Provide task-first onboarding/context.
- Start with the current task's goal, relevant dependencies, prior decisions, known risks, blockers, related artifacts, and source references.
- Then include enough project background to avoid loss of context.
- Avoid loading all raw history by default.

### Project-Characterized AI Context Injection

- Provide project/task context that changes based on the current project.
- Include project-specific business background, confirmed rules, user preferences, decision style, important history, risks, and relevant artifacts.
- Keep the context as a project/task supplement, not a replacement for the AI's global identity, safety rules, or tool rules.

### AI Context Query Shape

- Provide a context query behavior for AI/system use.
- Return most relevant conclusions first.
- Include source references after conclusions.
- Include optional archive entries or artifacts that can be loaded next.
- Include confidence and stale/pending markers where relevant.

### Archive Manager Reminders

- Support archive manager reminders for execution AI when context conflicts, missing context, or stale decisions matter.
- Severe conflicts may proactively remind execution AI.
- Ordinary missing context should be returned as part of context query, not interrupt execution.

## Non-Goals

- No full human free-form "ask Archive Room" chat UI in this phase.
- No Phase 7 confirmation queue governance UI, batch confirmation, or confirm/reject/defer workflows beyond existing data display.
- No rewriting AI global identity, core safety boundaries, or generic tool rules.
- No raw history dumping as an onboarding package.
- No replacing existing project detail pages or task execution flows.

## Success Criteria

- Human users can open a project archive and understand what the archive represents, what it contains, what is missing, and how to use it.
- New AI agents can start with a concise project onboarding package.
- Execution AI can obtain task-level context without reading all raw chat history.
- Same AI receives meaningfully different context for different projects or tasks.
- Archive manager reminders help with severe conflicts without creating noisy interruptions.
