# Task 1.4 Release Preflight Command

## Scope

Added a read-only release preflight command for the stage-pipeline Project Execution release.

Command:

- `scripts/project_orchestration_release_preflight.py`

Tests:

- `tests/test_project_orchestration_release_preflight.py`

## Behavior

The command scans only the canonical Markdown project store under `projects-md/*/project.md`, reads project frontmatter, and reports projects whose `executionModel` is not `stage_pipeline_v1`.

The command intentionally does not instantiate `MarkdownProjectStore` or call `load_all()` because those paths may perform legacy migration or metadata repair. It parses frontmatter directly and emits JSON containing:

- `backupCandidate.source`
- `backupCandidate.target`
- exact `legacyDeletionCandidates[].projectDir`
- exact `legacyDeletionCandidates[].projectFile`
- candidate project IDs, titles, task counts, and reasons
- `destructiveActionsPerformed: []`

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_release_preflight.py
.venv/bin/python -m pytest -q tests/test_project_orchestration_release_preflight.py tests/test_project_execution_legacy_characterization.py tests/test_execution_lifecycle.py tests/test_project_execution_ordering.py
.venv/bin/python scripts/project_orchestration_release_preflight.py --status-dir data --timestamp 20260725T000000Z
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Results:

```text
2 passed in 0.20s
19 passed in 46.79s
Change 'add-project-task-orchestration' is valid
```

Real local `data/` preflight summary:

```json
{
  "backupCandidate": {
    "source": "/home/cosh/my-virtual-office/data",
    "target": "/home/cosh/my-virtual-office/data.backup-before-stage-pipeline-20260725T000000Z",
    "actionRequired": "copy_status_dir_before_destructive_cleanup"
  },
  "summary": {
    "canonicalProjectCount": 3,
    "legacyDeletionCandidateCount": 3,
    "readErrorCount": 0
  },
  "destructiveActionsPerformed": []
}
```

Deletion candidates from the real local scan:

| Project ID | Title | Tasks | Reason |
|---|---|---:|---|
| `1900b60c-eea7-4e9b-a0d6-02cd34da9d12` | `日报专项` | 3 | `missing_required_execution_model` |
| `954c2f17-1b8a-450b-bc1a-3004c289e853` | `高优测试` | 2 | `missing_required_execution_model` |
| `project-afee7f27-6336-4c92-9082-067e690c71bf` | `可复用金融分析链路` | 10 | `missing_required_execution_model` |

## Read-Only Guard

The unit tests snapshot every file under the temporary status directory before and after both direct function execution and CLI execution. They assert the snapshots are identical and that the report contains no destructive actions.
