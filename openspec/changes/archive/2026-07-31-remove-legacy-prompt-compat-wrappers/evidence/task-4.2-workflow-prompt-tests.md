## Task 4.2 Workflow Prompt Test Migration

Date: 2026-07-31

### Change summary

No workflow prompt-only tests needed migration in this task. Current workflow prompt tests already target the owning service module:

- `tests/test_workflow_prompt_formatting.py`
  - `services.workflow_prompt_formatting.render_workflow_task_prompt(...)`
  - `services.workflow_prompt_formatting.render_workflow_review_prompt(...)`
  - `services.workflow_prompt_formatting.render_workflow_rework_prompt(...)`

### Verification commands

- `rg "server\\._wf_build_(project_context|task_prompt|review_prompt|rework_prompt)" tests -g '*.py' -n`
  - Result: no matches.
- `PYTHONPATH=app .venv/bin/python -m pytest tests/test_workflow_prompt_formatting.py tests/test_prompt_formatter_static.py -q`
  - Result: `8 passed`.

### Risk / follow-up

`app/server.py` still contains workflow runtime prompt wrapper functions. Runtime ownership and wrapper removal are handled by Tasks 4.3 and 4.4.
