## Context

The repository currently exposes one main application entry point (`app/index.html`), three standalone application pages (`app/setup.html`, `app/models.html`, `app/cron.html`), and one public frontend (`website/index.html`). The main entry point loads more than a dozen feature style modules. Those modules share DOM and JavaScript behavior but currently implement overlapping token, typography, component, dialog, close-control, and feedback systems.

The target source of truth is the Figma page [`00 · SYSTEM UI STANDARD · AI START HERE`](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=356-240). CodeGraph discovery and current-source verification are recorded in [`analysis/modification-points.md`](analysis/modification-points.md). The design below is limited to confirmed modification points `MP-01` through `MP-11`.

This is a frontend-only migration. Existing handler boundaries, DOM integration contracts, API calls, payloads, persistence timing, polling, SSE/WebSocket behavior, retry behavior, and business state transitions are compatibility constraints, not redesign opportunities. The current dirty working tree is part of the baseline and must be preserved.

The existing change `redesign-settings-large-modal` remains the behavioral baseline for settings. Frames `147:2` and `148:3` remain the workflow-composition baseline for project orchestration. The canonical system standard wins for shared tokens, components, action semantics, icons, focus, dialogs, and feedback.

### Figma delivery

The following editable frames were added without overwriting earlier approved work:

- [Representative high-fidelity context](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=387-744): reuses the approved settings modal in real Virtual Office context and identifies the surfaces that inherit the same system semantics.
- [Interaction overview](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=387-745): maps 16 numbered interactions to visual response, loading, success, error, retry, focus, and persistence behavior.
- [Storage and submission](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=387-746): separates browser-local preferences, general server configuration, sensitive integrations, and domain data; documents commit ordering and partial failure.

Programmatic inspection found no placeholder text, font mismatch, clipped text, top-level overflow, or missing interaction numbers. All text in the three delivery frames uses `Noto Sans SC` Regular, Medium, or Bold.

## Goals / Non-Goals

**Goals:**

- Establish one canonical semantic token foundation for every repository-owned frontend entry point.
- Give equivalent controls one component contract while preserving existing class names and handlers where possible.
- Distinguish close, delete, clear, remove, save, test, navigation, and danger semantics.
- Provide a shared dialog presentation and a shared feedback queue without changing business results.
- Migrate all current surfaces, including uncommitted settings, office-branding, and personal-assets frontend work.
- Preserve domain visuals such as the office canvas and orchestration pipeline while standardizing their surrounding chrome.
- Add repeatable static, interaction, responsive, and visual acceptance evidence.

**Non-Goals:**

- Changing backend routes, services, repositories, providers, data files, protocols, configuration formats, SSE, WebSocket, or business state machines.
- Rewriting feature renderers or consolidating independent domain models.
- Changing request order, persistence timing, test side effects, retry semantics, or confirmation strength.
- Replacing the office pixel-art scene, avatar art, charts, project pipeline geometry, or public-site marketing composition.
- Completing unrelated work from another active change or reverting user modifications.
- Introducing a framework, build pipeline, external UI dependency, or second global design system.

## Decisions

### D1. Add a canonical token layer before every feature stylesheet (`MP-01`)

Create `app/ui-system.css` and load it before feature styles in `app/index.html`. It will own the canonical custom properties for canvas, surface, toolbar, panel, text, accent, semantic statuses, spacing, radii, typography, focus, and motion preferences.

The current `app/style.css:138-147` properties (`--ui-bg`, `--ui-surface`, `--ui-border`, `--ui-text`) become compatibility aliases into the canonical namespace. In particular, the current `--ui-surface: #1a1a2e` is corrected by mapping Surface to `#12121E` and Panel to `#1A1A2E` rather than treating both as the same value.

`app/fonts.css:9-20` stops applying a pixel font to every Chinese descendant. Product UI uses the Figma typography family and hierarchy; technical values retain `--vo-technical-font`; pixel typography remains explicitly scoped to office/brand domain visuals.

