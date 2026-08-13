# Meeting-domain migration and operations

## Authority and files

`<status-dir>/meeting-domain.sqlite3` is the only runtime authority for executable Meetings, events, occupancy, AI Meeting requests, callback replay, action-item idempotency and notification intents. `meeting-domain.json`, `executable-meetings.json` and `meeting-requests.json` are offline migration/rollback inputs only. Runtime has no JSON fallback, dual read, full-store `snapshot/update`, or legacy load/save compatibility path.

Startup states:

- valid unified Store: normal reads and mutations;
- no unified Store and empty/absent legacy inputs: initialize an empty Store;
- no unified Store with legacy data: fail Meeting mutations with `meeting_store_migration_required`;
- invalid or unknown schema: fail closed with `meeting_store_invalid`.

The supported deployment has exactly one server writer. The active-process lock is `meeting-store-active.lock`.

## Offline migration

Stop the server and all Meeting mutations first. Always start with dry-run:

```bash
.venv/bin/python scripts/migrate_performance_stores.py --status-dir /absolute/status/dir
```

Review counts, `sourceDigest`, every `relationshipChecks.*.status`, destination and source byte counts. Apply only after dry-run passes:

```bash
.venv/bin/python scripts/migrate_performance_stores.py --status-dir /absolute/status/dir --apply
```

Apply creates byte-for-byte timestamped backups of every present legacy input, validates a candidate SQLite database, runs `integrity_check`, installs it atomically and writes `performance-store-migration-report.json`. Repeating the same apply must return `already_migrated` without new backups or replacement. A changed source digest, symlink, malformed input, dangling request link, conflicting occupancy, running server, replace/fsync failure or unknown schema fails closed.

Do not edit or delete the legacy inputs between dry-run and apply. Do not use a force/last-writer-wins merge.

## Rollback

Rollback is permitted only while the candidate server is stopped:

1. preserve the failed unified Store and report as evidence;
2. restore both byte backups to their original legacy names;
3. restore the prior code and Project state snapshot;
4. remove or relocate the candidate unified Store so prior code cannot treat it as authority;
5. restart only with `./start.sh`;
6. compare Meeting/request/event/occupancy counts, request links and idempotency keys.

Agent calls, Feishu delivery and other external effects are not reversible. Reconcile them from callback outcomes, notification intents and Meeting events after data rollback.

## Locks, compare tokens and recovery

- Repository mutation is short and atomic. Normal commands load only one Meeting/request and its owned rows; collection transactions are explicit for creation, occupancy reconciliation and timeout sweeping. Agent/notification/callback/Project work runs outside it.
- Agent completion commits only when Meeting ID, phase, version, event sequence, call ID and participant still match.
- Project results verify request, Meeting, task, attempt and blocker linkage before commit.
- Action-item Project projection dedupes by `(meetingId, actionItemId)` and Meeting commit compares the draft snapshot.
- Callback replay uses verified event/message identity. Card values cannot override actor identity or Store linkage.
- Restart rebuild reports ambiguous occupancy and never silently selects between two forced owners.

## Observability and sensitive data

Use migration status/schema, operation, ID digest, phase/status, stale commit, reconciliation, callback replay, notification failure, load/save bytes and duration as diagnostics. Never log credentials, raw callback bodies, unrestricted transcripts, raw Provider output or local absolute paths. Notification/callback DTOs are allowlisted, bounded and redacted.

## Evidence

- Fixed migration rehearsal: `openspec/changes/archive/2026-07-13-extract-meeting-and-collaboration-services/migration-rehearsal.json`.
- Performance: `performance-final.json` and `performance-result.md` in the same change.
- Automated regression: `regression-phase7.md`.
- Runtime/manual/release rehearsal: `acceptance-phase8.md` and `release-rehearsal.md`.
