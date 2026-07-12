## Why

Project execution, review, artifact, and scheduling workflows form the largest business domain inside `app/server.py`. After the pilot boundary is proven, these workflows should be separated so their state transitions and failure behavior can be tested without HTTP coupling, while measured backend bottlenecks in the migrated paths are reduced.

## What Changes

- Extract project and task operations into cohesive project-domain services.
- Extract execution lifecycle, reviewer/rework/acceptance workflow, artifact access, and project scheduling in bounded slices.
- Preserve existing execution states, confirmation gates, idempotency, workspace safety checks, persistence formats, and API contracts.
- Allow confirmed bugs discovered during migration to be fixed in the owning slice when the defect is reproducible, covered by regression tests, and documented as an intentional compatibility exception.
- Improve backend performance in migrated paths by eliminating evidenced redundant project-store reads and writes, avoiding repeated scans where compatibility can be preserved, and measuring the result against a pre-change baseline.
- Introduce project-scoped atomic updates for migrated state transitions to prevent lost updates and duplicate starts without holding locks across provider, notification, filesystem, or network work.
- Keep frontend interaction and visual behavior outside this change.
- Remove migrated business orchestration from HTTP handlers after each slice passes compatibility tests.
- This change starts only after `extract-http-foundation-and-project-service-pilot` is accepted and archived.

## Capabilities

### New Capabilities

- `project-execution-service-boundaries`: Defines independently testable service ownership for project execution and its supporting workflows.

### Modified Capabilities

None currently; detailed review must reassess whether any existing project behavior requirements require delta specs.

## Impact

- Expected code: `app/server.py`, `app/project_store.py`, new project-domain service modules, and project/execution tests.
- Public API and persistence formats are intended to remain compatible.
- Verified bug fixes may intentionally change defective behavior, but must not introduce unrelated product changes or silent contract drift.
- Backend performance improvements and project-level concurrency fixes are intentional goals; frontend UX changes are not included.
- Detailed design and tasks are deferred until the first change establishes the accepted service conventions.