Canonical values:

| Semantic role | Value |
| --- | --- |
| Canvas | `#0A0A0F` |
| Surface | `#12121E` |
| Toolbar | `#151520` |
| Panel | `#1A1A2E` |
| Primary text | `#E8E8F0` |
| Muted text | `#888888` |
| Accent | `#FFD700` |
| Success | `#4CAF50` |
| Info | `#4FC3F7` |
| Warning | `#FFB300` |
| Danger | `#F44336` |
| Spacing | `2/4/6/8/12/16/24/32px` |
| Radius | `4/6/8/12px` and pill |
| Type sizes | `8/9/10/12/14/18px` with the Figma line-height hierarchy |

Alternative rejected: defining a `:root` per feature. It would preserve the current divergence and make static enforcement ambiguous.

### D2. Use a shared component compatibility layer instead of mass DOM renaming (`MP-02`)

Create `app/ui-components.css`. It defines canonical contracts for button, navigation item, input, select, textarea, toggle, card, badge, status, and icon control. Existing feature classes are mapped into those contracts with grouped selectors; feature CSS remains responsible for layout and domain-specific geometry.

`app/window-controls.css:2-96` changes `--vo-close-*` from danger-red to a neutral close treatment. Delete remains danger and continues to require its existing confirmation. Clear and remove remain separate actions with their own documented meaning.

Every shared control contract includes default, hover, active, focus-visible, disabled, loading, invalid/error, and success treatment where applicable. Color supplements text, icon, `aria-*`, or status copy; it is not the only state signal.

Alternative rejected: renaming every feature class to `ui-*`. That would create unnecessary DOM/test churn and raise the risk of breaking renderer and selector contracts.

### D3. Move generic dialog styling out of JavaScript while preserving dialog state (`MP-03`)

Create `app/ui-dialogs.css`. `app/vo-dialogs.js::ensureStyles()` no longer injects a competing CSS string; it only ensures the external contract is available or becomes a no-op after the stylesheet is loaded.

The following variables and flows remain unchanged:

- `activeDialog` remains `null | {kind, overlay, resolve, keydown}`.
- `show(options)` still creates the same result contract for alert, confirm, and prompt.
- `removeActive(result)` still removes the keydown listener and resolves exactly once.
- Enter, Escape, initial focus, input selection, and caller-facing Promise values remain unchanged.
- Backdrop click is not added to the generic dialog because it is not part of its current behavior. Feature surfaces keep backdrop close only where already supported.

The visual change adds canonical dialog shell, actions, focus-visible, accessible title association, and neutral/danger action tones.

Alternative rejected: replacing `voAlert/voConfirm/voPrompt` with browser-native dialogs. Native dialogs cannot meet the UI standard and would change focus and asynchronous behavior.

### D4. Introduce one queued feedback boundary with legacy adapters (`MP-04`)

Create `app/ui-feedback.js` and `app/ui-feedback.css` exposing `window.VOFeedback`. Its input contract is `{message, tone, persistent, action, duration}` and its runtime state is a queue of independent feedback items.

The existing functions remain callable as thin adapters:

- `ProjMgr::toast(msg, type)`
- `_acpShowToast(msg)`
- `_archiveToast(message, type)`
- `_showOfficeToast(msg)`
- `_sklToast(message)`
- `VOSettingsSaveFeedback::{start, success, failure}`

Newly touched callers pass explicit tone. Legacy single-argument calls remain supported during migration, but emoji parsing is not the long-term semantic contract. Multiple transient messages stack instead of overwriting one element. Success/info use `role=status`; blocking errors use `role=alert` and may remain persistent with a retry action.

Settings keeps its inline footer status because it belongs to the form lifecycle. The shared boundary supplies its visual tone, not a replacement business flow.

Alternative rejected: converting every failure to a toast. Field errors and workflows requiring correction need persistent inline, banner, or dialog feedback.

