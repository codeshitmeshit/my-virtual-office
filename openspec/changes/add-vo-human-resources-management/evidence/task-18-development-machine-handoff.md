# Task 18 Development-Machine E2E Handoff

Date prepared: 2026-07-24

Status: **local implementation and regression complete; real-environment gate
not started**.

Reviewed runtime revision:
`66828bb10adba1c690a6cc89dcd36ce87704a85c`
(`codex/merged-agent-management`). The later handoff-only commit does not change
runtime behavior. Deploy this exact runtime revision, not the preparer's dirty
working tree.

Tasks 18.2–18.10 remain open. Local tests, the fake Provider, API tests and
screenshots are supporting evidence only and do not satisfy this gate.

## 18.1 Required target record

Before the first mutation, copy this table into the result package and replace
every `REQUIRED` value. Do not record secrets.

| Item | Value |
|---|---|
| Approved development-machine identifier | `REQUIRED` |
| Access path/operator | `REQUIRED` |
| Repository checkout path | `REQUIRED` |
| Service supervisor and stop/start/restart commands | `REQUIRED` |
| Browser base URL and entry method | `REQUIRED` |
| VO revision before deployment | `REQUIRED` |
| VO reviewed revision | `66828bb10adba1c690a6cc89dcd36ce87704a85c` |
| OpenClaw executable and version | `REQUIRED` |
| `VO_PORT` | `REQUIRED` |
| Resolved absolute `VO_STATUS_DIR` | `REQUIRED` |
| Timezone/daily time/submission window/workers/timeout/retry | `REQUIRED` |
| Test human identity | `REQUIRED` |
| Test ordinary Agent self AI ID | `REQUIRED` |
| Test colleague AI ID | `REQUIRED` |
| Test disposable Agent AI ID for create/delete | `REQUIRED` |
| Timestamped backup path | `REQUIRED` |
| Evidence package path | `REQUIRED` |
| Previous-revision rollback command | `REQUIRED` |

Task 18.1 must remain unchecked until this record is complete and the target is
confirmed to run real OpenClaw. The local `127.0.0.1:8090` instance previously
inspected is not eligible.

## Read-only preflight

Run from the development-machine checkout and save the output before changing
code, configuration or data:

```bash
pwd
git status --short
git rev-parse HEAD
git log -1 --format='%H %cI %s'
command -v openclaw
openclaw --version
curl -fsS http://127.0.0.1:${VO_PORT:-8090}/health
curl -fsS http://127.0.0.1:${VO_PORT:-8090}/api/agents
```

Stop if the checkout is dirty, the target/restart command is ambiguous, the
status directory is unresolved, the backup cannot be verified, OpenClaw is not
real and reachable, or the intended Agent identities are not registered.

## Backup and rollback prerequisites

Resolve `VO_STATUS_DIR` to a non-empty absolute directory dedicated to this VO
instance. Reject `/`, a home directory, or a repository root. Back up that
directory with the target's approved backup tool and record:

- source path and destination path;
- start/end timestamps and command exit status;
- file count/size and a backup checksum or manifest;
- pre-deployment revision and a copy of the non-secret effective configuration.

Do not delete or overwrite the source directory to test the backup. A feature
rollback retains the HR database and HR Agent identity.

The approved feature rollback order is:

1. Set `VO_HR_SCHEDULER_ENABLED=false`.
2. Wait for active HR claims to reach a terminal state or expire.
3. Set `VO_HR_ENABLED=false`.
4. Restart VO with the recorded supervisor command.
5. Verify Agent Management, Archive Room, meetings, projects and existing Agent
   operations remain available.
6. Roll code back to the recorded previous revision only if required. Restore
   data from backup only for proven corruption.

## Deployment and switch sequence

1. Deploy exactly
   `66828bb10adba1c690a6cc89dcd36ce87704a85c` into a clean checkout.
2. Start with `VO_HR_ENABLED=false` and
   `VO_HR_SCHEDULER_ENABLED=false`; restart and capture the Task 18.2 baseline.
