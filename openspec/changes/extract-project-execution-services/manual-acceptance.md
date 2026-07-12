# Manual acceptance result

Date: 2026-07-12 (Asia/Shanghai)

The application was started exclusively with the repository `./start.sh`. No direct Python server command was used for acceptance. The acceptance instance used HTTP 8090, WebSocket 8091, a temporary configured management token supplied from a mode-0700 temporary file, and an isolated Git workspace under `/private/tmp`.

## Results

| Scenario | Result | Evidence |
|---|---|---|
| Startup and UI | Pass | `start.sh` reported HTTP and WebSocket ready; `/health` returned 200; the in-app browser rendered the Virtual Office shell and project navigation. Gateway/CDP diagnostics were unavailable and reported as degraded optional integrations. |
| Management token | Pass | An unauthenticated project mutation returned 403; the same request with the temporary configured token succeeded. Because `VO_MANAGEMENT_TOKEN` was configured before `start.sh`, the server log exposed only its hash prefix and never the token value. |
| Project/task CRUD | Pass | Created an isolated project and tasks, read them back, updated project/task fields, and preserved both updates. |
| Execution and dirty-worktree gate | Pass | The first start on a dirty Git workspace returned 409 `dirty_worktree_confirmation_required`; the confirmed retry ran the native executor and produced `acceptance.txt` containing exactly `section8-pass`. |
| Review/rework/acceptance | Pass | The first native Claude review returned `needs_more_work`; the task moved `reviewing → reworking → execution_complete`, retained linked feedback, and launched the next attempt. This exposed the wrong-provider-workspace bug described below. After the fix, a fresh task's native review was bound to its validated attempt workspace and returned `pass`; the task moved to `awaiting_user_acceptance`, then HTTP acceptance moved it to `done`. Repeated acceptance returned the stable documented 409 and did not duplicate acceptance history. |
| Artifact access | Pass | Associated `acceptance.txt` was listed, read as 13 bytes (`section8-pass`), and streamed with HTTP 200, `text/plain`, and `Content-Length: 13`. Unassociated inline reads remained forbidden. |
| Scheduling | Pass with expected degraded dependency | With Gateway intentionally unavailable, create returned HTTP 502 `Failed to create cron job`; reconciliation confirmed no partial Virtual Office binding was persisted. Automated phase 1–5 tests cover the successful Gateway path. |
| Git snapshot failure | Pass | After validation as a Git workspace, an invalid Git configuration caused start to fail closed with HTTP 409 and code `workspace_git_snapshot_failed`; Provider launch did not begin. |
| Concurrent operations | Pass after migration bug fix | Concurrent project and task updates both returned HTTP 200 and preserved the project marker, task priority, and compatibility work-log comment. |

## Bug fixes discovered during acceptance

1. Native Codex/Claude reviewers previously inherited their provider default working directory. Review execution now passes the already validated project workspace privately to native providers; the path is not added to the prompt, review DTO, notification, or log payload.
2. The task compatibility work-log path previously used a stale legacy load/merge/save after the command Service had committed. Under a concurrent project update this could persist both business changes but raise `ProjectConflictError`, producing an empty HTTP response. `_wf_write_task_file` now uses the shared repository's per-project atomic update. A threaded regression test covers the combined project/task write.
3. Final pre-submit review found that the management client treated every HTTP 403 as an invalid token. Authentication rejection now carries `management_token_required`; domain/security 403 responses pass through unchanged, preserving the valid token and the real error. The frontend behavior test covers the no-prompt, no-retry, no-token-clear path.
4. Overall CR found that native reviewer prompts requested read-only behavior without enforcing it at the Provider boundary. Native Codex reviews now force `read-only` sandbox with no approvals, while Claude Code reviews force plan mode; ordinary executor/chat calls keep their existing permissions.
5. Overall CR found two Cron recovery gaps. Unexpected dispatch exceptions no longer complete the occurrence, and Gateway-success/local-binding failures now compensate or remain retryable instead of silently splitting state.

Temporary acceptance projects and workspaces are disposable and are removed after the final regression evidence is captured.