### D5. Separate the main shell from the office domain visual (`MP-05`)

Create `app/ui-main-shell.css` for toolbar, sidebar, modal shell, chat, SMS, browser, monitor, and office-surrounding chrome. It consumes D1-D4 and is loaded after the primitive layers but before feature-specific layout styles.

`app/game.js`, `app/chat.js`, `app/sms-panel.js`, `app/browser-panel.js`, and `app/sidebar-ui.js` keep their existing state writes (`open`, `hidden`, `minimized`, floating geometry, CSS runtime variables, polling, and local-storage keys). Runtime geometry such as `--sms-toolbar-clearance` remains inline because it is state, not competing static presentation.

The office canvas, furniture, weather art, avatars, and other rendered scene content remain a documented domain-visual exception. Toolbar, controls, dialogs, and feedback around that canvas are not exceptions.

Alternative rejected: refactoring `app/game.js` as part of the migration. Its size and behavioral reach make that materially riskier than a stylesheet-first compatibility migration.

### D6. Migrate settings and people-management surfaces without changing their state objects (`MP-06`)

The following state sources remain authoritative:

- `AgentManagement.state` in `app/agent-management.js:4-22`
- `HumanResources.state` in `app/human-resources.js:4-30`
- `PersonalAssets.state` in `app/personal-assets.js:4-35`
- settings draft/save state in `app/settings-modal-ui.js`, `app/settings-save-feedback.js`, and `app/settings-save-transport.js`

CSS in `settings-modal.css`, `agent-management.css`, `human-resources.css`, `human-resources-figma.css`, `personal-assets.css`, and `agent-configuration.css` is reduced to structure and feature-specific layout, while shared shell, tabs, cards, forms, badges, notices, and actions resolve through D1-D4.

The settings and personal-assets files currently present as untracked or modified files are preserved and migrated in place. Their API, revision, sync, dirty-draft, loading/error, and focus-return behavior is not duplicated or replaced.

Alternative rejected: merging settings, Agent Management, HR, and Personal Assets into a new JavaScript state authority. That would exceed the frontend visual scope and risk business-state regressions.

### D7. Preserve workflow geometry while standardizing coordination surfaces (`MP-07`)

Projects, orchestration, meetings, archive room, and human decisions retain their current renderer data flows:

- `ProjMgr.state` remains the owner of project, task, workflow, acceptance, pending-action, and polling state.
- `MeetingCenter.selected` and its runtime remain unchanged.
- `ArchiveRoom.state` remains unchanged.
- Human Decision sorting, draft, attention, and resolution closures remain unchanged.

Their CSS adopts D1-D4 for page/modal chrome, buttons, forms, tabs, status, confirmation, feedback, and focus.

Project orchestration specifically retains frame `147:2`/modal `148:3` geometry, pipeline canvas, task grouping, parallel relationships, directional links, and the absence of a bottom “保存编排” action. The pipeline is a domain-layout exception; its shared controls are not.

Alternative rejected: normalizing the pipeline into generic cards/grid geometry. That would violate the approved orchestration composition and obscure workflow relationships.

### D8. Consolidate catalog and registry presentation without merging their data models (`MP-08`)

Skills, Skills Organization, MCP Registry, and Branch Agent Selector keep these current authorities:

- `_sklSkills`, `_sklLibraryData`, `_sklEditingName`
- `_mcpServers`, `_mcpAgentsById`
- current organization polling, feature flag, and mutation fetch boundaries

Their modal, cards, forms, markers, badges, actions, and feedback adopt D1-D4. Duplicate legacy catalog declarations in `app/style.css:5132` are removed only after selector/computed-style tests show their dedicated CSS replacement covers all reachable states.

Alternative rejected: creating a generic catalog data module. The two domains have distinct APIs and workflows; only their presentation contracts are shared.

### D9. Give standalone application pages a shared stylesheet while preserving inline handlers (`MP-09`)

