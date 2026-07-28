# Project Agent Instructions

## Highest-Priority Constraint

- This constraint takes precedence over all other implementation preferences in this file: for every new requirement, default to placing the implementation in one or more new, focused files. Do not append new logic to existing large files unless the change is both minimal and unquestionably part of that file's existing responsibility.

## Workflow Constraints

- Do not invoke or use the `hammer` skill or any `hammer-*` skill in this repository.
- If a task would normally trigger a Hammer workflow, skip Hammer and handle the task directly with ordinary repository inspection, implementation, testing, and review.
- Do not create, restore, or rely on `.hammer/` workflow files or Hammer gates for this project.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## Modularity and Complexity Constraints

- Prefer implementing every new API, route group, integration, background job, or substantial feature in a new, focused module instead of adding more business logic to a large legacy file such as `app/server.py`.
- Keep legacy entry-point files limited to transport handling, route registration, dependency wiring, and thin compatibility delegation. Put validation, orchestration, state transitions, and persistence decisions in the owning module.
- New modules must depend on explicit interfaces or injected collaborators and must not import a legacy entry-point module to reach its globals or helpers. Avoid circular imports, duplicated state authorities, and hidden cross-module mutation.
- When modifying an existing feature in a highly coupled file, extract the touched responsibility into a focused module when it is safe and proportionate to the change. Do not make the legacy file larger by default.
- Preserve public behavior and compatibility during extraction, but remove obsolete compatibility delegates and duplicate implementations after their callers have migrated.
- Treat reduced coupling, smaller responsibility boundaries, readability, and maintainability as required implementation outcomes. The project should become incrementally simpler with each change rather than accumulating more logic in shared files.
- If keeping new logic in an existing legacy file is genuinely necessary, document the reason and keep the addition as small and isolated as possible.
