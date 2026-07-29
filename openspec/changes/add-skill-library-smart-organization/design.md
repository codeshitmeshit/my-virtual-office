## Context

The Skills Library currently stores each skill as `<openclaw-home>/skills-library/<slug>/SKILL.md`. `app/server_services/skills.py` scans those directories and exposes CRUD/apply handlers through `app/server_routes/skills.py`; `app/skills-library-ui.js` renders a small flat list. There is no persisted category catalog.

The archive manager already has a stable `archive-manager` identity, lifecycle state in `archive-room/manager.json`, an activity log, and an established `_wf_call_agent` invocation path. Manual archive maintenance, AI refinement, and archive-count audit independently set the manager to `working`, but those transitions are not protected by one atomic mutual-exclusion boundary.

Owner-authorized legacy mutations already use `X-VO-Management-Token` through `window.i18n.managementFetch`. Skill organization and manual classification can reuse this contract rather than creating another identity system.

Constraints:

- `SKILL.md` and skill folders remain the source of truth for skill content.
- Classification must not add lifecycle fields to individual skills.
- Existing files added directly outside the UI must remain discoverable.
- There is one local Virtual Office; no team-space scope is introduced.
- No new external database, queue, or model dependency is added.

## Goals / Non-Goals

**Goals:**

- Persist one primary category and optional tags without modifying `SKILL.md`.
- Reuse the existing archive manager for bounded, validated classification.
- Enforce owner authorization and archive-manager-wide mutual exclusion.
- Apply successful assignments independently while retaining failed skills in `默认标签`.
- Persist only the latest run summary needed by the top marker and failure correction flow.
- Keep implementation responsibilities in new focused modules with thin changes to existing routes, UI bootstrap, and archive entry points.
- Provide deterministic recovery, validation, observability, and rollback behavior.

**Non-Goals:**

- Creating a second organizer agent, independent job queue, or independent activity log.
- Adding per-skill intake or organization lifecycle status.
- Rewriting skill content, synchronizing agent copies, or changing MCP Registry behavior.
- Supporting batch manual moves, drag-and-drop classification, or organization undo.
- Building a general multi-user or team-space authorization model.

## Decisions

### 1. Store classification in one atomic sidecar catalog

Add `app/services/skill_library_catalog.py` as the sole classification repository. It stores `<skills-library>/.vo-library-catalog.json` with this logical shape:

```json
{
  "schemaVersion": 1,
  "revision": 7,
  "categories": [
    {"id": "default", "name": "默认标签", "kind": "system"},
    {"id": "development-testing", "name": "开发与测试", "kind": "system"}
  ],
  "skills": {
    "dev-debug": {
      "primaryCategoryId": "development-testing",
      "tags": ["diagnostics"]
    }
  },
  "lastOrganization": {
    "runId": "run-id",
    "outcome": "completed",
    "startedAt": "timestamp",
    "completedAt": "timestamp",
    "processedCount": 4,
    "movedCount": 4,
    "failures": [],
    "dismissedAt": null
  }
}
```

`lastOrganization` is run-level presentation state, not a field on a skill. Failed skill names and disclosure-safe reasons live only in that latest run summary.

The repository will:

- seed the immutable default and five general categories;
- reject rename/merge/delete attempts against `default`;
- normalize category IDs, tag values, lengths, and duplicates;
- default any on-disk skill missing from the catalog to `default` in the read projection;
- ignore stale catalog entries for folders that no longer exist and compact them on the next authorized write;
- reject symlink targets and write through a same-directory temporary file, `fsync`, and `os.replace`;
- serialize writes with a repository lock and increment `revision`.

Alternative considered: add category fields to `SKILL.md` frontmatter. Rejected because classification would mutate portable skill instructions, create merge noise, and couple archive governance to content ownership.

Alternative considered: one metadata file per skill. Rejected because category creation, partial-run application, failure-count correction, and revision checks need atomic cross-skill updates.

### 2. Add focused domain and transport modules

Add:

- `app/services/skill_library_catalog.py` for catalog persistence and invariants;
- `app/services/archive_manager_work_coordinator.py` for non-queued mutual exclusion;
- `app/services/skill_library_organization.py` for prompt construction, result validation, partial application, correction, dismissal, and recovery;
- `app/server_routes/skill_library_organization.py` for the new HTTP route group;
- `app/skills-library-organization-ui.js` and `app/skills-library-organization.css` for category navigation, status markers, failure filtering, and manual moves.

Existing files receive only wiring or delegation:

- `app/server.py` constructs collaborators, authorizes mutation routes, and registers thin adapters;
- `app/server_routes/__init__.py` registers the focused route group;
- `app/server_services/skills.py` enriches the existing list projection and assigns new/imported skills to default through the repository;
- `app/server_services/archive_room.py` wraps its three user-visible `working` operations with the shared coordinator;
- `app/skills-library-ui.js` keeps CRUD/apply operations and delegates organization rendering;
- `app/index.html`, locale JSON, and stylesheet/script includes receive minimal structural changes.

