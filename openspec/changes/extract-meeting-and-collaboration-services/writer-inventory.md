# Meeting-domain writer inventory

## Authorities before consolidation

| Authority | Data | Lock | Writers |
| --- | --- | --- | --- |
| `executable-meetings.json` | meetings, events, occupancy, executable idempotency | `_EXEC_MEETING_LOCK` | lifecycle create/transition/run/intervention/agenda/arbitration/moderator/targeted-question/end/reconcile, action-item state, projections/advisories that repair data |
| `meeting-requests.json` | requests, request idempotency, conversion metadata | `_MEETING_REQUEST_LOCK` | create, confirm, reject, blocker resolution |
| Project Markdown | meeting blocker/history/action items/decisions and created tasks | `ProjectRepository` | request block/update/result application, action-item projection/conversion, user blocker actions |
| Feishu callback log/config | callback audit and delivery configuration | existing adapter locks | authenticated card receiver and notification adapters |

`tests/test_meeting_store_characterization.py` uses the Python AST to lock the exact direct reader and writer function sets, cross-domain Project/callback/notification/recovery boundaries, and the only two legacy filename literals.

`tests/generate_meeting_inventory.py` deterministically inventories every `server.py` function whose name contains `meeting` and every direct call edge into or out of those functions. The generated `meeting-call-inventory.json` is compared byte-semantically in tests, so any new, removed, or rerouted Meeting boundary requires an explicit inventory update.

### Executable-store readers

`_meeting_complete_live_advisories`, `_meeting_active_projection`, `_meeting_history_projection`, every `_handle_executable_meeting_*` command/detail/events path, and reconcile. The executable writer set is the same command family plus projection/advisory repair writers; its exact membership is executable in `EXPECTED_READERS`/`EXPECTED_WRITERS`.

### Request-store readers and writers

Readers: create, list, detail, confirm, reject, and blocker resolution. Writers: create, confirm, reject, and blocker resolution. Exact sets are guarded by AST tests.

### Cross-domain boundaries

- Project: block/update Meeting blocker, resolve blocker, apply Meeting result, sync action items, and user blocker action.
- Callback: authenticated card handler, Meeting-request dispatcher, and callback audit record.
- Notification: Meeting request/failure senders and persistent delivery marker.
- Recovery: Meeting reconcile and occupancy rebuild.

## Planned ownership

| Current concern | Target owner | Commit rule |
| --- | --- | --- |
| Meeting/request/event/occupancy/idempotency | `MeetingDomainRepository` | one unified atomic mutation |
| Lifecycle and Agent turns | `MeetingLifecycleService` | prepare token, slow work outside lock, compare-and-commit |
| Request decision/conversion | `MeetingRequestService` | request + Meeting atomic in unified Store; Project compare token separately |
| Action-item projection/task conversion | `MeetingActionItemService` | stable `(meetingId, actionItemId)` dedupe through ProjectRepository |
| Notification intent/delivery result | `MeetingNotificationService` | business commit first; best-effort external delivery |
| Feishu action dispatch | verified adapter + `MeetingCallbackService` | trusted context + persistent callback dedupe |

## Characterization coverage

- Lifecycle: all legal/illegal transitions, expected version, run/continue/timeout, cancellation, stale Agent work, intervention, agenda, arbitration, moderator takeover, targeted questions, completion, and restart reconcile.
- Requests: required fields, one unresolved blocker, list/detail ordering, auto/human confirmation, rejection, repeated decision, conversion, and Project blocker state.
- Occupancy: participant conflicts, archive-manager exclusion, replacement, terminal release, active projection, and recovery rebuild.
- Action items: Meeting result projection, accept/reject/keep, source project/task linkage, duplicate conversion, and project resume/block outcomes.
- Collaboration: Feishu card confirm/reject, callback replay/audit, notification markers/failure, and sensitive-data redaction.
- Compatibility: old optional fields, API status/payloads, project records, Meeting projections, SSE/WebSocket/static frontend contracts.

## Baseline method

`tests/meeting_baseline_harness.py` runs three warmups and twenty measured iterations for legacy executable/request load and atomic save using 1/20/100 Meeting fixtures, 20 events per Meeting, one request per Meeting, and two occupied Agents per Meeting. It also executes a real pending-request confirmation with instrumented save helpers; the observed baseline is one executable write plus three request writes (four Meeting-domain durable writes, zero Provider calls). `performance-baseline.json` records these counts, bytes, median, and p95. `characterization-manifest.json` maps lifecycle, Agent call, stale/concurrent result, reentrant call, legacy record, request decision/dedupe, Meeting callback action/replay, and action-item dedupe to ten pytest node IDs. `tests/run_meeting_characterization_manifest.py` executes those exact nodes and emits a machine-readable result.
