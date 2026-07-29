## 1. Classification Catalog

- [x] 1.1 Add `app/services/skill_library_catalog.py` with schema-versioned categories, immutable `默认标签`, five seeded purpose categories, one primary category, optional tags, revision checks, symlink rejection, and atomic replacement; add focused repository tests for defaults, validation, corruption recovery, and atomic-write failure.
- [x] 1.2 Integrate catalog projection with existing skill listing and create/import/save-from-agent/delete paths so uncatalogued on-disk skills derive `默认标签` and stale entries compact only on authorized writes; add compatibility tests proving existing `skills` consumers and skill-file CRUD behavior remain valid.

## 2. Archive Manager Mutual Exclusion

- [x] 2.1 Add `app/services/archive_manager_work_coordinator.py` with a non-blocking single-holder lease, holder metadata, deterministic release, and stale-start recovery hooks; add unit tests for acquire, busy rejection, release-on-error, and restart reconciliation.
- [x] 2.2 Wire the coordinator into manual archive maintenance, archive-manager AI refinement, and archive-count audit with thin changes to existing entry points; add concurrency and regression tests proving a later operation is rejected rather than queued and manager status returns to a valid terminal state.

## 3. Skill Organization Domain

- [x] 3.1 Add the bounded archive-manager classification prompt and strict response parser in `app/services/skill_library_organization.py`; test 20-item batching, 2 KiB summaries, untrusted-content isolation, JSON-only parsing, unknown/duplicate/missing slugs, invalid categories, unsafe values, and oversized tags.
- [x] 3.2 Implement asynchronous run creation, default-category snapshotting, sequential batch execution, partial assignment application, custom ordinary-category creation, terminal run summaries, and one terminal archive-manager activity; test complete, partial, total failure, timeout, unavailable/paused manager, and direct-apply-without-undo behavior.
- [x] 3.3 Implement persisted-run recovery, marker dismissal, revision-protected single-skill manual correction, failure-count decrement, and final `resolved` transition without adding per-skill lifecycle state; add focused recovery, race, stale-revision, and resolution tests.

## 4. HTTP and Authorization

- [x] 4.1 Add `app/server_routes/skill_library_organization.py`, explicit runtime dependency wiring, and additive read projections for categories, organization result, catalog revision, and archive-manager state; cover route registration and response compatibility.
- [x] 4.2 Add management-token authorization before body parsing for run start, marker dismissal, and manual category mutation; add HTTP contract tests for missing, invalid, and valid owner credentials plus stable busy, unavailable, disabled, validation, and revision-conflict error codes.
- [x] 4.3 Add `VO_SKILL_LIBRARY_ORGANIZATION_ENABLED` rollout handling so disabled deployments cannot start runs while existing skill CRUD/apply remains available; test disabled, enabled, and rollback-compatible sidecar behavior.

## 5. Skills Library Interface

- [ ] 5.1 Add `app/skills-library-organization-ui.js` and `app/skills-library-organization.css`, minimally update the modal bootstrap, and implement the three-column searchable library with right-aligned smart-organize/create/import actions, purpose categories, selected-skill details, and no Skills Library MCP entry; add static structure and responsive-layout checks.
- [ ] 5.2 Implement running, completed, partial-failure, and resolved top markers; persist dismissal behavior, poll only while running, disable smart organization for busy/unavailable/empty-default conditions, and stop polling at terminal state; add DOM tests for every state and duplicate-click prevention.
- [ ] 5.3 Implement partial-failure navigation to a filtered `默认标签` view and owner-authorized single-skill category correction through `managementFetch`; add DOM tests for failure badges, revision conflicts, real-time count reduction, final resolution, and disabled mutation controls during active organization.

## 6. Localization, Documentation, and Acceptance

- [ ] 6.1 Add Chinese and English copy for categories, controls, markers, errors, and accessibility labels; update Skills Library documentation to describe the sidecar metadata, owner boundary, archive-manager reuse, MCP separation, and absence of team-space or organization-lifecycle concepts.
- [ ] 6.2 Add an end-to-end acceptance fixture covering at least 100 default-category skills, multi-batch completion, partial failure, manual repair, archive-manager activity visibility, busy prevention across archive operations, restart recovery, and management-token prompting; capture reproducible commands and evidence for the later OpenSpec verification gate.
- [ ] 6.3 Run focused Python and JavaScript suites plus Skills Library, Archive Room, management-token, route-split, MCP Registry, and direct-filesystem regression checks; document observed duration/count logs, feature-flag rollback results, residual risks, and any unverified environments in `verification-evidence.md`.