New service modules receive filesystem, clock, ID, archive-state, and agent-call collaborators explicitly and do not import `server.py`.

Alternative considered: append all orchestration to `server_services/skills.py`. Rejected because that module is already a compatibility-heavy service split and would become the authority for persistence, AI orchestration, concurrency, and presentation state.

### 3. Use the existing management-token boundary for owner actions

The following mutations require `X-VO-Management-Token` and are called through `window.i18n.managementFetch`:

- `POST /api/skills-library/organization/runs`
- `POST /api/skills-library/organization/dismiss`
- `POST /api/skills-library/<skill>/category`

The existing legacy mutation policy is extended so authorization runs before JSON body parsing. Reads remain available through the existing Skills Library GET surface.

Alternative considered: trust the browser UI alone. Rejected because agents or other local callers can invoke HTTP routes directly.

### 4. Run organization asynchronously without a queue

The start endpoint performs authorization and precondition checks, atomically acquires the archive-manager coordinator, records a run-level `running` summary, starts one bounded background worker, and returns `202` with `runId`.

The UI renders the optimistic running marker immediately and polls the enriched Skills Library projection every two seconds while a run is active. No websocket or durable job queue is introduced.

The coordinator is a process-wide, non-blocking lock shared by:

- manual archive maintenance;
- archive-manager AI refinement;
- archive-count audit;
- skill organization.

If another listed operation holds the lock, skill organization returns `409 archive_manager_busy`; it is neither queued nor started. The current manager state mirrors the holder kind so both Archive Room and Skills Library disable their relevant controls.

On process startup, a run persisted as `running` with no live coordinator owner is finalized as interrupted/failed, its default-category skills remain unchanged, and the manager state is reconciled out of the stale working presentation.

Alternative considered: rely only on `manager.json.status == "working"`. Rejected because concurrent requests can both observe idle before either writes working.

Alternative considered: queue the second operation. Rejected by the product decision to use disabled controls and explicit retry instead of a queue.

### 5. Send bounded, untrusted skill summaries to the archive manager

The worker snapshots the slugs currently projected into `default`, then creates deterministic batches of at most 20 skills. Each item contains the slug, parsed name, description, and bounded structural summary (frontmatter and headings, at most 2 KiB); full instruction bodies are not sent.

The prompt:

- identifies the existing archive manager role;
- treats all skill text as untrusted classification data and forbids following embedded instructions;
- supplies existing category IDs/names;
- requires JSON only;
- permits either an existing category ID, a proposed ordinary category name, or a disclosure-safe failure reason;
- explicitly requires `newCategoryName` when a clear purpose is not represented by the existing categories, so category absence alone is never a valid failure reason;
- permits `failureReason` only when the purpose cannot be determined reliably from the bounded skill summary;
- requires exactly one result for every input slug.

Only one batch is in flight at a time. This bounds prompt size and model concurrency while still processing every skill in the default snapshot.

Alternative considered: send complete `SKILL.md` files. Rejected because it increases latency, data exposure, and prompt-injection surface without materially improving purpose classification.

### 6. Validate AI output before applying independent assignments

`skill_library_organization.py` parses the reply as a strict JSON object and rejects unknown skill names, duplicate assignments, missing batch members, invalid category identifiers, unsafe category names, oversized tags, and path-like values.

For each valid result:

1. Re-read the catalog under the repository lock.
2. Confirm the skill directory still exists and its primary category is still `default`.
3. Resolve an existing category or create one normalized ordinary category.
4. Write the new primary category and sanitized tags.

Invalid, ambiguous, stale, missing, or failed results remain in `default` and are added to the run-level failures. Valid assignments from other items are retained. One atomic catalog write commits the terminal run summary and all accepted assignments.

Manual correction also requires an expected catalog `revision`. A stale request returns `409 catalog_revision_conflict` so it cannot overwrite a concurrent organizer result.

Alternative considered: apply the archive manager reply wholesale. Rejected because skill text is untrusted, model output can be malformed, and partial success must not corrupt category metadata.

### 7. Derive failure presentation from the latest run, not skill state

The enriched list response includes categories, catalog revision, archive-manager public state, and a disclosure-safe `organization` projection.

- Successful skills render in their destination category.
- Failed skill slugs remain under `default`; the UI derives the `归类失败` badge from `lastOrganization.failures`.
- The public projection retains each bounded failure `code` and disclosure-safe `reason`; failed cards and the selected-skill panel display the reason without exposing raw model output.
- Activating the partial-failure marker selects `default` and filters to those slugs.
- A successful manual move removes that slug from `failures` in the same catalog write.
- When the final failure is removed, the run-level outcome becomes `resolved`.
- Dismissal only sets `dismissedAt`; the next run replaces the entire summary.

This satisfies persistent UI feedback without introducing an organization property on each skill.

### 8. Append one terminal archive-manager activity

While running, the coordinator updates the archive manager's current status and label but does not append a persistent running activity for skill organization. At the terminal outcome it appends exactly one existing-format activity:

- action: `skill_library_organize`;
- status: `ok` for full completion or `error` for partial/total failure;
- message: disclosure-safe counts;
- error: bounded summary without skill content.

