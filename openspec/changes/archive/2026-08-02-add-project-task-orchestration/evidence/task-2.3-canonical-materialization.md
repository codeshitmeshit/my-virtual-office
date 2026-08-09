# Task 2.3 Canonical Materialization

## Scope

Updated canonical Project/Task materialization so newly materialized projects use the stage-pipeline contract by default.

Code:

- `app/services/project_materialization.py`
- `app/project_store.py`

Tests:

- `tests/test_project_materialization.py`
- `tests/test_project_materialization_characterization.py`
- `tests/test_project_cli_materialization_characterization.py`
- `tests/test_project_materialization_boundaries.py`
- `tests/test_project_orchestration_store.py`
- Related command and authoring creation tests

## Implemented Defaults

Every canonical new project now receives:

- `executionModel: stage_pipeline_v1`
- Draft `orchestration` state from `default_orchestration_state()`
- No canonical `projectExecutionStartMode`, `projectExecutionFlowActive`, `projectExecutionFlowStopReason`, `executionPolicy`, `workflowActive`, `workflowPhase`, `activeTaskId`, `activeAgent`, or `autoMode`

Every canonical new task now receives:

- Positive `executionStage`
- `stageRunId: None`
- Default `orchestrationSkip` from `default_skip_state()`
- No canonical `executionOrder`

## Store Guard

`MarkdownProjectStore` now preserves old progression fields only when they are already present on the loaded/input object. Canonically materialized projects that omit old authorities are not serialized with default legacy frontmatter fields.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_materialization.py
```

Result:

```text
17 passed in 0.32s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_materialization.py tests/test_project_materialization_boundaries.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py
```

Result:

```text
30 passed in 11.48s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py tests/test_project_materialization.py tests/test_project_materialization_boundaries.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_store_authoring_metadata.py tests/test_project_repository.py tests/test_project_commands.py tests/test_project_authoring_service.py tests/test_project_authoring_direct_create.py tests/test_project_templates.py tests/test_project_template_compatibility.py
```

Result:

```text
126 passed in 11.35s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py tests/test_project_materialization.py tests/test_project_materialization_boundaries.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_store_authoring_metadata.py tests/test_project_repository.py tests/test_project_commands.py tests/test_project_authoring_service.py tests/test_project_authoring_direct_create.py tests/test_project_orchestration.py tests/test_project_orchestration_release_preflight.py tests/test_project_execution_legacy_characterization.py tests/test_execution_lifecycle.py tests/test_project_execution_ordering.py
```

Result:

```text
158 passed in 54.57s
```

```bash
rg -n "projectExecutionStartMode|projectExecutionFlowActive|projectExecutionFlowStopReason|workflowActive|workflowPhase|activeTaskId|activeAgent|autoMode|executionPolicy|executionOrder" app/services/project_materialization.py tests/test_project_materialization.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_orchestration_store.py
```

Result:

```text
Only negative assertions remained in tests; no old progression authority remained in canonical materialization implementation.
```
