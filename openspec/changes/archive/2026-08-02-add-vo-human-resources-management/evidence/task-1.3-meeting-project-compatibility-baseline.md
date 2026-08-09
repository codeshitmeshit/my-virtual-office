# Task 1.3 Meeting And Project Compatibility Baseline

## Command

```bash
.venv/bin/python -m pytest -q -rxX \
  tests/test_archive_room_phase_4.py \
  tests/test_meeting_for_ai_phase1.py \
  tests/test_meeting_for_ai_phase4.py \
  tests/test_meeting_lifecycle_service.py \
  tests/test_project_actors.py \
  tests/test_project_commands.py
```

## Result

```text
93 passed, 3 xfailed in 2.88s
```

The three strict expected failures are named compatibility defects, not ignored flaky tests:

1. Concurrent archive-manager reconciliation may create more than one provider Agent; task 2.4 owns the fix.
2. A fresh negative roster cache may miss an externally created archive manager; task 2.4 owns the fix.
3. The legacy `/api/meetings/create` domain path does not apply archive-manager exclusion even though executable meetings do; task 4.5 owns the policy unification.

Each assertion describes the required post-change behavior and uses `strict=True`, so an early fix becomes an XPASS failure until the marker is deliberately removed.

## Compatibility Contract Locked By Passing Tests

- Archive-manager deletion rejects with `archive_manager_cannot_delete`.
- Archive-manager project defaults and task assignment reject with `archive_manager_not_assignable`.
- Executable meeting participant and moderator validation reject archive manager with `archive_manager_not_meeting_participant`.
- Meeting confirmation preserves the same archive-manager exclusion.
- Executable meeting creation claims occupancy only for valid participants.
- Completion, cancellation, timeout, arbitration, and recovery release only occupancy owned by that meeting.
- A stale terminal release does not overwrite a newer meeting owner.
- Project actor validation keeps one responsible actor, one executor, optional reviewer, and system-Agent exclusion semantics.
- Legacy project commands retain their stable archive-manager error semantics.

No production logic changed in this task.