Later manual resolution updates only the run-level marker and does not append a second activity for the same run. The Skills Library does not add a log endpoint or log UI. The Archive Room's existing global activity dialog displays the record.

### 9. Keep the redesigned UI isolated from MCP Registry

The Skills Library modal removes its MCP Registry button and renders:

- right-aligned smart-organize, create, and import actions;
- purpose categories with immutable `默认标签` first;
- searchable skill cards;
- a selected-skill panel with source, primary category, and single-skill category change;
- failure-reason text on failed cards and in selected-skill details;
- top markers for running, completed, partial failure, and resolved outcomes.

The smart-organize button is disabled when the manager is busy, unavailable, or the default category is empty. Manual category mutation controls are disabled during an active organization run to avoid confusing revision conflicts; server revision checks remain authoritative.

The MCP Registry retains its existing independent entry and modal.

### 10. Preserve compatibility and add bounded observability

Existing callers that only consume `skills` continue to work because the list response retains the current field and adds optional top-level fields. Existing create/import/save-from-agent paths assign default metadata after the skill file write; if the metadata write fails, the skill still projects to default on the next read.

Each run emits one structured server start event and one terminal event containing run ID, duration, processed/moved/failed counts, batch count, and stable error code. Logs exclude skill content, model replies, management tokens, and raw failure text. No per-skill terminal logs are emitted, avoiding log amplification.

## Flow

```mermaid
sequenceDiagram
    actor Owner
    participant UI as Skills Library UI
    participant API as Organization Routes
    participant Lock as Archive Manager Coordinator
    participant Catalog as Skill Catalog
    participant AI as Existing Archive Manager

    Owner->>UI: Start smart organization
    UI->>API: POST run with management token
    API->>Lock: Try acquire
    alt Manager busy
        Lock-->>API: Busy
        API-->>UI: 409; keep button disabled
    else Manager idle
        Lock-->>API: Lease
        API->>Catalog: Snapshot default-category skills
        API-->>UI: 202 with runId
        loop Batches of at most 20
            API->>AI: Bounded classification prompt
            AI-->>API: Strict JSON assignments/failures
        end
        API->>Catalog: Validate and atomically apply results
        API->>Lock: Append one terminal activity and release
        UI->>API: Poll list projection
        API-->>UI: Completed or partial-failure marker
    end
```

## Risks / Trade-offs

- [Archive operations not all use the coordinator] → Wrap every current user-visible operation that sets archive-manager status to `working`; add direct concurrent-request tests for each pair.
- [A process crash leaves a stale running result] → Reconcile persisted running summaries on startup before enabling the button.
- [AI output or skill text attempts prompt injection] → Send bounded summaries, mark text untrusted, require JSON-only output, allowlist input slugs, and validate every field before writes.
- [External filesystem edits drift from catalog metadata] → Reconcile projections on every list and compact only during authorized atomic writes.
- [Long runs keep the manager unavailable] → Batch sequentially, cap per-item input, expose running duration, and allow code/config rollback to disable new starts.
- [Partial catalog write corrupts all classifications] → Use repository serialization, symlink checks, temporary-file `fsync`, atomic replace, schema versioning, and corruption tests.
- [Management token retry duplicates a start] → Authorization rejects before mutation; after authorization the non-blocking coordinator makes repeated starts return busy. The client retains the returned `runId`.
- [Adding enriched fields breaks old clients] → Keep the existing `skills` array shape and treat new projection fields as additive.
- [Manual correction races with an active run] → Disable controls in the UI and enforce expected catalog revision server-side.
- [No organization undo] → Keep skill content untouched and preserve failure items in default; rollback affects metadata only, matching the confirmed non-goal.

## Migration Plan

1. Add the catalog repository and characterization tests with the feature flag `VO_SKILL_LIBRARY_ORGANIZATION_ENABLED` disabled.
2. Add enriched read projections; missing catalog data projects every existing skill into `默认标签` without rewriting skill files.
3. Add owner-authorized manual category mutation and default assignment for create/import/save-from-agent.
4. Add the shared coordinator and migrate the three existing user-visible archive-manager working operations.
5. Add the archive-manager classification worker, recovery, activity summary, and new UI module.
6. Enable the feature for local acceptance; verify normal, partial failure, busy, missing manager, empty default, restart recovery, and management-token scenarios.
7. Enable by default after acceptance evidence passes.

Rollback:

- Disable `VO_SKILL_LIBRARY_ORGANIZATION_ENABLED` to prevent new runs and hide/disable organization controls.
- Existing skill CRUD/apply remains functional because `SKILL.md` storage is unchanged.
- Preserve the sidecar catalog for forward recovery; if code rollback cannot read it, it is ignored as a hidden non-directory file.
- If necessary, restore category projection by deleting only the validated sidecar after making a backup; all skills then derive `默认标签`.

## Open Questions

None blocking. Batch size, polling interval, and input-summary byte limits are internal bounded defaults and may be tuned after local acceptance without changing the confirmed product behavior.
