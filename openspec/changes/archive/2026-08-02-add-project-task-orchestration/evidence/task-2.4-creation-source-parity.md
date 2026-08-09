# Task 2.4 Creation Source Parity

## Scope

Updated project creation sources so their new Project/Task outputs share the marked stage-pipeline orchestration contract.

Code:

- `app/services/browser_project_creation.py`
- `app/services/project_commands.py`
- `app/services/project_direct_materialization.py`
- `app/services/project_materialization.py`
- `app/services/project_template_materialization.py`

Tests:

- `tests/test_project_materialization.py`
- `tests/test_project_materialization_characterization.py`
- Related CLI, command, authoring, template, store, and orchestration tests

## Implemented Source Alignment

- Manual project creation no longer passes legacy `executionPolicy.maxActiveTasks` into canonical materialization.
- Browser template creation maps explicit blueprint `executionStage` and otherwise defaults template tasks to stage 1.
- Agent direct-create no longer seeds task `executionOrder`.
- Versioned-template and recurrence materialization no longer seed task `executionOrder`.
- Canonical task materialization no longer infers initial `executionStage` from board-card `order`; initial tasks default to stage 1 unless an explicit valid `executionStage` is provided.
- Existing-project task creation still uses `max(existing executionStage) + 1`, preserving the later modal/add-task default expected by the orchestration plan.

## Parity Coverage

`tests/test_project_materialization_characterization.py` now asserts that manual browser, Agent direct-create, versioned-template, and recurrence outputs all:

- persist `executionModel: stage_pipeline_v1`;
- persist draft orchestration state;
- assign every task a positive `executionStage`;
- assign default `stageRunId` and `orchestrationSkip`;
- omit legacy project progression authorities and task `executionOrder`.

Multi-task browser/direct/template/recurrence sources additionally assert their initial tasks begin as one parallel stage (`[1, 1]`) rather than silently recreating old list-order serial execution.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_materialization.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_commands.py tests/test_project_authoring_service.py tests/test_project_authoring_direct_create.py tests/test_project_templates.py tests/test_project_template_compatibility.py tests/test_project_orchestration_store.py
```

Result:

```text
99 passed in 3.18s
```

```bash
.venv/bin/python -m pytest -q tests/test_project_materialization.py tests/test_project_materialization_boundaries.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_orchestration_store.py tests/test_project_store_authoring_metadata.py tests/test_project_repository.py tests/test_project_commands.py tests/test_project_authoring_service.py tests/test_project_authoring_direct_create.py tests/test_project_templates.py tests/test_project_template_compatibility.py tests/test_project_orchestration.py tests/test_project_orchestration_release_preflight.py tests/test_project_execution_legacy_characterization.py tests/test_execution_lifecycle.py tests/test_project_execution_ordering.py
```

Result:

```text
169 passed in 59.75s
```

```bash
rg -n "executionOrder|executionPolicy|maxActiveTasks|projectExecutionStartMode" app/services/project_direct_materialization.py app/services/project_template_materialization.py app/services/browser_project_creation.py app/services/project_recurrence_materialization.py app/services/project_materialization.py app/office.py tests/test_project_materialization.py tests/test_project_materialization_characterization.py tests/test_project_cli_materialization_characterization.py tests/test_project_orchestration_store.py
```

Result:

```text
Only negative assertions remained in tests; creation-source materializers no longer seed the old authorities.
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
8 / 52 tasks complete
```
