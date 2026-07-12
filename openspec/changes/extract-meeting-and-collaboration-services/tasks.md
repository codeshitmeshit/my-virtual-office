## 1. Baseline and writer inventory

- [x] 1.1 Inventory every executable Meeting, request, occupancy, event, idempotency, action-item, notification, callback, recovery, and project-linkage reader/writer; add characterization fixtures and fixed performance baselines for both legacy stores, lifecycle transitions, confirmation/rejection, Agent calls, callback replay, old records, and concurrent operations.

## 2. Unified schema, repository, and migration

- [ ] 2.1 Implement the versioned `meeting-domain.json` schema, `MeetingDomainRepository`, coherent deep-copy snapshot, single atomic update boundary, bounded metadata invalidation, validation/repair rules, namespaced idempotency, and focused repository/concurrency tests proving all Meeting-domain persistence uses the coordinator.
- [ ] 2.2 Implement `scripts/migrate_meeting_store.py` with default dry-run, explicit apply, no-follow source reads, source re-digest, byte backups, deterministic merge, relationship/occupancy/conflict validation, atomic destination validation, JSON report, source-digest idempotency, and failure/rollback tests covering malformed, changing, symlinked, conflicting, disk/replace/fsync, repeated, and already-migrated cases.
- [ ] 2.3 Add the runtime authority gate for valid unified, empty-new, migration-required, invalid, and unknown-version states; migrate legacy Meeting/request store helpers to the unified repository, forbid parallel runtime authority, and run API/storage/old-record/startup compatibility regression.

## 3. Meeting lifecycle and occupancy service

- [ ] 3.1 Extract lifecycle creation, transitions, conflict actions, interventions, agenda/arbitration/moderator operations, Agent turn orchestration, terminalization, timeout, and recovery into `meeting_lifecycle.py` with explicit repository/Agent/clock/ID ports and phase/sequence/call compare tokens; migrate HTTP/internal callers and verify every transition, stale result, failure, cancellation, and compatibility path.
- [ ] 3.2 Move participant eligibility, archive-manager exclusion, occupancy claim/release, conflict handling, participant replacement, terminal cleanup, and restart rebuild into the lifecycle/repository boundary; add concurrent Meeting, stale-owner release, conflicting legacy occupancy, recovery repair, and unrelated-Meeting parallelism tests.

## 4. AI meeting request and project-linkage service

- [ ] 4.1 Extract request create/list/detail, required-field validation, urgency/auto-confirm policy, context selection, confirm/reject, duplicate unresolved request prevention, and atomic request-to-Meeting conversion into `meeting_requests.py`; migrate HTTP, Agent bridge, Feishu, and internal callers with idempotency and payload/status compatibility tests.
- [ ] 4.2 Integrate request/Meeting results with `ProjectRepository` using task/attempt/blocker compare tokens, stable reconciliation diagnostics, and idempotent forward recovery; verify stale linkage rejection, Project commit failure/retry, repeated decision, Meeting success/Project failure, resume/block/human-decision outcomes, and concurrent project updates.

## 5. Action-item projection and task conversion

- [ ] 5.1 Extract Meeting result normalization, stable action-item identity, project-task projection, completion state, explicit selection, and `(meetingId, actionItemId)` task conversion dedupe into `meeting_action_items.py`; migrate callers and test repeated conversion, concurrent project edits, stale Meeting linkage, partial failure/retry, bounded history, and old-record compatibility.

## 6. Notifications and trusted callbacks

- [ ] 6.1 Extract bounded redacted notification DTOs, stable intent keys, sent/failed markers, and best-effort delivery coordination into `meeting_notifications.py`; preserve business-state-first ordering and verify notification failure/crash/retry, credential/transcript/path/error canaries, payload compatibility, and no business rollback.
- [ ] 6.2 Keep Feishu authenticity/transport parsing in adapters and extract trusted callback commands into `meeting_callbacks.py`; persist callback dedupe/outcomes in the unified Store, migrate Meeting-request and Meeting actions, and verify forged actor/linkage, unsupported actions, cross-project/request access, replay, concurrent delivery, audit redaction, and stable card responses.

## 7. Boundary, performance, and complete regression

- [ ] 7.1 Remove migrated business orchestration from compatibility delegates; add static checks preventing Service imports of `server.py`/`OfficeHandler`/transport types and direct Meeting JSON writes, update fixed 1/20/100 Meeting performance results, and prove request conversion reduces two Meeting-domain writes to one without increasing Agent/notification calls or unbounded scans.
- [ ] 7.2 Run the complete Python, JavaScript, static, migration, persistence, Project Execution, Provider, Feishu, notification, SSE/WebSocket, workflow, security, concurrency, performance, and OpenSpec strict regression; document commands/results, scenario traceability, confirmed bug fixes, compatibility exceptions, and any manual-only coverage.

## 8. Documentation, migration rehearsal, and release readiness

- [ ] 8.1 Update service-boundary/operator documentation for the unified schema, authority gate, migration modes/report/conflict handling, backups/rollback, lock/token ordering, trusted callbacks, reconciliation, observability, and legacy-store non-authority; run the migration on copied small/medium/large fixtures and attach exact count/link/digest evidence.
- [ ] 8.2 Start the application only through `start.sh` and complete manual acceptance for migration-required/invalid states, migrated startup, Meeting lifecycle/intervention/recovery, occupancy conflicts, request decision/conversion, Project resume/block, action-item task conversion, callback replay, notification degradation, and management authorization.
- [ ] 8.3 Execute an isolated release rehearsal: stop mutations and server, back up legacy/unified/project state, run migration dry-run/apply/validation, start exactly one candidate process through `start.sh`, exercise active Meeting/request/project state, stop and restore backups/prior code, restart through `start.sh`, and verify counts, links, occupancy, idempotency, and non-reversible Agent/Feishu reconciliation before final confirmation.
