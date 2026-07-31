## Task 3.4 Archive Regressions

Date: 2026-07-31

### Covered behavior

Focused archive regression coverage after archive wrapper migration/removal:

- Archive prompt document rendering:
  - refine prompt
  - context prompt
  - unavailable context prompt
- Archive Room phase 6 context behavior:
  - project-specific context differs by project
  - supplemental context boundary remains present
  - derived context includes project-specific material
- Project execution prompt construction still includes archive context through the service owner.

### Verification commands

- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_prompt_formatter_static.py tests/test_archive_prompt_documents.py tests/test_archive_room_phase_6.py tests/test_project_execution.py::test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context tests/test_project_execution.py::test_project_execution_rework_prompt_highlights_unfinished_checklist_focus -q`
  - Result: `14 passed`.
- `git diff --check -- app/server.py app/server_services/projects.py tests/test_prompt_formatter_static.py openspec/changes/remove-legacy-prompt-compat-wrappers/evidence/task-3.2-archive-runtime-entrypoints.md`
  - Result: passed.
- `openspec validate remove-legacy-prompt-compat-wrappers --strict`
  - Result: `Change 'remove-legacy-prompt-compat-wrappers' is valid`.

### Residual risk

A broad `tests/test_project_execution.py` run currently reports failures unrelated to archive context prompt ownership. The project/workflow task group should use focused project tests and address prompt-specific failures that fall within its scope.
