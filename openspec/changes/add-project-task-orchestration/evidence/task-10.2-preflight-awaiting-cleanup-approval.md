# Task 10.2 Legacy Cleanup Preflight Evidence

## Status Directory Resolution

- `VO_STATUS_DIR` in the current shell was empty.
- Runtime `data/vo-config.json` still points `presence.statusDir` at `/data`.
- The release preflight script defaults to repository `data/` when
  `VO_STATUS_DIR` is unset.
- Repository `data/projects-md` contained 3 canonical project records.
- `/data/projects-md` contained 0 canonical project records.
- The cleanup preflight target for recoverable legacy records is therefore:
  `/home/cosh/my-virtual-office/data`.

## Backup

- Source: `/home/cosh/my-virtual-office/data`
- Backup: `/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z`
- Command: `cp -a /home/cosh/my-virtual-office/data /home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z`
- Backup size: `138M`
- Backup file count: `1232`
- `diff -qr` after copying reported only live status/log files that changed
  after the copy:
  - `feishu-chat-worker-status.json`
  - `logs/restart-20260724T213208Z.log`

## Recoverability Checks

The three legacy candidate `project.md` records have matching source and
backup checksums:

- `b6187c13f0153b856941680f168c17ecc4da36675418e46db83317b79d692701`
  - Source: `/home/cosh/my-virtual-office/data/projects-md/item--1900b60c-a548608581/project.md`
  - Backup: `/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z/projects-md/item--1900b60c-a548608581/project.md`
- `2e6509d2d8488e36dfc8fdaa402efe42b478e0e4e39af37925952340bfb85a89`
  - Source: `/home/cosh/my-virtual-office/data/projects-md/item--954c2f17-a64e73c0af/project.md`
  - Backup: `/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z/projects-md/item--954c2f17-a64e73c0af/project.md`
- `0a9469e7afff125e771fc30c824f15d1181d8f9552c610f1cab72162c26b3c91`
  - Source: `/home/cosh/my-virtual-office/data/projects-md/item--project--500e1c190f/project.md`
  - Backup: `/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z/projects-md/item--project--500e1c190f/project.md`

## Read-Only Preflight

Command:

```bash
.venv/bin/python scripts/project_orchestration_release_preflight.py --status-dir /home/cosh/my-virtual-office/data --timestamp 20260727T110200Z
```

Result:

- `readOnly`: `true`
- `destructiveActionsPerformed`: `[]`
- `canonicalProjectCount`: `3`
- `legacyDeletionCandidateCount`: `3`
- `readErrorCount`: `0`
- `requiredExecutionModel`: `stage_pipeline_v1`

Deletion candidates reported by the read-only preflight:

| Project ID | Title | Directory | Reason | Task Count |
| --- | --- | --- | --- | --- |
| `1900b60c-eea7-4e9b-a0d6-02cd34da9d12` | `日报专项` | `/home/cosh/my-virtual-office/data/projects-md/item--1900b60c-a548608581` | `missing_required_execution_model` | 3 |
| `954c2f17-1b8a-450b-bc1a-3004c289e853` | `高优测试` | `/home/cosh/my-virtual-office/data/projects-md/item--954c2f17-a64e73c0af` | `missing_required_execution_model` | 2 |
| `project-afee7f27-6336-4c92-9082-067e690c71bf` | `可复用金融分析链路` | `/home/cosh/my-virtual-office/data/projects-md/item--project--500e1c190f` | `missing_required_execution_model` | 10 |

Control preflight for `/data`:

```bash
.venv/bin/python scripts/project_orchestration_release_preflight.py --status-dir /data --timestamp 20260727T000000Z
```

Result:

- `canonicalProjectCount`: `0`
- `legacyDeletionCandidateCount`: `0`
- `readErrorCount`: `0`

## Automated Verification

Command:

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_release_preflight.py
```

Result:

- `2 passed in 0.44s`

## Approval Gate And Cleanup

Initial state:

- No destructive cleanup was performed before explicit approval.
- The read-only preflight found 3 deletion candidates and the task required
  separate explicit approval before removing confirmed legacy project records.

Approval received:

- User explicitly approved: `批准删除这 3 个 legacy 项目记录`.

Cleanup command:

```bash
rm -rf /home/cosh/my-virtual-office/data/projects-md/item--1900b60c-a548608581 /home/cosh/my-virtual-office/data/projects-md/item--954c2f17-a64e73c0af /home/cosh/my-virtual-office/data/projects-md/item--project--500e1c190f
```

The command used only the three exact directories reported by preflight and
approved by the user.

Post-cleanup directory check:

```bash
find /home/cosh/my-virtual-office/data/projects-md -maxdepth 1 -type d | sort
```

Result:

- Only `/home/cosh/my-virtual-office/data/projects-md` remained.

Post-cleanup read-only preflight:

```bash
.venv/bin/python scripts/project_orchestration_release_preflight.py --status-dir /home/cosh/my-virtual-office/data --timestamp 20260727T111000Z
```

Result:

- `canonicalProjectCount`: `0`
- `legacyDeletionCandidateCount`: `0`
- `readErrorCount`: `0`
- `readOnly`: `true`
- `destructiveActionsPerformed`: `[]`

Post-cleanup backup recoverability:

```bash
sha256sum /home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z/projects-md/item--1900b60c-a548608581/project.md /home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z/projects-md/item--954c2f17-a64e73c0af/project.md /home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260727T110200Z/projects-md/item--project--500e1c190f/project.md
```

Result:

- `b6187c13f0153b856941680f168c17ecc4da36675418e46db83317b79d692701`
  for `item--1900b60c-a548608581/project.md`
- `2e6509d2d8488e36dfc8fdaa402efe42b478e0e4e39af37925952340bfb85a89`
  for `item--954c2f17-a64e73c0af/project.md`
- `0a9469e7afff125e771fc30c824f15d1181d8f9552c610f1cab72162c26b3c91`
  for `item--project--500e1c190f/project.md`
