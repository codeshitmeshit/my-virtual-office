# Section 8 start-script acceptance and rollback rehearsal

## Candidate start

- Candidate was started and restarted only with `./start.sh`; HTTP `8090` and WebSocket `8091` passed the script's built-in health checks.
- The configured management token was the startup-script default `4285`. An unauthenticated destructive Project request returned `403 management_token_required`; authenticated lifecycle requests succeeded.
- `./start.sh --browser` was attempted and stopped at its prerequisite check because Docker is not installed on this machine. No direct Python server or alternative browser launcher was used. CDP/UI/performance checks therefore remain explicit manual-only coverage.
- Browser viewer, OpenClaw Gateway, Hermes, and Feishu reported unavailable because the local machine lacks Docker, a Gateway token/config, Hermes configuration, and Feishu application credentials respectively. Their unavailable/degradation paths passed without affecting healthy Providers.

## Live acceptance

- Health and WebSocket startup checks passed. Provider availability returned Codex `200`, Claude Code `200`, Hermes `503` disabled/unavailable, and Hermes Gateway Platform `200` disabled/unconfigured.
- Codex live run `codex-1783935599453-1b013426` completed through `codex-app-server` with reply `OK`, no modified files, one terminal event, and persisted request/reply history. Repeating the same idempotency scope returned `duplicate_completed` with the same run ID and no second launch.
- Codex terminal replay with `Last-Event-ID=2` returned only event `3 run.completed` and closed immediately. Conversation reset removed the native thread mapping while leaving office-visible request/reply history readable.
- Claude Code live run `claude-code-1783935621128-83e51357` completed through `claude-code-cli` with reply `VO_PROVIDER_ACCEPTANCE_OK`, session metrics/message/terminal frames, no file operation, and persisted session `61d0c1e1-16f4-4f3b-8955-337831cb9377`.
- An idle Provider conversation emitted an initial snapshot and a heartbeat after approximately ten seconds. A deliberately disconnected conversation stream closed server-side without a follow-up request-loop traceback.
- Missing run SSE returned the existing `404 run.failed` frame. Missing Hermes/OpenClaw/Feishu dependencies degraded only their own path; Codex, Claude, Project, Meeting, health, and WebSocket remained healthy.
- Workflow E2E passed **20/20** including dispatch-to-human-intervention, stop, auto mode, review persistence, Done transition, and portability checks. Project CRUD passed **5/5**.
- Meeting runtime acceptance passed management auth, lifecycle/versioning, intervention, recovery, occupancy cleanup, request confirmation, Project resume, action-item conversion, and missing-webhook notification degradation.
- Approval ordering/tokens/replay, cancellation races, timeout/failure isolation, attachment validation, conversation concurrency, OpenClaw queued delivery, and Project/Meeting Provider integration use the checked-in fake/local adapter suites when a real external path is unavailable.

## Defects found and corrected during acceptance

1. The offline Meeting migration required both legacy JSON files even when only the executable Store existed. It now treats either legacy source as optional, fingerprints absence as part of the source state, backs up only files that exist, and fails if existence/content changes before cutover. A regression test covers the single-source migration.
2. The real status directory was migrated offline from one populated legacy Store to `meeting-domain.json`: 14 Meetings, 14 event owners, zero requests/occupancy, source digest `12efb6ac2ce38609a289e8d5a75e67f1081dce80051ad754a57ce0b9655d9a9e`. Backup `executable-meetings.json.backup-20260713T093505Z` and the migration report were written before cutover.
3. Replayed terminal SSE frames left the HTTP/1.1 connection open. Run transport now marks the connection closed after journal or snapshot terminal output; live replay returned in zero seconds.
4. A client-disconnected conversation SSE could return to the HTTP request loop and log `ConnectionResetError`. Both run and conversation transports now close the connection when catching disconnect errors; focused regression and live disconnect passed.

## Isolated rollback rehearsal

1. New runs were stopped/drained; pending Codex and Hermes approval counts were both zero. Current histories/native mappings, Meeting counts/digest, and content hashes were recorded.
2. Candidate was stopped with its `start.sh` process trap. A temporary detached worktree restored prior commit `4b205d1902641cea8734accfbf7fa91a6fc25786` and a private copy of the current state. No live user state was edited by the rollback candidate.
3. The prior candidate was started only with its own `./start.sh` on isolated ports `18090/18091`. Health, Codex availability, Claude availability, Meeting API, Codex history, Claude history/native session, and unified Meeting Store all remained readable.
4. Critical content hashes were unchanged in the rollback copy: Meeting Store `3200693d…120f6`, Codex activity `313aeec0…e390`, Codex thread mapping `4659bf26…007a`, and Claude acceptance history `4d86769b…0911`. Meeting counts remained 16 Meetings, 16 event owners, one request, and zero occupancy.
5. The prior process was stopped, the temporary worktree/state were removed, and the current candidate was restarted through `./start.sh`. The same critical hashes, history counts, Claude native session, Meeting counts, and migration digest remained unchanged.
6. Active run/event state was intentionally absent after restart because it is documented non-durable memory state. Persisted histories/native mappings are the rollback compatibility contract. No external Provider side effect other than the two explicit read-only acceptance replies occurred; Feishu sent nothing because credentials were absent.

## Final regression

- All **77** isolated Python test/script files passed after the acceptance fixes; the two live-only files were covered by `start.sh` workflow/runtime acceptance rather than launching an in-process Python server.
- JavaScript/static: **23/23** static checks and **12/12** pure JavaScript/DOM tests passed.
- Provider characterization manifest: **21/21** passed.
- Fixed run/event, coordinator, approval, and conversation performance gates passed without call-count or retention regression.
- Generated Provider inventory reproduced exactly; Python compilation, `git diff --check`, and strict OpenSpec validation passed.

## Manual-only gaps

- CDP visual interaction and browser performance: Docker/CDP unavailable.
- Hermes API/Desktop/Gateway happy path and native approval continuation: no local Hermes/Gateway configuration.
- OpenClaw live queued delivery: no readable Gateway config/token.
- Feishu card delivery/callback: no application credentials/webhook.

These paths retain full fake/local contract, concurrency, security, failure-isolation, and static coverage. They are not reported as live passes.
