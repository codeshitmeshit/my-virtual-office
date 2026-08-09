# Personal Assets OSS Weak Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add best-effort cross-region Personal Assets snapshots through the existing VO OSS service without putting OSS on the local save path.

**Architecture:** A focused atomic sync-state store and sync coordinator sit beside the existing profile authority. Owner mutations notify the coordinator after local commit; a single background worker performs snapshot upload/restore and conflict detection. Thin management routes expose state and commands to a scoped Personal Assets UI strip.

**Tech Stack:** Python 3 dataclasses/threading/JSON/`io.BytesIO`, existing `PersonalAssetStore`, existing `OssStorageService`, vanilla JavaScript/CSS, pytest, Node static checks.

## Global Constraints

- `$STATUS_DIR/personal-assets.json` remains the only authoritative profile write path.
- OSS failure must never change the result of a successful local mutation.
- Do not expose or mutate OSS configuration from Personal Assets.
- New logic lives in focused modules; `app/server.py` receives dependency-wiring changes only.
- Sensitive Agent reads remain in HUMAN DECISIONS.
- Remote writes are best-effort snapshots, not strong consistency.

---

### Task 1: Atomic synchronization state

**Files:**
- Create: `app/services/personal_asset_sync_state.py`
- Test: `tests/test_personal_asset_sync_state.py`

**Interfaces:**
- Produces: `PersonalAssetSyncStateStore(path, now=None)`, `snapshot()`, `set_enabled(enabled)`, `mark_pending(revision)`, `mark_syncing(mode)`, `mark_synced(...)`, `mark_failed(...)`, `mark_conflict(...)`, and `set_resolution(resolution)`.

- [ ] **Step 1: Write failing state-store tests** for default enabled state, atomic `0600` persistence, pending/synced transitions, stable error-only failure persistence, and conflict resolution validation.
- [ ] **Step 2: Run `pytest -q tests/test_personal_asset_sync_state.py`** and verify import/behavior failures are caused by the missing module.
- [ ] **Step 3: Implement the minimal atomic store** with schema validation, per-path locking, UTC timestamps, and no secret-bearing fields.
- [ ] **Step 4: Re-run the focused test** and keep it green.

### Task 2: Snapshot synchronization coordinator

**Files:**
- Create: `app/services/personal_asset_sync_service.py`
- Create: `app/services/personal_asset_sync_worker.py`
- Modify: `app/services/personal_asset_store.py`
- Test: `tests/test_personal_asset_sync_service.py`
- Test: `tests/test_personal_asset_store.py`

**Interfaces:**
- Consumes: `PersonalAssetStore`, `PersonalAssetSyncStateStore`, and an injected `OssStorageService`-compatible object.
- Produces: `PersonalAssetSyncService.status()`, `on_profile_mutation(profile)`, `set_enabled(enabled)`, `request_sync()`, `resolve_conflict(resolution)`, and `run_once()`; `PersonalAssetSyncWorker.start()`, `wake()`, and `stop()`.

- [ ] **Step 1: Write a failing profile-restore test** showing that `restore_profile_snapshot(profile, expected_revision=...)` validates all entries/suggestions and atomically replaces only the public profile collections.
- [ ] **Step 2: Run the store test** and verify it fails because the restore API is absent.
- [ ] **Step 3: Implement minimal restore support** inside the existing store authority; replace only profile entries/suggestions, preserve the usage audit, clear stale access links and idempotency receipts, and increment the local revision.
- [ ] **Step 4: Write failing coordinator tests** for local-first success under OSS failure, correct object scope/content type, empty-region restore, safe remote update, divergent conflict, Keep local, Use cloud, checksum/size rejection, and sanitized errors.
- [ ] **Step 5: Run the coordinator tests** and verify expected missing-type failures.
- [ ] **Step 6: Implement canonical envelopes and the coordinator** using `integration_id="personal-assets"`, `object_id="profile-snapshot.json"`, semantic fingerprints excluding local revision, checksum validation, and ETag baseline comparison.
- [ ] **Step 7: Implement the daemon worker** as a single injected callback loop with `Event` wakeups and retry deadlines capped to 60-second waits.
- [ ] **Step 8: Run the focused tests** and refactor only after green.