Create `app/ui-standalone.css` and load D1-D4 in `setup.html`, `models.html`, and `cron.html` in a consistent order. Static decorative inline styles move to the stylesheet. Dynamic visibility/geometry written by existing handlers may remain inline.

The following behavior is explicitly preserved:

- `setup-settings.js::currentStep` and `nextStep(n)`.
- All existing form ids and inline `onclick` entry points.
- Setup test flows that currently call `/setup/save` before provider tests. These controls must remain explicitly described as saving and testing; the migration must not silently redefine them as side-effect-free Test.
- Models and cron API calls, modal state, i18n, and list rendering.

Alternative rejected: splitting the standalone scripts into new modules during this change. It offers little UI benefit and expands the regression surface.

### D10. Align the public website through aliases, not application-shell duplication (`MP-10`)

`website/styles.css:2-24` retains marketing-friendly aliases such as `--bg`, `--surface`, and `--accent`, but those aliases point to the canonical foundation. Navigation, CTA buttons, cards, badges, forms, focus, and responsive behavior follow the shared semantic system.

Marketing headings may retain larger display sizes, and hero/demo artwork remains a public-content visual exception. Links, copy, CTA targets, i18n, and `website/script.js` behavior remain unchanged.

Alternative rejected: making the public site import all application shell CSS. The public layout has different composition needs; semantic alignment does not require coupling its entire cascade to the app.

### D11. Enforce adoption with static, interaction, responsive, and visual evidence (`MP-11`)

Add focused test files that inventory all entry points and stylesheets. Test fixtures include:

- `ENTRY_POINTS: tuple[Path, ...]`
- `SYSTEM_TOKENS: dict[str, str]`
- `DOMAIN_VISUAL_EXCEPTIONS: dict[Path, set[str]]`
- `PROHIBITED_GLOBAL_ROOTS: set[Path]`

Static validation detects undefined custom properties, competing global token roots, missing stylesheet order, unsupported component-state omissions, and new static inline decoration. Explicit runtime geometry and documented domain visuals are allowlisted narrowly.

Interaction tests cover dialog results/focus, queued feedback, settings save feedback/transport, and representative feature DOM contracts. Visual acceptance covers desktop and narrow viewports for the main shell, settings/management, projects/orchestration, meetings/archive/decisions, catalogs, standalone pages, and website.

Alternative rejected: using screenshots alone. Screenshots cannot prove handler, request, focus, or state compatibility.

### D12. Keep chat header actions structurally visible (`MP-05`, `MP-11`)

The optional compact-context control currently returns to normal flow for Codex sessions, but it has no chat-header-specific dimensions. The legacy global `button` padding makes it wider than the other header actions. Together with a non-shrinking Agent selector and status labels, the header's existing `overflow: hidden` clips the trailing close control.

The chat header therefore treats compact-context, new-session, move, and close as one fixed, non-shrinking action group. Each control keeps a canonical 32px hit area (28px at the supported narrow breakpoint) with a borderless, transparent default treatment, a subtle panel fill on hover, the shared focus/disabled states, neutral close semantics, and an accessible name. The Agent selector and live-status copy become the flexible region and truncate before the action group. Existing click handlers, chat state, API calls, local storage, and close/reset behavior do not change.

The compact Figma addendum is [PATCH · Chat Header Controls · Close Always Visible](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=400-228). It contains the high-fidelity header target, numbered interaction overview, and explicit no-persistence note in one frame, as permitted for a small UI correction.

### D13. Use one locally hosted product font across every DOM surface (`MP-01`, `MP-09`, `MP-10`, `MP-11`)

Every repository-owned DOM surface uses a locally hosted Noto Sans SC variable font under the internal family name `VO Sans`. The single file covers Simplified Chinese, Latin, numbers, symbols, and weights 100–900; `--ui-font-family`, the legacy pixel alias, and the legacy technical alias all resolve to that family so existing selectors do not create visible font mixing. Remote Google font imports are removed from the main app, standalone entries, and public website.

