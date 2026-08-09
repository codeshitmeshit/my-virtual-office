# Task 1.1 Archive Manager Pre-Extraction Baseline

## Environment

- Date: 2026-07-19 (Asia/Shanghai)
- Repository revision: `463b2af`
- Platform: `Darwin 25.5.0 arm64`
- Python: `3.12.13` from `.venv/bin/python`
- Node.js: `v20.20.2`
- Real OpenClaw: not required for this baseline; existing tests use isolated temporary OpenClaw homes and deterministic gateway fakes.

## Command

```bash
.venv/bin/python -m pytest -q \
  tests/test_archive_room_phase_1_3.py \
  tests/test_archive_room_phase_4.py \
  tests/test_archive_room_phase_5.py \
  tests/test_archive_room_phase_6.py \
  tests/test_archive_room_phase_7.py \
  tests/test_archive_room_phase_8.py \
  tests/test_agent_communication_skill.py
```

## Result

```text
.........................................                                [100%]
41 passed in 1.51s
```

Result: **PASS**. This is the required green reference before extracting the archive manager's system-Agent lifecycle.

## Locked Behavior Covered By Existing Tests

| Behavior | Existing evidence |
|---|---|
| Missing archive manager is created once and repeated overview calls are idempotent | `test_archive_manager_auto_create_idempotent_and_profile_files` |
| Required Profile files load from the repository template | `test_archive_manager_profile_files_load_from_template` |
| Existing stale Profile versions are upgraded | `test_archive_manager_existing_agent_updates_stale_profile_version` |
| Existing Agents with missing Profile files are repaired instead of recreated | `test_archive_manager_existing_agent_repairs_profile_files` |
| Provider creation failure preserves Archive Room read access | `test_archive_manager_creation_failure_degrades_readonly` |
| Pause/resume state and manual maintenance remain usable | `test_archive_manager_pause_resume_and_manual_maintain_current_project` |
| Archive manager cannot be deleted or assigned to ordinary project work | `test_archive_manager_cannot_be_deleted_or_assigned_to_project_tasks` |
| Archive manager chat scope remains constrained | `test_archive_manager_chat_boundary` |
| Canonical communication Skill install, no-op, upgrade, conflict, legacy, and symlink behavior | `tests/test_agent_communication_skill.py` |
| Existing archive manager repairs its communication Skill | `test_existing_archive_manager_repairs_communication_skill` |
| Archive data, artifact safety, event maintenance, context, governance, scheduling, and paused automatic work | Archive Room Phase 1–3 and Phase 5–8 suites |

## Current Persistence And Startup Anchors

The pre-extraction implementation persists lifecycle state through `_archive_manager_load_state` and `_archive_manager_save_state`, reconciles the provider through `_archive_manager_create_if_missing`, projects state through `_archive_manager_public_state`, and runs startup reconciliation through `_archive_manager_profile_check_on_startup`.

This baseline confirms persisted-state code paths are exercised indirectly, but the existing suite does not isolate a process-restart simulation as a named test. Task 1.2 must add an explicit deterministic restart-visible-state characterization before lifecycle production code changes.

## Known Characterization Gaps Reserved For Task 1.2

- Concurrent lifecycle reconciliation is not directly covered.
- Provider timeout/exception classification is not directly covered.
- Provider creation success followed by Profile failure and later repair is only partially covered.
- Explicit simulated process restart with persisted lifecycle state is not a named scenario.
- Repeated startup-profile checks are not directly asserted for one effective Agent.

No production code or existing test assertion was modified by task 1.1.
