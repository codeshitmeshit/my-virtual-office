# Task 2.2 Markdown Store Round Trip

## Scope

Extended `MarkdownProjectStore` persistence support for the stage-pipeline orchestration fields.

Code:

- `app/project_store.py`

Tests:

- `tests/test_project_orchestration_store.py`

## Implemented Storage Fields

Project frontmatter:

- `executionModel`
- `orchestration_json`

Task frontmatter:

- `executionStage`
- `stageRunId`
- `orchestrationSkip_json`

## Malformed Frontmatter Handling

- Malformed or non-object `orchestration_json` loads as `{}`.
- Malformed or non-object `orchestrationSkip_json` loads as `{}`.
- Invalid, missing, zero, or negative `executionStage` loads as `None` so orchestration validation can reject it as an invalid stage assignment.

## Boundary

`MarkdownProjectStore` only persists and repairs storage-shaped values. It does not own stage validation, orchestration state transitions, dispatch, authorization, or projection logic.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py
```

Result:

```text
2 passed in 0.16s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py tests/test_project_store_authoring_metadata.py tests/test_project_repository.py tests/test_project_orchestration.py
```

Result:

```text
51 passed in 2.40s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py tests/test_project_store_authoring_metadata.py tests/test_project_repository.py tests/test_project_orchestration.py tests/test_project_orchestration_release_preflight.py tests/test_project_execution_legacy_characterization.py tests/test_execution_lifecycle.py tests/test_project_execution_ordering.py
```

Result:

```text
70 passed in 47.82s
```

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result:

```text
Change 'add-project-task-orchestration' is valid
```

```bash
npx --yes @fission-ai/openspec@latest instructions apply --change add-project-task-orchestration --json
```

Result:

```text
6 / 52 tasks complete
```
