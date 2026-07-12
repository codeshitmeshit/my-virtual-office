# Confirmed scenario evidence

This matrix maps every scenario in `specs/project-execution-service-boundaries/spec.md` to current implementation and verification evidence. Test file names identify executable coverage; manual/rehearsal documents provide runtime evidence where appropriate.

| Requirement / scenario | Implementation evidence | Verification evidence |
|---|---|---|
| Incremental extraction — migrated slice | Thin delegates in `app/server.py`; six modules under `app/services/` | `test_project_execution_service_boundary.py`, adapter contracts in `test_project_commands.py`, `test_execution_lifecycle.py` |
| Incremental extraction — unresolved slice remains | Legacy `_wf_*` orchestration remains outside migrated ownership | Static boundary test and `docs/SERVICE_BOUNDARIES.md` non-goal |
| Explicit dependencies — service without HTTP | Dataclass/callable ports in lifecycle, review, artifact, schedule, repository modules | Direct service suites for each module; static import checks |
| Project/task compatibility — valid operation | `project_commands.py` plus handler adapters | `test_project_commands.py`, old Markdown round trips, workflow E2E 20/20 |
| Project/task compatibility — invalid input | Command validation before repository update | Invalid-input and no-partial-mutation cases in `test_project_commands.py` |
| Lifecycle — eligible start | Persist-before-launch and active-attempt token in `execution_lifecycle.py` | Lifecycle and Project Execution start/transition tests; manual native execution |
| Lifecycle — rejected gate | Eligibility/workspace checks precede launcher | Lifecycle gate matrix and dirty confirmation tests |
| Lifecycle — Git snapshot failure | Fail-closed result `workspace_git_snapshot_failed` | Focused tests plus manual HTTP 409 reproduction |
| Lifecycle — non-Git workspace | Directory snapshot path remains allowed | Lifecycle non-Git cases |
| Lifecycle — Provider failure | Compare-and-commit failure/cleanup branches | Provider exception, cancel, retry, and runner intermediate tests |
| Review — enters review | Review start validates attempt/reviewer and commits reviewing first | `test_review_acceptance_service.py`, `test_project_execution.py` |
| Review — rework | Linked attempt, feedback, bounded rework, notification intent | Review/rework limit and notification tests; manual `reviewing → reworking → execution_complete` chain with linked feedback |
| Review — repeated acceptance | Stable attempt linkage and one acceptance history/intent | HTTP/Feishu repeat tests; manual first 200 then stable 409 with one history item |
| Artifact — valid request | `artifacts.py` opened-file context, limits, and handler streaming | `test_artifact_service.py`; manual 13-byte inline and streamed artifact |
| Artifact — escape rejection | Explicit absolute-root validation, realpath containment, no-follow/fstat, associated-only policy | Missing/relative-root, traversal, symlink-swap, non-regular-file, limit tests |
| Scheduling — due task | `project_schedule.py` occurrence claim, Gateway/binding/execution ports, exception-safe release | Schedule service and Cron phase 1–5/idempotency/failure-retry suites |
| Scheduling — ineligible task | Pause/archive/active/done skip rules | Cron skipped/paused/archived/repeat cases |
| Scheduling — restart recovery | Persisted bindings/history, lease and occurrence reconciliation | Recovery/replay/lease tests; medium-fixture rollback boot |
| Atomicity — same project | Ref-counted project lock plus atomic repository update | Repository writer races and final concurrent compatibility-log regression/manual 200+200 |
| Atomicity — different projects | Per-project locks with short shared commit lock | Different-project barrier/concurrency tests |
| Atomicity — slow dependency | External calls outside locks, compare token on return | Execution/review/notification/Gateway race tests |
| API/event/storage compatibility | Thin HTTP adapters and Markdown store preserved | Full 505 Python, 23 JavaScript, workflow, SSE/WebSocket, notification suites |
| Defect — confirmed active-slice bug | Fail-closed Git snapshot, reviewer workspace binding, atomic compatibility log | Failing-before/API/manual reproductions and regression tests; documented in manual acceptance |
| Defect — untrusted mutation | Management guard before body parsing | Token boundary and sensitive-data tests; manual 403 |
| Defect — meeting request agent bridge | Dedicated validated meeting-request command remains exempt from browser token | Meeting request/blocker/linkage tests |
| Defect — managed workspace deletion | Root/descendant/symlink checks | Managed deletion safety cases in execution tests |
| Defect — ambiguous/outside slice | Documented scope and unchanged unrelated orchestration | Service-boundary static/doc contract |
| Performance — migrated persistence | Repository cache/coordinator and measured call counts | `performance-baseline.md`, `performance-result.md`, performance artifact tests |
| Performance — redundant path | Cron project-store loads reduced from 2 to 1 | Fixed harness JSON and `performance-result.md` |
| Performance — noisy timing | Report separates count evidence from noisy elapsed percentiles | Performance report methodology/gates |
| Backend-only experience | No project UI redesign; only test harness token header changed | Git diff plus 23 frontend/static scripts |
| Backend-only — frontend proposal excluded | Ownership/non-goal documented | `docs/SERVICE_BOUNDARIES.md` and static documentation contract |

All rows are covered by current executable evidence or by the explicitly named manual/rehearsal evidence; none relies only on implementation intent.