3. Set only `VO_HR_ENABLED=true`; restart and complete lifecycle/directory/UI
   checks while the automatic schedule remains disabled.
4. Complete the real human and Agent audience tests and all representative
   high-risk operations.
5. Configure a controlled short cycle; only then set
   `VO_HR_SCHEDULER_ENABLED=true`.
6. Complete persistence/restart checks.
7. Rehearse the rollback order above. Do not automatically delete HR or its
   database.

Configuration values must be applied through the target's existing environment
or supervisor mechanism. Do not paste management, gateway or Provider tokens
into evidence.

## Browser entry

Human:

1. Open the recorded VO base URL.
2. authenticate through the target's normal management flow;
3. open **Agent Management** and verify the two tabs share roster/selection;
4. keep the browser Network panel and VO/OpenClaw logs available for correlation.

Agent:

1. From the registered Agent's loopback execution context, mint a launch:

   ```bash
   curl -fsS -X POST \
     -H 'X-VO-Agent-Action: agent-management' \
     -H 'X-VO-Agent-Id: <SELF_AI_ID>' \
     http://127.0.0.1:${VO_PORT:-8090}/api/agent-management/sessions
   ```

2. Open the returned relative `launchUrl` against the recorded browser base URL.
3. Do not paste the one-use launch code into logs or evidence.
4. Verify exchange removes the code from the URL and the Agent UI defaults to
   self. Repeat mint/exchange after VO restart; the old session must fail.

## E2E execution checklist

### 18.2 Disabled baseline

- Agent Management/configuration, workspace, Archive Room, projects, meetings,
  Providers and existing create/delete work with both HR switches disabled.
- Record clean browser screenshots, HTTP status, revision and OpenClaw version.

### 18.3 HR lifecycle and directory

- Real OpenClaw HR is auto-created once, rediscovered after restart and repaired
  without duplicates.
- HR appears in office/directory, pause/resume works, team sync and missing-info
  completion persist, `vo-agent-hr` is exposed, HR is meeting-eligible, and
  archive-manager remains isolated.

### 18.4 Governed Agent audience

- Self is the default and can auto-save/undo low-risk profile fields.
- A colleague returns public data only and creates access-audit evidence.
- Identity switching, restricted fields/actions, human assessments/evidence and
  HR commands are denied and absent from response plus DOM.
- Expiry/restart invalidates the session and a new launch re-enters cleanly.

### 18.5 Human high-risk flows

- Exercise Provider, branch, workspace, assignment, binding, create and delete.
- For every action record impact text, challenge/command correlation without
  secrets, direct legacy-route denial, downstream persistence and refreshed UI.

### 18.6 Controlled daily cycle

- Follow one stable command ID through accepted, processing and terminal state.
- Record real HR-to-Agent communication, raw/normalized report, late or missing
  response, evidence, assessment/insufficient-information, partial failure
  isolation, persistence and refreshed UI.

### 18.7 Restart and recovery

- Restart VO and OpenClaw during or after controlled work.
- Verify profiles/reports/assessments, claim recovery, duplicate prevention,
  session invalidation/re-entry and existing VO domain regressions.

### 18.8 Rollback rehearsal

- Execute the approved scheduler-then-HR disable sequence.
- Preserve HR data and identity; prove existing VO and Archive Room remain
  operational; record restoration steps.

## Evidence package

Use a target-local directory such as:

```text
<approved-evidence-root>/agent-management-hr-e2e/<UTC timestamp>/
  00-target-and-versions.md
  01-config-redacted.md
  02-disabled-baseline/
  03-human-hr/
  04-agent-audience/
  05-high-risk/
  06-daily-cycle/
  07-restart/
  08-rollback/
  09-failures-retries-uncovered.md
  logs/
  screenshots/
```

Each scenario must include browser action, timestamp, HTTP/command/log
correlation, persisted outcome and final refreshed UI. Record failures and
retries; do not replace missing evidence with lower-level test results.

After Tasks 18.2–18.9 are complete, run strict OpenSpec validation and
specification-to-test traceability for 18.10. Do not archive this change during
the gate.
