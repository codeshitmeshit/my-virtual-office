## Context

Virtual Office currently has two communication-skill sources. The local `/skills/vo-agent-communication/SKILL.md` file is the current provider-aware contract, while `app/server.py` generates a legacy `AgentPlatform-to-AgentPlatform_Communications` skill and seeds only that generated copy into the OpenClaw Skills Library. Library seeding does not install the skill into agent workspaces, and OpenClaw agent creation writes profile files without installing a communication skill. Consequently an agent can receive a delegation request without seeing the VO contract and can fall back to native session discovery or provider CLI commands.

OpenClaw roster discovery reads `openclaw.json` or falls back to agent directories containing `sessions/`. In contrast, `/vo-config` currently reports `openclaw.detected` from the existence of the configured home directory alone. A residual directory containing only Skills Library data therefore appears available even when no OpenClaw agent can be discovered.

The VO service owns its HTTP communication endpoint and history, its local skill sources, OpenClaw workspace files under the configured home, and agent creation through the gateway. It does not own OpenClaw's internal native-tool dispatcher, so prevention of private fallback is enforced through managed agent instructions and verified through real-agent acceptance rather than a nonexistent VO-side tool interceptor.

## Goals / Non-Goals

**Goals:**

- Use `skills/vo-agent-communication/SKILL.md` as the single ordinary-chat contract for every supported sender and target provider, including Codex, and as the source for runtime, library, and OpenClaw workspace copies.
- Install or refresh a VO-managed copy for every eligible discovered or newly created OpenClaw agent.
- Preserve unrelated skills and files while making reserved VO-managed skill identities deterministic and upgradeable.
- Make cross-agent routing instructions explicitly require current VO roster lookup, provider-aware target selection, the VO communication endpoint, and stable conversation identifiers.
- Return truthful, non-sensitive OpenClaw availability and readiness information.
- Verify routing behavior at helper, API, and real-agent acceptance levels.

**Non-Goals:**

- Intercept or remove OpenClaw native session tools globally.
- Change provider adapters or the payload contract of `/api/agent-platform-communications/send`.
- Auto-route arbitrary natural-language requests in the VO HTTP layer by guessing the intended target.
- Install OpenClaw workspace skills into Codex, Claude Code, or Hermes workspaces.
- Redesign meetings, projects, browser control, or long-running orchestration.

## Decisions

### 1. Treat the repository skill as the canonical source

Add a small canonical-skill loader near the existing built-in skill management code. It reads `skills/vo-agent-communication/SKILL.md`, validates the expected frontmatter identity, and returns content plus a SHA-256 content version. Both the Skills Library entry and agent workspace copies use these exact bytes.

The generated legacy communication body and its constant cease to be an independent source. The canonical skill directly describes routing to OpenClaw, Hermes, Claude Code, and Codex through the same VO endpoint; it does not redirect Codex targets to `vo-codex-communication` or require a second installed chat skill.

After the canonical entry is seeded, the old reserved library entry is eligible for migration only when its `SKILL.md` matches a known VO-generated legacy form and the directory contains no auxiliary files. Migration removes only the positively identified managed file and then removes the directory with `os.rmdir` if empty; it never uses recursive deletion. Unknown, modified, or augmented legacy directories remain untouched and are reported as migration conflicts.

Alternative considered: keep generating an OpenClaw-specific shortened skill. Rejected because it recreates the divergence that caused the incident and makes future routing-rule changes version-dependent.

### 2. Mark and atomically synchronize VO-managed workspace copies

Install the canonical skill at `skills/vo-agent-communication/SKILL.md` in eligible OpenClaw workspaces. A colocated marker records the VO-managed identity and canonical content hash. Writes use a temporary file followed by `os.replace`, under a process-local synchronization lock, so concurrent roster refresh and agent creation cannot expose a partial skill.

Before reading or writing the managed directory, resolve the real paths of `workspace/skills`, the canonical skill directory, the skill file, and marker. Reject the operation if any existing path component is a symlink or if any resolved target leaves the workspace boundary.

Synchronization behavior is idempotent:

- Missing managed skill: create the directory, skill, and marker.
- Matching hash: do nothing.
- Older marked copy: replace only the managed skill and marker.
- Unmarked conflicting file at the reserved canonical path: do not overwrite it silently; report `conflict` readiness so the agent is not represented as communication-ready.
- Unrelated workspace skill or file: never modify it.

The previous generated legacy workspace skill, when present with content matching a known VO-managed legacy form, is removed after canonical installation. A non-matching legacy path is reported as a migration conflict instead of being deleted.

Alternative considered: call the public Skills Library apply handler for synchronization. Rejected because that handler depends on refreshed compatibility maps, overwrites without managed ownership metadata, and cannot safely distinguish a VO-managed copy from user content.

### 3. Synchronize at discovery refresh and agent creation boundaries

After OpenClaw discovery produces normalized agent records, run bounded synchronization once for each OpenClaw agent and attach a non-sensitive readiness object to its record (`ready`, `updated`, `conflict`, or `error`). This occurs only on the existing discovery refresh boundary rather than on every roster read. The skill is small, and checksum comparison makes the steady-state cost proportional to the number of discovered OpenClaw agents with constant-size file reads. Agent-originated communication rejects an OpenClaw sender whose readiness is explicitly non-ready; this prevents a conflict or sync error from being merely diagnostic while preserving human-to-agent and non-OpenClaw routes.

