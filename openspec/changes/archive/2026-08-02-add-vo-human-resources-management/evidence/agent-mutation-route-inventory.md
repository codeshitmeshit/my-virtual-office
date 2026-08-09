# Agent Mutation Route Inventory

Task: `14.1`

Captured against: current worktree before Agent Management authorization changes

Purpose: characterize every existing write path that can alter an Agent's
identity, appearance, Provider/runtime settings, branch, workspace, assignment,
binding, creation, or deletion.

This is a migration inventory, not a statement that the current authorization
is acceptable. `Current actor check: none` identifies a known pre-migration
condition that later tasks must remove without silently breaking callers.

## Disposition vocabulary

- **keep**: preserve the route and its owning domain.
- **delegate**: preserve compatibility at the route while moving the relevant
  mutation through the new field-level configuration or high-risk command
  service.
- **split**: keep unrelated workspace/domain actions in their existing owner,
  but delegate Agent configuration fields to the new authority.
- **read-only**: preserve reads but remove mutation behavior.
- **remove**: delete an obsolete duplicate after callers migrate.

## Direct Agent and office mutation routes

| Method and route | Mutated scope and current persistence authority | Current actor check | Known callers | Required disposition |
|---|---|---|---|---|
| `POST /api/office-config` | Replaces the entire `VO_STATUS_DIR/office-config.json`; includes Agent name, legacy role, emoji, colors, appearance, branch, `statusKey` binding, Provider metadata, office layout, furniture, and branches | none; accepts browser JSON and sends wildcard CORS | `app/game.js` `saveOfficeConfig`, full reset, office editor, legacy `_acp*` editor | **split/delegate**: preserve office-layout compatibility, but prohibit whole-document Agent/branch/binding mutation; route Agent fields through the profile service and confirmed high-risk service |
| `POST /api/agent-workspace/{agent}` | Mixed authority: `agent-workspaces.json`, office-config Agent overrides, scores, workspace files, `HEARTBEAT.md`, Agent skills, and shared Skill library | none; target Agent comes from the URL and `actor` comes from the body | `app/game.js` `_agentWorkspacePost` and Agent Workspace forms | **split/delegate**: profile `updateSettings` fields use the new profile/high-risk policy; retained notes/tasks/files/skills actions receive an explicit authorized actor boundary in their owning domain |
| `POST /api/agent/create` | Creates a real OpenClaw/Hermes/Codex/Claude Code Agent, Provider workspace/profile files, communication Skill state, and refreshed roster state | none | `app/game.js` `_acpCreateNewAgent` | **delegate** to authenticated-human high-risk command with a payload-bound confirmation challenge |
| `DELETE /api/agent/delete` | Deletes the real Provider Agent and Provider-specific history/files; system-role deletion policy already protects `main`, HR, and archive manager | none | `app/game.js` `_acpDeleteAgent` | **delegate** to authenticated-human high-risk command with a payload-bound confirmation challenge; retain system-role policy |
| `POST /api/agent/{agent}/skills` | Creates or replaces a Skill in the selected real Agent workspace | none; target Agent comes from the URL | legacy Skill editor in `app/game.js`, using raw `fetch` | **keep** in the Skill/workspace owner, add management authorization, and do not expose through low-risk Agent profile mutation |
| `DELETE /api/agent/{agent}/skills/{skill}` | Removes a Skill from the selected real Agent workspace | none; target Agent comes from the URL | legacy Skill editor in `app/game.js`, using raw `fetch` | **keep** in the Skill/workspace owner with management authorization |
| `POST /api/skills-library`, `/api/skills-library/apply`, `/api/skills-library/save-from-agent`, `/api/skills-library/upload` and `DELETE /api/skills-library/{skill}` | Mutates the shared Skill library or copies Skills between the library and a selected Agent workspace | none in the current generic routes | Skill editor and Agent Workspace in `app/game.js` | **keep** in the Skill owner with management authorization; Agent-targeted apply/save must use a server-authorized target |
| `POST /set-model` | Writes a host-watcher `set-model` request for one OpenClaw Agent | none | no current application caller found; superseded by `/api/native-models/openclaw/agent-model` | **remove** after compatibility confirmation |