Legacy CSS and DOM-authored inline presentation are migrated to `var(--ui-font-family)` rather than covered by a blanket universal `!important` override. This keeps the cascade reviewable and avoids hiding future feature-local regressions. A focused static test rejects remote font imports and hard-coded DOM font families. Office canvas `ctx.font` assignments remain unchanged because their metrics are part of pixel-art drawing geometry, not DOM interface typography.

The variable WOFF2 asset and its SIL Open Font License are stored under `app/assets/fonts/noto-sans-sc/`. Loading uses `font-display: swap`; a generic sans-serif fallback is retained only for asset failure. No API, persistence, handler, or backend contract changes.

The compact editable reference is [PATCH · Unified Product Typography · VO Sans](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=403-228). It shows the Chinese/Latin/numeric sample, DOM coverage, remote-font removal, and the Canvas/no-persistence boundary.

### D14. Keep the Human Resources role emoji independent from localization (`MP-05`, `MP-06`, `MP-11`)

The merged Human Resources toolbar entry uses the repository's existing `🧑‍💼` system-role emoji. The emoji is rendered in its own `aria-hidden="true"` span, while `data-i18n="agent_management"` moves to a sibling label span. This prevents `i18n.applyTranslations()` from replacing the complete button subtree and removing the icon when the language changes.

The button id, `openAgentManagement('humanResources')` handler, title localization, toolbar component treatment, and Agent Management state boundary remain unchanged. The emoji is presentational, has no independent interaction, and introduces no API, persistence, analytics, or backend side effect.

The compact editable reference is [PATCH · Human Resources Entry Emoji](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=412-275). It combines the toolbar target, numbered language/accessibility behavior, and explicit no-persistence boundary in one frame.

## Scenario-to-modification-point mapping

| Scenario group | Confirmed files / symbols / variables | Design | Test anchor |
| --- | --- | --- | --- |
| Foundation resolution and domain exceptions | `app/style.css::root --ui-*`, `app/fonts.css --vo-pixel-ui-font`, `app/index.html` stylesheet `href` | D1, D5, D10 | `test_frontend_ui_system_contract.py`, font tests, screenshots |
| Equivalent controls, close/delete, form states | `window-controls.css --vo-close-*`, `.mm-input`, `.mm-btn`, settings nav rules | D2 | `test_frontend_ui_component_contract.py`, management/HR/settings tests |
| Dialog keyboard and action compatibility | `vo-dialogs.js activeDialog`, `show(options)`, `removeActive(result)` | D3 | `test_vo_dialogs_ui.js`, existing delete/reset tests |
| Multiple and persistent feedback | project/Agent/archive/office/skills toast functions, settings `currentState` | D4 | `test_ui_feedback.js`, `test_settings_save_feedback.js` |
| Main application surface adoption | main shell rule families and existing panel class/state writes | D5-D8 | existing feature UI tests plus viewport screenshots |
| In-progress settings and personal-assets work | settings save modules; Agent/HR/Personal Assets `state` objects | D6 | settings, Agent, HR, personal-assets focused suites |
| Orchestration composition and system override | `ProjMgr.state`, orchestration CSS roots, frames `147:2`/`148:3` | D7 | orchestration CSS/interaction tests and reference screenshot |
| Standalone/public adoption | inline roots/styles, `currentStep`, standalone status elements, website aliases | D9-D10 | standalone/website contract tests and narrow screenshots |
| Repeatable acceptance | test inventories and exception fixtures | D11 | targeted pytest/Node commands and visual evidence manifest |
| One product font across DOM UI | `app/fonts.css`, `--ui-font-family`, entry-point font imports, legacy CSS/inline font declarations | D13 | `test_unified_frontend_font.py`, `test_font_assets.js`, screenshots |

## Data and interaction invariants

### Draft lifecycle

