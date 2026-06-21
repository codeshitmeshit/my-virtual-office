# Checklist: Meeting Participant XP

确认状态：已确认

## Checklist Items

### CHK-001: Completed executable meeting grants participant XP

- Requirement: Completed executable meetings should award XP to participating AI agents.
- Verification method: Create or simulate an executable meeting with at least two participants, transition it to `completed`, then inspect `/api/projects/scores` or `project-scores.json`.
- Expected result: Each unique valid participant receives the configured meeting XP award.

### CHK-002: Award is idempotent

- Requirement: Repeated end/summarize/archive calls must not double count XP for the same meeting.
- Verification method: Invoke the same completion path twice or call the terminal handler after the meeting is already completed.
- Expected result: Participant scores increase only once for the meeting, and meeting state records that XP was already awarded.

### CHK-003: Non-completed meetings do not grant XP

- Requirement: Only completed executable meetings should grant meeting XP.
- Verification method: Cancel, pause, fail, or leave a meeting awaiting user decision, then inspect scores.
- Expected result: No meeting participation XP is added for non-completed states.

### CHK-004: Meeting XP does not increment task completed count

- Requirement: Meeting participation should affect XP without pretending a project task was completed.
- Verification method: Record an agent score entry before and after a completed meeting.
- Expected result: `score` increases, optional `meetings` count increases, but task-oriented `completed` does not increase.

### CHK-005: Score history is traceable

- Requirement: Users and developers should understand why XP changed.
- Verification method: Inspect the affected agent's history entry after a meeting award.
- Expected result: History includes a meeting-specific type or reason, meeting id or topic, award timestamp, and points.

### CHK-006: All completion paths are covered

- Requirement: Meeting XP should be awarded regardless of how a meeting completes.
- Verification method: Exercise moderator summary completion, arbitration completion, user moderator takeover completion, and fallback run completion.
- Expected result: Each path awards exactly once per completed meeting.

### CHK-007: Invalid or system-only participants are skipped defensively

- Requirement: Agents that should not participate in normal work should not receive leaderboard XP.
- Verification method: Simulate a meeting record containing empty, unassigned, or archive-manager participant ids.
- Expected result: Invalid/system ids are skipped and valid participants still receive XP.

### CHK-008: Leaderboard remains sorted by total XP

- Requirement: Existing leaderboard behavior should remain stable.
- Verification method: Award meeting XP to an agent and fetch `/api/projects/scores`.
- Expected result: Leaderboard ordering reflects updated total `score` descending, with no new ranking rule.

### CHK-009: Existing task scoring is unchanged

- Requirement: Task completion XP behavior should not regress.
- Verification method: Complete tasks with different priorities, due dates, and checklist states using existing paths.
- Expected result: Task XP values and task completion count behavior remain the same as before this change.

### CHK-010: Persistence survives restart/reload

- Requirement: Meeting XP and idempotency marker must persist with existing data files.
- Verification method: Complete a meeting, reload the score and meeting stores, then call completion handling again.
- Expected result: Previously awarded XP remains present and is not awarded again.

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-20T16:42:13+08:00
- 用户确认摘要：用户回复 `pass`，确认当前 checklist 可作为后续 todolist 和实现依据。

## 验证记录

- 验证时间：2026-06-20T16:52:48+08:00
- 验证命令：`.venv/bin/python tests/test_meeting_for_ai_phase1.py`
- 验证结果：通过。覆盖完成会议参会者 XP、幂等、非完成会议不加分、无效参与者过滤、leaderboard `meetings` 字段和任务 `completed` 不增加。
- 验证命令：`.venv/bin/python tests/test_project_execution.py`
- 验证结果：通过。命令输出包含预期的本地 gateway 连接失败日志，但测试最终 `ok`。
- 验证命令：`.venv/bin/python tests/test_meeting_for_ai_phase4.py`
- 验证结果：通过。命令输出包含 sandbox 下 gateway 连接受限日志，但测试最终通过。

## 测试与完成确认记录

- 确认项：tested
- 确认时间：2026-06-21T00:00:00+08:00
- 用户确认摘要：用户确认 `meeting-participant-xp` 可以归档。
- 确认项：done
- 确认时间：2026-06-21T00:00:00+08:00
- 用户确认摘要：用户确认 `meeting-participant-xp` 可以归档。
