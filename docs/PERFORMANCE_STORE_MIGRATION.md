# Performance store migration

The Agent event stream and Meeting domain are SQLite authorities:

- `agent-events.sqlite3` replaces `codex-activity.json`.
- `meeting-domain.sqlite3` replaces `meeting-domain.json` (and the older split Meeting files).

Measured latency, storage footprint, methodology, and known Meeting-path regressions are documented in [the backend performance optimization report](PERFORMANCE_OPTIMIZATION_REPORT_2026-08-13.md).

Stop the Virtual Office server first. The server holds `meeting-store-active.lock`, so the migration fails closed if a process is still serving the status directory.

## Development machine procedure

1. Locate the development status directory. It is the directory containing one or more of `codex-activity.json`, `meeting-domain.json`, `executable-meetings.json`, or `meeting-requests.json`; do not point the command at the repository root.
2. Stop `./start.sh` and confirm no Virtual Office server process is using that status directory.
3. Copy the status directory or take a filesystem snapshot.
4. Run the dry-run below. Require `ok: true` and inspect each store's record count and `sourceDigest`.
5. Run `--apply`. Require each source-backed store to report `migrated` (`already_migrated` is expected on a repeat).
6. Confirm the two `.sqlite3` files, timestamped `.backup-*` files, and the migration report exist with mode `0600`.
7. Validate both databases, restart, and check `/api/meetings/store-status` returns `ok: true` and `state: unified`.

Validate without changing authority:

```bash
python3 scripts/migrate_performance_stores.py --status-dir /path/to/status
```

Apply the migration:

```bash
python3 scripts/migrate_performance_stores.py --status-dir /path/to/status --apply
```

The apply operation validates both sources, writes timestamped mode-`0600` JSON backups, builds candidate databases, runs SQLite `integrity_check`, writes a prepared report, verifies that source bytes have not changed, and then installs the databases. Re-running the same command is idempotent and reports `already_migrated`.

Validate the resulting files before restart:

```bash
sqlite3 /path/to/status/agent-events.sqlite3 'PRAGMA integrity_check;'
sqlite3 /path/to/status/meeting-domain.sqlite3 'PRAGMA integrity_check;'
```

Both commands must print exactly `ok`. The repository migration regression can also be run with:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  tests/test_performance_store_migration.py \
  tests/test_meeting_store_migration.py
```

The runtime deliberately does not read legacy JSON. If a database is absent while legacy data is present, Meeting endpoints fail with `meeting_store_migration_required`; this is a deployment error, not a signal to restore fallback reads.

After migration, restart the server so the process creates its bounded SQLite connection pools. No runtime compatibility interface, dual read, or per-Meeting event polling endpoint remains; clients receive Meeting changes through the shared dashboard SSE stream.

Keep the source JSON and `.backup-*` files through the observation period. Rollback requires the previous application version as well as its JSON inputs: the current application cannot run from legacy JSON. While stopped, preserve the failed databases and their `-wal`/`-shm` sidecars for diagnosis, restore the backup filenames, deploy the previous version, and only then restart.
