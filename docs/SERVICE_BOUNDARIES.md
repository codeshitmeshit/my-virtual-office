# Project service boundaries

Virtual Office routes project-domain work through thin transport adapters and independently testable application services. Public HTTP routes, JSON fields, status semantics, Markdown persistence, Provider protocols, SSE/WebSocket behavior, and frontend workflows remain compatible.

## Dependency direction

```text
OfficeHandler / Feishu / Meeting / Cron
                    |
                    v
             compatibility delegates
                    |
      +-------------+-------------+
      v             v             v
 project_commands  execution_lifecycle  review_acceptance
      |             ^             |
      |             |             |
      +------ project_schedule ----+
                    |
              ProjectRepository
                    |
          MarkdownProjectStore adapter

OfficeHandler -> artifacts -> validated filesystem handles
```

Code under `app/services/` must not import `server.py`, `OfficeHandler`, `http.server`, or HTTP request/response objects. The AST gate in `tests/test_project_service_static_boundaries.py` discovers every top-level Service module automatically.

## Module ownership

| Module | Owns | Does not own |
| --- | --- | --- |
| `project_execution.py` | Workspace-validation pilot and `ServiceResult` compatibility type | HTTP parsing or response writes |
| `project_repository.py` | Project-scoped atomic updates, coherent snapshot, legacy three-way commits, delete coordination, repair/history compatibility | Business state machines or slow external calls |
| `project_commands.py` | Project/task CRUD, Done/checklist/column policies, managed-workspace deletion decision | Filesystem deletion implementation or HTTP authorization |
| `execution_lifecycle.py` | Start/status/cancel, attempt transitions, persist-before-launch, Provider compare-and-commit | Provider implementation, HTTP, or Review decisions |
| `review_acceptance.py` | Review, rework, acceptance, trusted entry context, notification intents and sanitized DTOs | Transport identity discovery or exactly-once external delivery |
| `artifacts.py` | Workspace containment, association/extension policy, bounded scan/read, secure open/delete and descriptor lifetime | HTTP streaming headers or management-token checks |
| `project_schedule.py` | Gateway/binding orchestration, dispatch claims/leases, occurrence idempotency, reconciliation and history decisions | Gateway transport implementation or project execution internals |

Legacy `_wf_*` orchestration remains a deliberate non-goal. It may keep its business flow, but every project-store write still goes through the shared Repository coordinator.

## Trusted entries

- `OfficeHandler` validates the management token before parsing or invoking browser management mutations.
- Feishu adapters derive actor and project/task linkage from the verified card/action context; request-body actor fields are not trusted.
- Meeting commands validate project/task linkage through their dedicated command entry and remain available to the execution-agent bridge without a browser token.
- Cron validates project-bound agents and delivery policy, and uses persisted claims plus a per-Cron monotonic run-now occurrence sequence.
- Services accept explicit `actor`, `source`, `EntryContext`, repository, clock, Provider, notification, Gateway, and filesystem ports. They never infer trust from arbitrary payload text.

## Writer and lock rules

`PROJECT_STORE.save_all` and `PROJECT_STORE.delete_project` may appear only in the `ProjectRepository` wiring in `app/server.py`. `_save_projects` is a compatibility delegate to `ProjectRepository.commit_snapshot`, not a direct full-store replacement.

Lock order is:

1. lock-registry guard;
2. project lock;
3. short global store commit lock.

Cron binding file locks are never held while acquiring a project/store lock. Per-Cron operation locks serialize Gateway CRUD and dispatch state for one Cron. Slow Provider, notification, Gateway, Git, and filesystem work must not run while a project lock is held; dependent results re-enter an atomic compare-and-commit boundary.

## Sensitive data

Workspace paths, Provider reply/error, Review feedback, Artifact content, credentials, and Feishu targets are sensitive.

- Raw Provider results and unknown Provider/Gateway metadata are not persisted or returned.
- Logger/notifier DTOs use allowlisted fields, shared credential redaction, absolute-path removal, and length limits.
- Artifact content is available only through authorized bounded reads/streams and is never copied to logs, notifications, or project state.
- Authorized project/workspace responses retain their existing path fields for compatibility; notifications and generic diagnostics do not.

Regression canaries include Basic/Bearer authorization, cookies, JSON and key-value secrets, POSIX paths (including spaces and a single segment), Windows drive paths, UNC paths, oversized text, Artifact content, and unexpected Provider metadata.

## Confirmed migration fixes

- Project writers no longer lose unrelated concurrent project/task/history fields.
- Git workspace snapshot failure fails closed before Provider invocation with `workspace_git_snapshot_failed`.
- Review/acceptance ignores forged actors, validates linkage, and persists stable local notification intent before best-effort delivery.
- Native Codex/Claude reviewers receive the revalidated attempt-workspace snapshot only in their in-memory Provider call, preventing project-path races or verification of the provider's unrelated default repository. Codex is forced to `read-only`/`never`, Claude Code to `plan`; these provider-layer restrictions are independent of the prompt, and the path is not copied into review DTOs or logs.
- Management-token retries now use the stable `management_token_required` code, so unrelated domain/security 403 responses pass through without prompting again or clearing a valid token.
- Artifact reads/deletes reject traversal, symlink swaps, non-regular files, unassociated paths, and resource-limit abuse.
- Cron history appends are atomic; same-Cron CRUD converges Gateway/binding state; update persistence failure compensates Gateway, delete retries tolerate an already-removed Gateway job, dispatch exceptions release without completing the occurrence, leases renew, run-now callbacks use an O(1) monotonic completion high-water mark, and binding capacity uses persisted atomic reservations with compensation.
- Shared redaction now covers structured credentials and absolute paths before logger/notifier persistence.

Each intentional correction has a failing-before regression. Other public behavior remains compatible and requires no Markdown data migration.

## Performance method and result

The fixed harness uses small (`5×10`), medium (`50×50`), and large (`200×100`) project/task fixtures, 3 warmups, and 20 measured runs. Store/Provider/notification/Gateway/Git-scan counts are the primary gate; median and p95 are secondary evidence.

Final results are in `openspec/changes/extract-project-execution-services/performance-result.md`. No measured call count increased. Archived Cron dispatch strictly improves from `2 loads / 1 save` to `1 load / 1 save`; medium and large Cron p95 also improve. The medium fixture is the staging release/rollback fixture.

## Verification

- Full automated Python, script-style Python, JavaScript/static, syntax, and OpenSpec commands are recorded in `openspec/changes/extract-project-execution-services/full-regression.md`.
- Live-browser/CDP and end-to-end operator acceptance must start through `./start.sh`; do not invoke `python app/server.py` directly for acceptance.
- Release rehearsal must back up project Markdown and Cron bindings, record active attempts/reviews/claims, drain work, validate the new version, and prove rollback restores the snapshots.