### Task 3: Runtime and HTTP integration

**Files:**
- Create: `app/services/personal_asset_sync_http.py`
- Modify: `app/services/personal_asset_service.py`
- Modify: `app/services/personal_asset_http.py`
- Modify: `app/services/personal_asset_runtime.py`
- Modify: `app/server.py`
- Test: `tests/test_personal_asset_service.py`
- Test: `tests/test_personal_asset_http.py`
- Test: `tests/test_personal_asset_server_wiring.py`

**Interfaces:**
- Consumes: Task 2 coordinator and worker.
- Produces: management sync GET data and POST commands under `/api/personal-assets/sync/*`; mutation notifications that cannot throw through the owner command.

- [ ] **Step 1: Write failing service/route tests** proving local mutation remains successful when the observer throws, management GET includes `sync`, preference validation is strict, sync-now is queued with `202`, and conflict choices accept only `local|remote`.
- [ ] **Step 2: Run the focused tests** and verify failures reflect missing sync integration.
- [ ] **Step 3: Add an optional post-commit observer** to `PersonalAssetService`; catch/log observer failures after local commit and notify on CRUD, suggestion changes, and confirmed onboarding.
- [ ] **Step 4: Implement `PersonalAssetSyncHTTP`** as transport-free command parsing and inject it into `PersonalAssetHTTPRoutes`.
- [ ] **Step 5: Wire the runtime** with a new state store, coordinator, optional worker, and `OssStorageService(_oss_runtime().active_context)`; keep `app/server.py` to imports and dependency construction.
- [ ] **Step 6: Run focused route and wiring tests** until green.

### Task 4: Personal Assets panel controls

**Files:**
- Modify: `app/personal-assets.js`
- Modify: `app/personal-assets.css`
- Modify: `app/locales/en.json`
- Modify: `app/locales/zh.json`
- Modify: `tests/check_personal_assets_ui.mjs`

**Interfaces:**
- Consumes: `{ profile, sync }` and the three management commands from Task 3.
- Produces: scoped auto-sync toggle, state/last-success text, sync-now/retry, and confirmed conflict actions.

- [ ] **Step 1: Add failing DOM/static behavior checks** for the sync strip, no OSS credential fields, retry/polling behavior, and both confirmed conflict commands.
- [ ] **Step 2: Run `node tests/check_personal_assets_ui.mjs`** and verify it fails because the controls are absent.
- [ ] **Step 3: Implement minimal UI state and handlers** in `personal-assets.js`, polling only while the modal is open and synchronization is active.
- [ ] **Step 4: Add scoped styles and localized copy** matching the approved Personal Assets visual language.
- [ ] **Step 5: Re-run the UI check** and visually verify the local page.

### Task 5: Regression and self-review

**Files:**
- Modify only files required to fix verified defects.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified feature and evidence-backed handoff.

- [ ] **Step 1: Run focused Python tests:** `pytest -q tests/test_personal_asset_sync_state.py tests/test_personal_asset_sync_service.py tests/test_personal_asset_store.py tests/test_personal_asset_service.py tests/test_personal_asset_http.py tests/test_personal_asset_server_wiring.py tests/test_oss_storage.py tests/test_oss_runtime.py`.
- [ ] **Step 2: Run static UI checks:** `node tests/check_personal_assets_ui.mjs && node tests/check_agent_guide_static.mjs`.
- [ ] **Step 3: Run the repository's relevant full Python suite** and report unrelated pre-existing failures separately.
- [ ] **Step 4: Audit for secrets, blocking OSS calls on mutation paths, unsafe overwrite paths, orphan threads, clipped UI, and accidental changes to HUMAN DECISIONS.**
- [ ] **Step 5: Review the diff against the design spec** and correct any deviation before claiming completion.
