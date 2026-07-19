## Why

Virtual Office can discover and run many system, project, and externally connected Agents, but it has no authoritative Agent directory, daily work record, evidence-backed workload feedback, or controlled way for Agents to inspect one another's public work information. A VO-level HR capability is needed so humans and Agents can understand who is available, what each Agent does, what work occurred each day, and where an Agent may need support without turning the system into a numeric ranking or punitive performance tool.

## What Changes

- Add one globally unique VO system Agent named `HR`, created before it manages ordinary Agent records, with visible lifecycle state, pause/resume controls, degraded behavior, explicit role boundaries, and eligibility to join ordinary meetings.
- Extract the reusable lifecycle behavior currently embedded in Archive Room's archive manager into a focused VO system-Agent lifecycle boundary, then use it for both the archive manager and HR while preserving all archive-manager behavior.
- Add an HR-owned directory for every discoverable system, project, and externally connected Agent, keyed by stable AI ID and retaining inactive Agent history, plus a manual information-completion action that asks only currently available Agents whose introduction is missing.
- Add a VO built-in Agent-directory skill, exposed from the current office's `/skills` catalog, that lets every Provider query each Agent's name, concise HR-coordinated introduction, AI ID, and availability without copying the skill into Agent workspaces.
- Add a first-level Human Resources module, modeled on Archive Room's navigation and degraded-read behavior, with HR status, Agent roster, daily reports, assessments, and relevant access history.
- Add a global daily collection cycle in which HR asks each eligible Agent what it did, preserves the raw response, produces a normalized report, marks non-response without negative inference, and accepts late submission.
- Add an HR-only daily assessment that combines reports with traceable task, meeting, artifact, and execution evidence to produce structured feedback and a non-numeric workload level without ranking Agents.
- Add field-level disclosure rules: humans and HR can read full records; ordinary Agents can read only another Agent's public profile, public work summary, availability, and workload level through a controlled query surface.
- Add access auditing for ordinary Agent cross-Agent reads, while exempting HR and human reads; allow HR, humans, and the viewed Agent to inspect the applicable audit history.
- Preserve inactive, disabled, or deleted Agent history while stopping future daily collection and assessment until the Agent becomes eligible again.
- Require strict unit and regression coverage for shared lifecycle behavior, Archive Room compatibility, HR workflows, authorization, scheduling, idempotency, failure isolation, and access audit rules.
- Require post-implementation validation on a development machine with a real OpenClaw environment because local tests will use injected fakes and cannot establish provider integration correctness.

## Capabilities

### New Capabilities

- `vo-system-agent-lifecycle`: Reusable, role-configured creation, discovery, profile synchronization, status, pause/resume, protection, activity, and degraded behavior for the archive manager, HR, and future VO system Agents.
- `hr-agent-directory`: HR lifecycle, Agent discovery, stable Agent records, HR-coordinated introductions, availability, and the global Agent-directory skill.
- `hr-daily-reporting`: Fixed daily collection cycles, raw and normalized Agent reports, non-response, late submission, idempotency, and failure isolation.
- `hr-performance-assessment`: Evidence-backed, HR-authored daily contribution, workload, blocker, improvement, runtime-state, and confidence feedback without scores or ranking.
- `hr-information-governance`: Human, HR, and ordinary-Agent disclosure boundaries, controlled cross-Agent reads, audit logging, and audit-log visibility.
- `hr-management-experience`: First-level Human Resources navigation, HR status, roster, daily report, assessment, history, failure, and degraded-read experiences.

### Modified Capabilities

- `meeting-collaboration-service-boundaries`: Preserve archive-manager exclusion while explicitly allowing the HR system Agent to participate as an ordinary eligible meeting participant without making attendance an automatic performance event.

## Impact

- System-Agent integration: archive-manager discovery/creation/profile/status code, OpenClaw gateway interactions, system-role metadata, and future system-Agent extension points.
- Human Resources domain: new focused modules for the directory, daily collection, assessment, information governance, persistence, scheduling, and transport delegation.
- Meeting domain: participant eligibility must distinguish the meeting-ineligible archive manager from meeting-eligible HR.
- Project and execution surfaces: HR and the archive manager remain unavailable for ordinary task assignment; task, meeting, artifact, and execution records are read as assessment evidence without transferring ownership to HR.
- UI and localization: a first-level Human Resources module, Agent detail views, status and workflow states, disclosure-safe Agent views, and access-history presentation.
- Runtime skill exposure: one repository-owned Agent-directory skill in the VO built-in catalog, backed by current safe public roster APIs rather than per-Agent workspace copies.
- Persistence and APIs: durable Agent profiles, reports, assessments, schedules, lifecycle activity, and access logs plus controlled query and management surfaces.
- Compatibility: Archive Room lifecycle, profile, assignment, meeting exclusion, maintenance, and degraded-read behavior must remain unchanged after extraction.
- Verification: deterministic fake-provider unit tests and regression suites locally, followed by mandatory real-OpenClaw development-machine acceptance evidence before the change can pass the test-result gate.
