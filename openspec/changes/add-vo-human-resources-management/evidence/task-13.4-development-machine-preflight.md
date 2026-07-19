# Task 13.4 Development-Machine Preflight

Date: 2026-07-20

Status: **blocked pending an approved real-OpenClaw development-machine target**. No development-machine mutation or deployment was performed.

## Startup configuration readiness

The repository startup path is ready for controlled deployment:

- `.env.example` declares every supported non-secret HR setting.
- `start.sh` repairs missing HR settings in an existing `.env` without replacing operator-supplied values.
- Repeated repair is idempotent. `VO_HR_ENABLED` defaults to `true`, while `VO_HR_SCHEDULER_ENABLED` remains `false`; an explicit `VO_HR_ENABLED=false` is preserved as the rollback/opt-out control.
- A blank `VO_HR_TIMEZONE` inherits `VO_TIMEZONE`, then `TZ`, then `UTC`; the remaining bounded values match `HRConfig` defaults.
- Focused startup/configuration and HR regression tests cover this behavior.

## Candidate inspected

The only target discoverable from the current repository and runtime configuration was the local VO instance on `http://127.0.0.1:8090`:

- It serves the current instance `/skills/index.md` and is started from this repository by `start.sh`.
- The checked-out implementation revision at inspection time was `7b2d76838f1e5f96d9c97fdd2476a27de70e75b1`.
- `/api/agents` returned only Codex and Claude Code providers; no `providerKind=openclaw` Agent was present.
- The configured OpenClaw path was not an available executable/runtime.

This candidate is therefore not eligible for tasks 13.5-13.9, whose acceptance criteria explicitly require a real OpenClaw environment. Treating demo/provider-fake behavior as real acceptance would invalidate the gate.

## Information required before mutation

The approved target must be supplied through an already configured access path; credentials or secrets must not be pasted into this document. Before deployment, record:

1. Development-machine identifier and access method.
2. Repository checkout path, deployment/update command, service supervisor, start/stop/restart commands, and health endpoint.
3. VO revision/version and real OpenClaw version, plus evidence that `/api/agents` exposes the intended OpenClaw provider.
4. Effective non-secret configuration: `VO_PORT`, `VO_STATUS_DIR`, `VO_HR_ENABLED`, `VO_HR_SCHEDULER_ENABLED`, timezone, daily time, submission window, worker count, timeout, and retry limit.
5. Timestamped backup location for the complete `VO_STATUS_DIR`, including existing archive, meeting, project, workspace, lifecycle, and communication authorities. The HR database will reside under `<VO_STATUS_DIR>/human-resources/hr.sqlite3` after initialization.
6. Exact code and data rollback commands, including the prior revision and service restart procedure.

## Approved feature-switch sequence

Once a valid target is explicitly approved, use this order:

1. Back up the status directory and record checksums/previous revision.
2. Deploy with `VO_HR_ENABLED=0` and `VO_HR_SCHEDULER_ENABLED=0`; restart and complete the task 13.5 baseline.
3. Set only `VO_HR_ENABLED=1`; restart and complete task 13.6 lifecycle verification.
4. Keep the scheduler disabled while completing task 13.7 directory, introduction, managed-skill, grant, permission, and audit verification.
5. Configure a controlled short cycle, then set `VO_HR_SCHEDULER_ENABLED=1` for task 13.8.
6. For rollback, first set `VO_HR_SCHEDULER_ENABLED=0`, allow active claims to settle or expire, then set `VO_HR_ENABLED=0` and restart. Preserve the HR database and HR Agent identity; do not delete either automatically.
7. If code rollback is required, restore the recorded prior revision and configuration only after both HR switches are disabled. Restore data from backup only for proven corruption, not as a routine feature rollback.

## Stop conditions

Stop and report without advancing the gate if the target lacks real OpenClaw, the status directory or backup cannot be resolved, the pre-enable baseline is not clean, provider identity is ambiguous, an in-flight claim cannot settle, or rollback commands have not been proven safe for the target supervisor.