## Agent workspace action split

`POST /api/agent-workspace/{agent}` multiplexes the following current actions:

| Action group | Current persistence authority | Configuration relevance | Required disposition |
|---|---|---|---|
| `updateSettings` | `agent-workspaces.json`, `office-config.json`, score store, and optional `HEARTBEAT.md` | Directly mutates name, display name, legacy role, emoji, color, branch, cron, heartbeat, task mode, and leaderboard points | **split/delegate** name/role/emoji/color to low-risk profile commands; branch to confirmed high-risk command; keep other settings in explicit workspace owners behind management authorization |
| `addBulletin`, `updateBulletin`, `deleteBulletin`, `addTask`, `updateTask`, `toggleTask`, `startTask`, `completeTask`, `deleteTask`, `setTaskMode`, `addNote`, `updateNote`, `deleteNote` | `agent-workspaces.json` | Not Agent profile configuration, but currently shares the untrusted route | **keep** in Agent Workspace with an explicit authorized actor boundary |
| `readFile`, `saveFile`, `createFile`, `deleteFile` | real Agent workspace files | Workspace writes are high impact and currently share the untrusted route | **keep** in the workspace domain, management-authorized; do not expose through low-risk Agent profile mutation |
| `saveAgentSkill`, `deleteAgentSkill`, `saveLibrarySkill`, `applyLibrarySkill`, `saveAgentSkillToLibrary` | Agent workspace skills and shared Skill library | Skill installation/removal is high impact and outside profile fields | **keep** in the Skill/workspace owners, management-authorized |

The existing route accepts an arbitrary body `actor` label; that value is
display metadata only and must not become authorization evidence.

## Provider, model, workspace, and binding routes

| Method and route family | Mutated scope and current persistence authority | Current actor check | Known callers | Required disposition |
|---|---|---|---|---|
| `POST /setup/save` | `vo-config.json`; global OpenClaw/Hermes/Codex/Claude Code configuration including workspace roots, default models, gateway and Provider settings | management token in the route | `app/setup.html`, `app/game.js` settings | **keep** for global setup; per-Agent Agent Management changes must not write this whole document |
| `POST /api/native-models/openclaw/agent-model` | host-watcher request changing one OpenClaw Agent model | management token through the `/api/native-models/*` prefix guard | `app/index.html`, `app/game.js`, `app/models.html`, all using `managementFetch`/the managed helper | **delegate** to the confirmed high-risk Agent command while retaining the Provider adapter |
| `POST /api/native-models/hermes/profile-model` | Hermes profile YAML model/provider/base URL | management token through the `/api/native-models/*` prefix guard | `app/models.html` managed helper | **delegate** to the confirmed high-risk Agent command while retaining the Hermes adapter |
| `POST /api/native-models/{openclaw,hermes}/{auth,provider}/*` | Provider credentials and custom Provider definitions | management token through the `/api/native-models/*` prefix guard | `app/models.html` managed helper | **keep** as global Provider administration; never expose to an ordinary Agent session |
| `POST /config/providers/{save-key,delete-key,save-custom}` | OpenClaw Provider keys/custom Provider definitions | management token through the `/config/providers/*` prefix guard | `app/models.html` uses `managementFetch` | **keep** as global Provider administration; never expose to an ordinary Agent session |
| Agent fields inside `office-config.json`: `statusKey`, `providerKind`, `providerAgentId`, `profile` | Visual-Agent to real Provider-Agent binding and Provider identity hints | none through `POST /api/office-config` | legacy `_acp*` editor | **delegate** to a confirmed high-risk binding command; the future profile store may read legacy values but may not accept them from low-risk self-service |
| Agent `branch` inside `office-config.json` and Agent Workspace `updateSettings` | Agent branch membership | none through both current routes | legacy `_acp*` editor and Agent Workspace settings | **delegate** to a confirmed high-risk branch command |

