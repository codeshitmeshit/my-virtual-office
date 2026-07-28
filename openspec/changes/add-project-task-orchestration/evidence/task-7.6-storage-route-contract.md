# Task 7.6 Evidence: Storage and Route Contract

## Scope

- Marked `stage_pipeline_v1` projects persist only the new orchestration authority.
- Markdown reload ignores legacy project progression fields and task `executionOrder` pollution.
- GET project detail and list routes expose derived multi-task orchestration projection after reload.
- Project start route rejects deleted legacy marked-project start payload fields.

## Changed Coverage

- `tests/test_project_orchestration_store.py`
  - `test_marked_project_save_and_reload_strips_legacy_authorities_even_if_present`
  - `test_marked_project_reload_ignores_legacy_frontmatter_pollution`
- `tests/test_project_orchestration_http.py`
  - `test_marked_project_routes_survive_markdown_reload_without_legacy_authorities`
  - `test_marked_project_start_route_rejects_legacy_payload_contract`

## Implementation Notes

- `MarkdownProjectStore` now omits old marked-project authority fields during write and ignores them during read when `executionModel` is `stage_pipeline_v1`.
- Marked task persistence writes `executionStage`, `stageRunId`, and `orchestrationSkip`; it does not write or reload `executionOrder`.
- HTTP contract tests drive `OfficeHandler.do_GET()` and `OfficeHandler.do_POST()` against repository-backed project data, so coverage includes route dispatch, markdown reload, projection, and response serialization.

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_project_orchestration_store.py tests/test_project_orchestration_http.py tests/test_project_stage_start_server.py
```

Result: `29 passed in 2.02s`

```bash
.venv/bin/python -m py_compile app/project_store.py tests/test_project_orchestration_store.py tests/test_project_orchestration_http.py
```

Result: passed

```bash
npx --yes @fission-ai/openspec@latest validate add-project-task-orchestration --strict
```

Result: `Change 'add-project-task-orchestration' is valid`