Where a surface already has editable state, the UI follows `Clean -> Dirty -> Validating -> Saving or Testing -> Success or Error`. A failed save or test keeps the draft and focuses the relevant error. Switching categories does not discard section drafts.

Closing a dirty surface presents the existing supported choices or, where the surface already requires explicit dirty-close handling, the canonical choices: **Save and close**, **Discard changes**, and **Continue editing**. This design does not add persistence behavior to surfaces that currently have no draft.

### Persistence domains

1. Browser-local preferences: `vo-display-prefs`, `vo-i18n-lang`, `vo-product-office-config`, `vo-product-color-favorites`, and `office-activity-log` keep their existing read/write boundaries.
2. General server configuration: `/vo-config`, `/api/office-config`, and `/setup/save` remain unchanged.
3. Sensitive integrations: Feishu, Hermes, Codex, and Claude values remain masked/configured flags after save. Plaintext is never copied to local storage, feedback, logs, analytics, screenshots, or export.
4. Domain data: projects, meetings, archive, skills, MCP, and personal assets continue to use their current domain APIs, revisions, polling, and state machines.

When local and server values belong to one user action, validation occurs first, authoritative server/domain state is committed next, and browser-local preferences/baseline are updated only after success. Independent secure transactions report their own result without marking unrelated settings saved.

## Risks / Trade-offs

- **[Risk] Feature CSS loaded later overrides shared semantics.** → Add order assertions and computed-style/static selector checks; remove duplicate declarations incrementally rather than with a global rewrite.
- **[Risk] Compatibility selectors increase CSS specificity.** → Keep primitives low-specificity, scope layout overrides to feature roots, and document the limited selectors that require stronger compatibility rules.
- **[Risk] The main application is large and visually stateful.** → Migrate by surface group after D1-D4, run focused tests after each group, and keep `app/game.js` business logic unchanged.
- **[Risk] A visual cleanup accidentally changes action meaning.** → Bind every action to the numbered interaction inventory and preserve the original handler/API boundary. Close is neutral; irreversible operations remain danger with confirmation.
- **[Risk] Legacy toast callers provide only emoji text.** → Keep adapters for compatibility, migrate touched callers to explicit tone, and test that simultaneous feedback stacks.
- **[Risk] Standalone inline CSS removal disturbs inline scripts.** → Move only static presentation, keep ids/onclick/dynamic state styles, and add entry-specific contract tests.
- **[Risk] Website and product UI need different composition.** → Share semantic aliases and component states, not the full application layout cascade.
- **[Risk] Dirty working-tree work is overwritten.** → Treat current source as baseline, review diffs file by file, and stop/re-run CodeGraph if any confirmed variable or write path changes before implementation.
- **[Trade-off] Compatibility aliases temporarily preserve some legacy names.** → This reduces behavioral risk. Static tests ensure aliases resolve to one source rather than becoming a second token system.

## Migration Plan

1. Record baseline focused-test results and screenshot inventory before production edits.
2. Implement D1 and D11 token/static enforcement together.
3. Implement D2-D4 shared components, dialogs, and feedback with legacy adapters and focused tests.
4. Migrate the main shell (D5), then settings/people surfaces (D6), coordination surfaces (D7), and catalogs (D8). Verify each group before proceeding.
5. Migrate standalone pages (D9) and website (D10), preserving their entry contracts.
6. Run all focused frontend tests, existing affected feature tests, OpenSpec strict validation, and representative desktop/narrow visual acceptance.
7. Review the final diff to confirm no backend file, API contract, state object, or persistence path changed.

Rollback is frontend-only: remove the new shared CSS/JS imports, restore the previous feature CSS declarations, and retain all data and backend state. There is no schema, storage, or service rollback.

## Open Questions

No design-blocking questions remain. If implementation reveals that a confirmed variable, type, selector owner, or handler boundary has changed in the working tree, implementation must stop and return to CodeGraph/source verification and modification-point confirmation before expanding this design.
