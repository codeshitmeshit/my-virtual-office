# Archive Room Phase 1-3 Review

## Product Review

The product scope is sufficiently clear for Phase 1-3.

Confirmed:

- Archive Room is a first-level main application module.
- This sub-requirement intentionally covers only the first three phases:
  - Archive data foundation.
  - Main navigation and project overview.
  - Project archive detail and artifact preview.
- Archive management AI, automatic整理, reminders, onboarding package APIs, and context query APIs are explicitly outside this sub-requirement.
- Phase 1-3 keeps only a minimal archive management AI placeholder, such as future-enabled or not-connected state. It does not auto-create or operate the archive management AI.
- Phase 1-3 includes a human-readable standard onboarding package that users can view and copy, but does not validate automatic AI loading.
- Phase 1-3 artifact scope is limited to artifacts explicitly associated with projects or tasks.
- Phase acceptance is a checklist structure and implementation planning concept, not an Archive Room feature.
- Project artifacts include documents, images, video, audio, and fallback handling for unsupported files.

Remaining product risks:

- Existing project/task records may not yet contain enough risk, active AI, pending confirmation, or artifact metadata to fully populate every overview field. Phase 1-3 should degrade gracefully with empty, zero, unknown, or derived values.
- "Confirmed fact", "AI inference", and "pending confirmation suggestion" may initially be mostly metadata scaffolding until later AI整理 phases populate richer data.
- Artifact discovery may depend on how current task outputs are stored. Phase 1-3 should support manually or programmatically registered artifact metadata rather than trying to infer every file in the workspace.
- Because automatic AI onboarding is out of scope, "new AI can understand the project" is a soft acceptance signal based on readable archive content, not an automated AI integration test.

No blocking product questions remain for checklist drafting.

## Technical Review

### Architecture And Data

The current VO server already centralizes durable local state under `VO_STATUS_DIR` and project persistence through existing project files/stores. Phase 1 should follow that pattern and add archive-specific project data under a stable archive location. The design should avoid moving existing project/task/chat data.

Recommended data principles:

- Use archive metadata files under `VO_STATUS_DIR`.
- Keep source references to existing project/task/meeting/chat records instead of copying raw histories.
- Store artifact metadata separately from the physical file path.
- Normalize preview access through an allowlisted server route rather than exposing raw filesystem paths.

### Frontend Integration

Archive Room should be added as a main app entry and rendered as a work-focused operational view. Since the application already has dense project and office UI patterns, Phase 2-3 should avoid a marketing-style landing page and focus on overview, filtering/sorting, and detail inspection.

Frontend considerations:

- Add a clear first-level "档案室" entry.
- Preserve existing project navigation and chat behavior.
- The overview should handle missing archive fields gracefully.
- The detail view should separate context, decisions/risks/rules, and artifacts.
- Media preview should use browser-native controls where possible.

### File Preview And Security

Artifact preview is the main risk area in Phase 1-3.

Required safeguards:

- Do not allow arbitrary path query access.
- Resolve paths only from known archive/artifact roots or registered artifact metadata.
- Block path traversal.
- Return clear fallback for unsupported preview types.
- Keep download/open behavior bounded to allowed files.

### Compatibility And Migration

Phase 1-3 should be additive:

- No destructive migration of existing projects.
- No forced rewrite of project files.
- Existing project/task/chat/meeting APIs should remain compatible.
- Existing Archive Room full requirement files should not be overwritten by this sub-requirement.

### Observability

Phase 1-3 does not include archive manager activity logs, but should still make user-visible data states clear:

- Empty archive.
- Missing fields.
- No artifacts.
- Unsupported preview type.
- Source unavailable.
- Data load failure.

## Review Conclusion

No blocking technical questions remain for Phase 1-3 checklist drafting.

Implementation should proceed only after the checklist is confirmed. The next artifact after checklist confirmation will be `todolist.md`.