## Project assignment routes

| Method and route family | Mutated scope and current persistence authority | Current actor check | Known callers | Required disposition |
|---|---|---|---|---|
| `PUT /api/projects/{project}` | Project defaults including default executor/reviewer fields | management token in `do_PUT` for `/api/projects/*` | project UI and tests | **keep** in the project domain; when initiated from Agent Management, require the high-risk confirmation service before delegating |
| `PUT /api/projects/{project}/tasks/{task}` | Task `assignee`, `executorAgentId`, and `reviewerAgentId` | management token in `do_PUT` for `/api/projects/*`; system-role assignment policy validates targets | project UI and workflow management | **keep** in the project domain and retain system-role policy; Agent Management entry uses confirmed high-risk assignment |
| `POST`/`DELETE /api/projects/*` management mutations | Project/task creation, execution controls, and deletion that can establish or remove assignments | management token in the `do_POST`/`do_DELETE` project prefix guards, except the separately governed Agent meeting-request path | project UI, workflow services, and tests | **keep** in the project domain; do not duplicate persistence in Agent profile storage |

Project assignment data remains project-owned. “Assignment” in Agent Management
is an orchestration entry into the project service, not a new assignment column
in the profile store.

## Reviewed routes outside configuration authority

The following Agent-addressed mutations were reviewed but do not belong in the
new profile store or high-risk configuration service:

| Route family | Existing owner and boundary | Inventory decision |
|---|---|---|
| `POST /api/presence/{agent}` | Presence broker/manual override; changes ephemeral office activity, not profile configuration | Keep in the presence domain. Its trusted Agent actor model must remain separate from browser Agent Management sessions. |
| `POST /api/agent-platform-communications/send` | Agent communication application service with its own sender/target validation and history | Keep in the communication domain; do not route through profile configuration. |
| `POST /api/agent/project-authoring/*` | Project-authoring service using the originless loopback Agent action boundary | Keep in project authoring; it may create project assignments under that specification but does not edit Agent configuration. |
| `POST /api/agent-human-resources/*` and Human Resources management commands | HR governance/application services | Keep in HR. Profile introduction reconciliation uses an injected port rather than direct cross-domain writes. |
| Chat/run/approval/history routes under Provider-specific paths | Provider execution/session owners | Keep out of Agent Management configuration unless a later confirmed requirement explicitly adds one of those operations. |

## Browser caller characterization

Current caller behavior is intentionally recorded because server authorization
must not be inferred from the client:

- `app/game.js` uses raw `fetch` for office-config writes, Agent Workspace
  writes, Agent creation/deletion, Agent Skill writes/deletes, and Skill Library
  application.
- `app/game.js`, `app/index.html`, `app/models.html`, and `app/setup.html` use
  `managementFetch` (directly or via a managed helper) for setup/native Provider
  operations.
- Client use of `managementFetch` is not sufficient authorization unless the
  corresponding server route also rejects a missing/invalid management token.

## Migration invariants

Later tasks must preserve these invariants:

1. There is no write path where a browser-selected Agent ID establishes actor
   authority.
2. Every retained legacy entry is management-authorized and delegates relevant
   Agent configuration to one field-level/high-risk policy, or it becomes
   read-only/removed.
3. Ordinary Agent self-service never receives Provider, branch, workspace,
   assignment, binding, create, delete, model, credential, file, Skill, cron,
   heartbeat, score, or project mutation authority.
4. Project assignment, workspace files/skills, Provider configuration, and HR
   data retain their existing domain owners; the profile store does not become
   a duplicate persistence authority.
5. Characterization tests are updated only when the corresponding migration
   task intentionally changes a documented route and supplies replacement
   authorization tests.
