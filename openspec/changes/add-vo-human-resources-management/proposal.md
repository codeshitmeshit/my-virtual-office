## Why

Virtual Office can discover and run many system, project, and externally connected Agents, but it has no authoritative Agent directory, daily work record, evidence-backed workload feedback, or controlled way for Agents to inspect one another's public work information. A VO-level HR capability is needed so humans and Agents can understand who is available, what each Agent does, what work occurred each day, and where an Agent may need support without turning the system into a numeric ranking or punitive performance tool.

## What Changes

- Add one globally unique VO system Agent named `HR`, created before it manages ordinary Agent records, with visible lifecycle state, pause/resume controls, degraded behavior, explicit role boundaries, and eligibility to join ordinary meetings.
- Extract the reusable lifecycle behavior currently embedded in Archive Room's archive manager into a focused VO system-Agent lifecycle boundary, then use it for both the archive manager and HR while preserving all archive-manager behavior.
- Add an HR-owned directory for every discoverable system, project, and externally connected Agent, keyed by stable AI ID and retaining inactive Agent history, plus a manual information-completion action that asks only currently available Agents whose introduction is missing.
- Add a VO built-in `vo-agent-hr` skill, exposed from the current office's `/skills` catalog, that lets every Provider query the HR Agent roster, each Agent's concise HR-coordinated introduction, AI ID, availability, permitted work information, and self access history without copying the skill into Agent workspaces.
- Merge Human Resources into one shared `Agent 管理` surface with peer `代理配置` and `人事运营` tabs, one roster and preserved Agent selection, while keeping human full views and ordinary-Agent public/self views server-authorized.
- Add self-service Agent configuration in the shared surface: low-risk identity, responsibility/specialty, and appearance changes apply immediately with automatic-save feedback and undo, while Provider, branch, workspace, and Agent-binding changes remain human-admin-only and require explicit confirmation.
- Replace long appearance option lists with compact current-value selectors whose dropdowns expose visual option grids, update the Agent preview immediately, and close after selection.
- Add a global daily collection cycle in which HR asks each eligible Agent what it did, preserves the raw response, produces a normalized report, marks non-response without negative inference, and accepts late submission.
- Add a management-only `日报` correction action with an available-Agent selection dialog, select-all and individual selection, explicit same-day report replacement, and immediate reassessment of every successfully refreshed Agent.
- Add an HR-only daily assessment that combines reports with traceable task, meeting, artifact, and execution evidence to produce structured feedback and a non-numeric workload level without ranking Agents.
- Add field-level disclosure rules: humans and HR can read full records; ordinary Agents can read only another Agent's public profile, public work summary, availability, and workload level through a controlled query surface.
- Add best-effort access auditing for ordinary Agent cross-Agent reads using the trusted VO-internal caller AI ID, while exempting HR and human reads; allow HR, humans, and the viewed Agent to inspect the applicable audit history.
- Preserve inactive, disabled, or deleted Agent history while stopping future daily collection and assessment until the Agent becomes eligible again.
- Require strict unit and regression coverage for shared lifecycle behavior, Archive Room compatibility, HR workflows, authorization, scheduling, idempotency, failure isolation, and access audit rules.
- Require mandatory end-to-end regression on an approved development machine with a real OpenClaw environment. Evidence must start from the merged Agent Management UI and traverse management authentication, real APIs, background commands, Provider/Agent communication, persistence, restart or recovery, and refreshed UI results; unit, API, static, or smoke tests cannot substitute for this gate.

## Capabilities

### New Capabilities

- `vo-system-agent-lifecycle`: Reusable, role-configured creation, discovery, profile synchronization, status, pause/resume, protection, activity, and degraded behavior for the archive manager, HR, and future VO system Agents.
- `hr-agent-directory`: HR lifecycle, Agent discovery, stable Agent records, HR-coordinated introductions, availability, and the global `vo-agent-hr` skill.
- `hr-daily-reporting`: Fixed daily collection cycles, raw and normalized Agent reports, non-response, late submission, idempotency, and failure isolation.
- `hr-performance-assessment`: Evidence-backed, HR-authored daily contribution, workload, blocker, improvement, runtime-state, and confidence feedback without scores or ranking.
- `hr-information-governance`: Human, HR, and ordinary-Agent disclosure boundaries, controlled cross-Agent reads, audit logging, and audit-log visibility.
- `hr-management-experience`: Unified Agent Management navigation, shared roster/selection, audience-specific configuration and Human Resources tabs, automatic-save configuration, HR status, reports, assessments, history, failure, degraded-read, and mandatory development-machine end-to-end experiences.

### Modified Capabilities

- `meeting-collaboration-service-boundaries`: Preserve archive-manager exclusion while explicitly allowing the HR system Agent to participate as an ordinary eligible meeting participant without making attendance an automatic performance event.

## Impact

- System-Agent integration: archive-manager discovery/creation/profile/status code, OpenClaw gateway interactions, system-role metadata, and future system-Agent extension points.
- Human Resources domain: new focused modules for the directory, daily collection, assessment, information governance, persistence, scheduling, and transport delegation.
- Meeting domain: participant eligibility must distinguish the meeting-ineligible archive manager from meeting-eligible HR.
- Project and execution surfaces: HR and the archive manager remain unavailable for ordinary task assignment; task, meeting, artifact, and execution records are read as assessment evidence without transferring ownership to HR.
- UI and localization: one Agent Management surface with configuration and Human Resources tabs, shared roster/selection, audience-specific Agent detail views, automatic-save controls, compact visual dropdowns, status and workflow states, disclosure-safe Agent views, and access-history presentation.
- Runtime skill exposure: one repository-owned `vo-agent-hr` skill in the VO built-in catalog, backed by current safe public HR APIs rather than per-Agent workspace copies or Provider-specific credentials.
- Persistence and APIs: durable Agent profiles, reports, assessments, schedules, lifecycle activity, and access logs plus controlled query and management surfaces.
- Compatibility: Archive Room lifecycle, profile, assignment, meeting exclusion, maintenance, and degraded-read behavior must remain unchanged after extraction.
- Verification: deterministic fake-provider unit tests and regression suites locally, followed by mandatory real-OpenClaw development-machine end-to-end evidence from browser action through persisted and rendered result before the change can pass the test-result gate.
