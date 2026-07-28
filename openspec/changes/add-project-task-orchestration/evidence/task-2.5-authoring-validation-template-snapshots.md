# Task 2.5 Evidence: Authoring validation and template snapshots

Date: 2026-07-27

## Scope

Updated the Agent project-authoring boundary and immutable template snapshots to use the stage-pipeline contract:

- Authoring validation accepts task `executionStage`.
- Authoring validation rejects missing, invalid, or non-contiguous stage assignments.
- Authoring validation rejects legacy draft inputs `projectExecutionStartMode`, `executionPolicy`, and task `executionOrder`.
- New template snapshots no longer synthesize `projectExecutionStartMode` or `executionPolicy.maxActiveTasks`.
- Legacy browser-template adapters synthesize task `executionStage: 1` while preserving historical disabled execution intent without old execution-policy fields.
- The VO project-authoring skill contract now tells agents to emit `executionStage` and not old progression fields.

## Verification

Focused authoring/template regression:

```text
.venv/bin/pytest -q tests/test_project_authoring_validation.py tests/test_project_templates.py
18 passed in 0.29s
```

Related authoring, direct-create, materialization, and template regression:

```text
.venv/bin/pytest -q tests/test_project_authoring_service.py tests/test_project_authoring_direct_create.py tests/test_project_materialization.py tests/test_project_materialization_characterization.py tests/test_project_templates.py tests/test_project_authoring_validation.py
87 passed in 2.18s
```

Agent authoring skill contract:

```text
node tests/check_vo_project_authoring_skill.mjs
VO project authoring skill contract passed
```

Static boundary check:

```text
rg -n "projectExecutionStartMode|executionPolicy|maxActiveTasks|executionOrder" app/services/project_authoring_validation.py app/services/project_templates.py skills/vo-project-authoring/SKILL.md tests/check_vo_project_authoring_skill.mjs tests/test_project_authoring_validation.py tests/test_project_templates.py
```

Remaining matches are intentional rejection inputs, negative assertions, guidance that explicitly forbids the legacy fields, or the template task-field exclusion list that prevents `executionOrder` from entering snapshots.

OpenSpec validation:

```text
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
Change 'add-project-task-orchestration' is valid
```

## Notes

- Authoring validation intentionally does not auto-normalize sparse stages such as `1, 3` into `1, 2`; the AI-facing boundary must reject incomplete/non-contiguous assignments so the user-visible plan remains explicit.
- Materialization still owns defaulting for non-AI creation sources covered in task 2.4.