For `_handle_agent_create`, install the canonical skill immediately after the gateway creates the workspace and profile files, before returning success and refreshing discovery. If installation fails, return a partial-creation error that names the agent and skill-readiness failure; do not claim that the agent is ready for cross-agent delegation. Re-running discovery can repair missing managed copies idempotently.

The archive-manager creation path also goes through the same explicit synchronization helper because it creates an OpenClaw agent outside `_handle_agent_create`.

Alternative considered: perform writes from every `/api/agents` request. Rejected because read endpoints should not repeatedly mutate disk and concurrent polling would amplify races and log noise.

### 4. Strengthen new-agent base instructions without rewriting user profiles

Update the OpenClaw `AGENTS.md` template so new agents are told to invoke the installed `vo-agent-communication` skill for office-agent delegation and never use private sessions or provider CLI as fallback. Existing profile files are not rewritten because they may contain user-authored identity and operating rules; existing agents receive the behavior through the managed skill itself.

Alternative considered: rewrite all existing `AGENTS.md` files. Rejected because VO cannot reliably separate user-authored profile content from generated content.

### 5. Centralize OpenClaw home inspection

Add a discovery-level inspection result that distinguishes:

- valid configuration with at least one valid configured agent;
- no configuration but at least one fallback agent directory accepted by discovery;
- missing home;
- residual/empty home;
- malformed configuration.

`discover_agents` and `_build_safe_vo_config` consume the same inspection logic, preventing roster and `detected` from disagreeing. The inspector validates that both the root document and nested `agents` value are dictionaries before reading `agents.list`. If `openclaw.json` is syntactically malformed or structurally invalid, discovery returns `malformed_config` and does not fall back to guessed directory agents. `/vo-config` keeps the existing boolean `detected` field for compatibility and adds a non-sensitive reason/readiness summary; it does not expose configuration contents or paths beyond the already exposed configured home.

Alternative considered: define detection as gateway reachability. Rejected because agent discovery is currently filesystem-authoritative and a reachable gateway does not prove that VO can resolve configured agent identities.

### 6. Preserve the existing communication endpoint and history contract

No new send endpoint is introduced. The canonical skill instructs agents to query `/api/agents`, confirm sender and target identities/provider kinds, and call `/api/agent-platform-communications/send` for all provider kinds, including Codex. Existing request/reply persistence remains the audit source. Tests assert stable `conversationId`, actual sender/target fields, Codex routing through the same endpoint, readiness rejection, and terminal status handling.

The server does not attempt to parse delegation intent or silently retry. Ambiguous targets, unavailable VO, busy targets, timeouts, and empty replies remain visible terminal outcomes.

## Risks / Trade-offs

- [OpenClaw can still ignore instructions and invoke a native tool] → Install the skill automatically, strengthen new-agent base instructions, expose readiness/conflicts, and require a real OpenClaw acceptance scenario. Full tool-level prohibition would require an OpenClaw policy hook outside this VO change.
- [Discovery now performs bounded writes] → Run synchronization only on startup/refresh and explicit creation, compare hashes before writing, use atomic replacement and a process lock, and avoid writes on ordinary roster reads.
- [A user already occupies the reserved canonical path] → Never silently overwrite an unmarked conflicting copy; expose conflict state and leave unrelated data intact.
- [Legacy migration can destroy customized data] → Never recursively delete; require known generated content and an exact managed file set, unlink only the known file, remove only an empty directory, and preserve/report every conflict.
- [Workspace-internal symlinks can redirect writes] → Reject symlinked path components and verify resolved skill/marker targets remain inside the real workspace before every managed write.
- [Agent creation can partially succeed before skill installation fails] → Return a precise partial-creation error and make discovery synchronization repairable and idempotent; do not delete the already-created agent automatically.
- [Malformed OpenClaw configuration previously fell back to directory scanning] → Prefer a deterministic unavailable result over guessed identities; surface a non-sensitive reason so the user can repair configuration.
- [Additional readiness fields may be ignored by older clients] → Keep existing response fields and boolean semantics compatible; additions are optional and no existing endpoint payload is removed.

## Migration Plan

1. Land canonical loading, managed synchronization, and detection inspection behind existing startup/discovery boundaries; no external configuration flag is required because synchronization is idempotent and scoped to reserved VO-managed paths.
2. On startup or first Skills Library read, seed `vo-agent-communication` from the repository source.
3. On the next OpenClaw discovery refresh, install or refresh canonical workspace copies and classify conflicts/errors.
4. Remove only a positively identified legacy managed file after canonical seeding/install succeeds; preserve unknown, modified, or augmented directories as conflicts.
5. Verify unit and integration tests, then run one real OpenClaw delegation such as “让分析师看一下最近市场动向”; confirm VO history contains the request/reply and native session/CLI tools were not used.

Rollback consists of reverting the code. Canonical workspace copies can remain because they describe the already-supported VO endpoint; no persistent schema migration is required. If rollback must restore the previous library trigger temporarily, the previous generated entry can be reseeded without deleting the canonical copy.

## Open Questions

None blocking. A future OpenClaw integration may add provider-native tool policy enforcement, but this change does not depend on that external capability.
