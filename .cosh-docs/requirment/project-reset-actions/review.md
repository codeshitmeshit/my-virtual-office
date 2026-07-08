# Project Reset Actions Review

## Product Review

No blocking product ambiguity remains.

The clarified behavior establishes two separate user intentions:

- A lighter recovery action: "重置任务状态".
- A broader project task-flow reset: "彻底重置项目".

The important product boundary is that neither action deletes user-created tasks or persistent history. The stronger option is therefore best described in UI copy as resetting the project task flow, not destroying data.

## Technical Review

### Architecture Touchpoints

- Frontend project board toolbar in `app/projects.js`.
- Project board styles in `app/projects.css`.
- Locale strings in `app/locales/zh.json` and `app/locales/en.json`.
- Project reset API in `app/server.py`.
- Markdown project persistence in `app/project_store.py` if additional persisted reset metadata is introduced.
- Project Execution helpers that already understand backlog/done columns, current execution state, meeting blockers, review results, and restart cleanup.

### Data and State Flow

The reset operation should be server-authoritative. The frontend should request reset and then replace or refresh the current project from the server response.

The server should:

- Validate the project exists.
- Detect whether high-risk confirmation is required.
- Refuse risky reset without confirmation.
- Locate the backlog column.
- Preserve task ordering before moving tasks.
- Clear current execution state and current execution context.
- Preserve audit/history data.
- Clear project-level active execution indicators.
- Save and return the updated project.

### Ordering Requirement

Ordering is a key risk. The reset must define a deterministic order source:

1. Existing user-visible order before reset should be preserved when tasks are retained.
2. Sort by current column order and task order when flattening tasks back to backlog.
3. If available, use an initial or stored order only when it does not conflict with the clarified requirement to preserve added tasks and visible sequence.

The implementation should avoid relying on dictionary iteration or file system order.

### Confirmation Requirement

Confirmation must be enforced in both frontend and backend:

- Frontend: show a high-risk confirmation for visible risky state before calling confirmed reset, or react to `confirmationRequired`.
- Backend: return `409` with `confirmationRequired` if risky state exists and request lacks confirmation.

This prevents accidental reset through API calls.

### Compatibility

- Existing projects without additional reset metadata must remain resettable.
- Existing scheduled cron state must remain untouched.
- Existing project artifacts and workspace files must remain untouched.
- Existing history fields must remain compatible with markdown persistence.

### Observability

The server should append a project activity entry for reset actions, including the reset mode and reset task count. This is enough for user-visible traceability without introducing a new logging surface.

### Risks

- Misinterpreting "彻底重置项目" as delete/recreate. Mitigation: UI copy should say it preserves tasks, history, configuration, and scheduled tasks.
- Loss of task order. Mitigation: explicit test cases for order preservation.
- Clearing too much history. Mitigation: checklist covers comments, attempts, meeting history, and artifacts preservation.
- Active execution continuing after reset. Mitigation: reset must clear project active fields and task active attempt; E2E should validate UI state no longer appears active/blocked.

## Review Conclusion

No blocking product or technical issue remains. Proceed to checklist confirmation before implementation planning.
