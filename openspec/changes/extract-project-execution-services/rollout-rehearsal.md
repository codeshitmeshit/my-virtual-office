# Local isolated pre-staging rollout and rollback rehearsal

Date: 2026-07-12 (Asia/Shanghai)

## Versions and isolation

- Candidate base commit: `13a8219afdc410a65cdf8b34d6d695fc22335c2b`
- Candidate runtime patch: `rollout-runtime.patch`
- Candidate runtime patch SHA-256: `e7eeb70ffbbf2f792c8e893d1dd0a26f3c81ded67fdf682267b29626dd4daee9`
- Rollback commit: `13a8219afdc410a65cdf8b34d6d695fc22335c2b`
- Candidate ports: HTTP 18090 / WebSocket 18091
- Rollback ports: HTTP 18092 / WebSocket 18093
- Reproducible runner: `rollout-rehearsal.sh`
- Persisted result: `rollout-rehearsal-result.json`
- Runtime state/backup directories: created below a fresh `/tmp/vo-rollout-rehearsal.*` root and removed after success unless `VO_ROLLOUT_KEEP=1`

The candidate identifier is the base commit plus the tracked runtime patch captured from the exact isolated candidate copy. Applying `rollout-runtime.patch` to the base commit reconstructs the rehearsed runtime changes; later documentation/test-evidence edits do not alter that artifact.

## Fixture, thresholds, and commands

The fixed medium fixture contains 50 projects and 2,500 tasks. Its path-independent pre-release state digest was `d1a1ebfca52a2d6bdee4ce42f42eac828920a078a5e6f3ea0d1ee83eebd19c59`.

Release gates:

- HTTP and WebSocket ready within the startup script's built-in 30-second HTTP deadline.
- All 50 projects load after release and rollback.
- Active write completes within 30 seconds.
- Drain snapshot contains zero tasks in `executing`, `reviewing`, or `reworking`.
- Rollback loads the post-release state without schema repair failure or lost acknowledged writes.
- Backup restore reproduces the pre-release digest and the original 50/2,500 counts.

Reproduction command from the repository root:

```bash
VO_ROLLOUT_KEEP=1 \
  VO_ROLLOUT_RESULT_OUTPUT=openspec/changes/extract-project-execution-services/rollout-rehearsal-result.json \
  openspec/changes/extract-project-execution-services/rollout-rehearsal.sh
```

The script contains the exact environment setup, medium-fixture generation, backup/digest commands, API payloads, active-attempt assertions, cancellation drain, rollback startup, compatibility reads, and backup-restore digest comparison. `VO_ROLLOUT_RESULT_OUTPUT` copies the runner's raw result JSON without hand normalization. Both application versions are started only through their copied repository `start.sh`; the management token is stored in a mode-0600 file and is never printed. Without `VO_ROLLOUT_KEEP=1`, disposable `/tmp` data is intentionally cleaned because the durable evidence is the tracked script, runtime patch, and result JSON.

## Before, active-work, drain, and rollback snapshots

| Stage | Projects | Tasks | Active execution tasks | Evidence |
|---|---:|---:|---:|---|
| Before release | 50 | 2,500 | 0 | Backup digest above |
| Candidate acknowledged write | 50 | 2,501 | 0 | `project-0.description=rollout-active-write`; task `rollout live task` persisted |
| Candidate active execution | 51 | 2,502 | 1 | Dedicated task reported `phase=executing`, `active=true`, and a non-empty active attempt ID |
| Candidate after drain | 51 | 2,502 | 0 | Cancellation returned the same attempt ID; task became `blocked`, attempt `cancelled`, and `activeAttemptId=null` |
| Rollback boot | 51 | 2,502 | 0 | Rollback version preserved the cancelled attempt, blocked task, and both earlier acknowledged writes |
| Backup restore verification | 50 | 2,500 | 0 | Restored digest exactly matched `d1a1eb…19c59` |

## Reconciliation and result

- Candidate startup: HTTP and WebSocket ready; medium fixture loaded.
- Active-work drain: a real execution attempt was first observed active, then explicitly cancelled; no task remained active before shutdown.
- Rollback startup: HTTP and WebSocket ready on the rollback ports; all acknowledged candidate writes and the drained `cancelled` attempt remained readable.
- Data backup: the pre-release archive restored to the exact original digest and entity counts.
- Expected diagnostic only: Gateway and browser viewer were unavailable in the isolated rehearsal; neither is required for project-store release/rollback integrity.
- After final CR fixes, the tracked runtime patch was regenerated from the exact candidate files (including the management-403 client correction); that final candidate was restarted via `start.sh` and re-read the drained `cancelled` attempt with `active=false`.

Result: **LOCAL PASS**. Candidate startup, active write, drain, rollback, and backup restoration met every declared local threshold with no project/task loss. This does **not** complete the real staging gate: staging configuration, Gateway, browser viewer, and environment-specific integrations must still be exercised before release approval.
