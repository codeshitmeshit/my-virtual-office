# Technical Design: Settings Large Modal

## Context

The current settings experience is a 270 px side panel defined by `#main-menu-panel` in `app/index.html` and opened by `toggleMainMenu()` in `app/game.js`. The runtime treats the panel's `open` class, the existing field IDs, and the original button handlers as its behavior contract: opening loads current settings and starts Feishu polling, closing stops polling, tests may retain their current save side effects, and `mmSaveSettings()` writes the existing local preferences before posting the server-backed configuration to `/setup/save`.

The requested change began as a presentation and information-architecture change. During functional acceptance, the user additionally approved durable save-result feedback and removal of the duplicated legacy save entry. The final scope therefore preserves every current control, action boundary, close behavior, payload and persistence format while consolidating `/setup/save` into the focused config runtime service.

Two implementation constraints shape the design:

- `app/oss-settings.js` dynamically inserts `#oss-settings-section` before `.mm-save-all` and observes the panel's `open` class. The modal layout must mount after that insertion and retain both `.main-menu-body` and the `open` class.
- `app/index.html` and both locale files already contain unrelated user changes for Personal Assets and OSS. Wiring must be a minimal local patch. New presentation logic and CSS belong in focused new files under MP-SET-01 and MP-SET-02.

The approved Figma large-modal frame (`334:240`) is the visual reference. Its interaction (`338:240`) and storage (`338:249`) boards are design evidence only and must be corrected wherever they describe behavior that differs from the current product.

## Goals / Non-Goals

### Goals

- Present settings as a centered, large desktop modal with stable header, category navigation, scrollable content, and footer action areas.
- Group all current settings into seven task-oriented categories without duplicating or replacing the current controls.
- Preserve the identity, value, ID, handler, conditional visibility, status target, and business side effects of every existing setting node.
- Preserve hybrid persistence: ordinary settings continue through the global save action, while integrations with independent save/test flows retain those boundaries; all server-side setup persistence uses one config runtime service entry.
- Keep the implementation isolated, reversible, localized, and compatible with the dynamically inserted OSS section.
- Make runtime behavior, Figma interaction documentation, and storage documentation agree.

### Non-Goals

- No changes to `toggleMainMenu`, `_mmLoadCurrentSettings`, `mmSaveSettings`, `mmTest*`, Feishu/Chat actions, OSS actions, import/export/reset actions, or their endpoints.
- No dirty-state tracking, unsaved-change confirmation, backdrop-close behavior, Escape shortcut, autosave, history, versioning, or rollback UI.
- No change to existing test-button save side effects or to the order of the global save operation.
- No backend API, persisted schema, localStorage key, secret-handling, or notification-delivery change.
- No general modal framework and no visual changes to unrelated dialogs, the office canvas, toolbar, meetings, Personal Assets, or agent management.

## Decisions

### 1. Mount a DOM-preserving presentation adapter (MP-SET-01)

Create `app/settings-modal-ui.js` with the following focused surface:

- `CATEGORY_DEFINITIONS`
- `settingsModalState`
- `classifySection(section)`
- `activateCategory(categoryId)`
- `mountSettingsModal()`

`mountSettingsModal()` will run after `oss-settings.js`, locate the existing `#main-menu-panel`, `.main-menu-body`, `.mm-section` nodes, and `.mm-save-all`, then create only presentation containers: dialog, navigation, content, category panels, and footer. It will move the original nodes into those containers. It will not clone form controls, replace them with generated markup, or rewrite IDs and inline handlers.

The original `#main-menu-panel` remains the visibility root, and `open` remains the only visibility state consumed by the existing runtime. `.main-menu-body` remains present below that root so the OSS module's established selector continues to resolve. `settings-modal-mounted` is added only after a complete successful mount. Repeated calls are idempotent.

The category ownership contract is:

| Category | Stable section anchors |
| --- | --- |
| Connections & Agents | `#mm-oc-path`, `#mm-hermes-enable`, `#mm-codex-enable` |
| Office | `#mm-office-name` |
| Display | `#mm-show-bubbles`, `#mm-show-weather` |
| Tools & Browser | `#mm-apiusage-enable`, `#mm-pcmetrics-enable`, `#mm-browser-enable` |
| Notifications | `#mm-feishu-enable`, including the current Feishu Chat controls in that section |
| Storage | `#oss-settings-section` |
| Advanced | `#mm-import-file` and the section containing the `/setup` help link |

Each current section must match exactly one category in the contract test. A future unrecognized section will be placed in Advanced and marked for diagnostics rather than hidden, so a newly added setting remains accessible until the ownership table and test are updated.

`activateCategory(categoryId)` changes only presentation state and ARIA selection/visibility. `settingsModalState` stores `{mounted, activeCategory}` for the current page session only; it is never serialized. Moving original nodes preserves partially edited values when switching categories.

Rationale: the current business logic is coupled to stable IDs but not to the sections' direct parent or order. Reparenting gives one source of truth for controls and behavior while avoiding changes to the 19k-line runtime file.

Alternatives rejected:

- A second generated form would create duplicate IDs and two state authorities.
- Rewriting `toggleMainMenu()` would risk settings-load and Feishu-polling lifecycle regressions.
- Adding layout orchestration to `app/game.js` would expand a legacy entry point and violate the focused-file constraint.

### 2. Apply modal styling only after successful mount (MP-SET-02)

Create `app/settings-modal.css`. Every geometry or component override will be scoped beneath `.main-menu-panel.settings-modal-mounted`. Without that class, the current `app/style.css` side panel remains the functional fallback.

The mounted root becomes a viewport overlay; `.settings-modal-dialog` is centered and sized from local variables such as `--settings-modal-width`, `--settings-modal-height`, and `--settings-modal-nav-width`. The desktop reference is approximately 960 x 680 px, bounded with `min()`/viewport-safe dimensions rather than fixed overflow. The dialog has:

- a stable header using the current title and close action;
- a left category navigation;
- an independently scrollable content region;
- category panels that use a dense card grid where space permits;
- a stable footer containing the original global save button.

At narrow desktop widths, navigation and content collapse to a compact single-column arrangement while the dialog remains viewport-bounded and every action remains reachable through scrolling. Existing `.mm-input`, `.mm-btn`, `.mm-status`, and `.mm-section` styles receive only scoped refinements. No global `.modal` selector is introduced.

Rationale: class-gated styling provides atomic enhancement and immediate rollback while protecting unrelated UI.

Alternative rejected: modifying `app/style.css` directly would enlarge a shared stylesheet and make the fallback and unrelated-style boundary harder to verify.

### 3. Wire resources minimally and localize category labels (MP-SET-03)

Patch `app/index.html` only to:

- load `settings-modal.css` after `style.css`;
- load `settings-modal-ui.js` after `oss-settings.js`.

Add these keys locally to both `app/locales/en.json` and `app/locales/zh.json`:

- `settings_modal_connections_agents`
- `settings_modal_office`
- `settings_modal_display`
- `settings_modal_tools_browser`
- `settings_modal_notifications`
- `settings_modal_storage`
- `settings_modal_advanced`
- `settings_modal_subtitle`

Navigation text is resolved through the existing `window.i18n.t` interface. On `i18n:changed`, the module updates its labels without reconstructing or moving form nodes again.

Rationale: loading after OSS makes the dynamic storage section available during classification; localized labels match the existing language lifecycle.

Alternative rejected: hard-coded category labels would diverge after language changes.

### 4. Preserve current behavior as an explicit compatibility contract

The modal adapter must not reference `/setup/save`, business endpoints, localStorage, runtime settings functions, or provider-specific state. The existing save owner in `app/game.js` remains authoritative for payload construction, persistence ordering and runtime updates. It delegates transport selection to a focused request module and emits lifecycle notifications to a focused presentation module.

The following behavior remains authoritative:

- The current toolbar button and close button call `toggleMainMenu()`.
- There is no new backdrop click, Escape close, or dirty-close confirmation.
- Opening still loads settings and starts current polling; closing still stops it.
- Test actions keep their current status targets and any current save/test side effects.
- Global save retains its present local-first then `/setup/save` sequence and runtime-update behavior. A persistent footer status mirrors the real pending/success/failure result without introducing a second save path.
- Feishu, Feishu Chat, OSS, and other independent integration actions retain their current save/test boundaries.
- Immediate local preferences retain their existing timing.

This is more restrictive than a behaviorally improved redesign, but it makes the UI conversion independently reviewable and avoids silently changing persistence semantics.

### 4.1 Make the authoritative save result perceptible and testable

Add `app/settings-save-feedback.js` as a presentation-only state machine with `start()`, `success()`, and `failure(message)` entry points. It mounts one `role="status"` / `aria-live="polite"` element in the existing modal footer, disables the existing `.mm-save-all` button only while a request is pending, and keeps the latest success or failure result visible until the next attempt. It does not call `/setup/save`, write localStorage, close the modal, or construct settings payloads.

The active `mmSaveSettings()` implementation in `app/game.js` must return its existing request promise and notify this module at the actual lifecycle boundaries:

1. after synchronous local preference writes and immediately before `/setup/save`, call `start()`;
2. on `{ ok: true }`, perform the existing runtime updates and then call `success()`;
3. on `{ ok: false }`, call `failure()` with the server error when available;
4. on rejection or JSON failure, call `failure()` with the caught error;
5. while pending, a repeated invocation returns the in-flight promise and must not send a second request.

This keeps one save authority while giving the user durable evidence of the real outcome. Unit tests must execute the actual `mmSaveSettings` function with controlled DOM, localStorage, and network collaborators to verify payload content, localStorage-before-request ordering, deduplication, success runtime updates, business failure, and network failure. Separate presentation tests verify button/status rendering and language refresh.

### 4.2 Consolidate server persistence into one entry

`app/server_services/config_runtime.py::_persist_setup_payload` is the sole setup persistence implementation. The live `OfficeHandler` delegates `/setup/save` body handling to `app/server_routes/config.py`; internal Feishu settings callers also call the config runtime service. The duplicated `_persist_setup_payload`, `_merge_setup_config`, and `_clear_setup_secret_paths` bodies are removed from `app/server.py`.

The focused service retains the previous compatibility behavior: explicit `VO_CONFIG` selection, status-directory preference for notification configuration, blank-secret preservation and explicit secret clearing, Codex demo-reply stripping, Feishu group-chat transport validation, runtime global refresh, roster refresh, gateway restart when credentials change, and Feishu Chat lifecycle refresh. Disk-write exceptions propagate to the HTTP boundary and must never be returned as `{ ok: true }`.

### 4.3 Prevent long-lived streams from starving the save request

The live browser opens several long-lived HTTP/1.x event streams. Functional acceptance showed that a same-origin `/setup/save` could remain queued indefinitely behind those connections. `app/settings-save-transport.js` therefore owns only request transport: on a local HTTP page opened through `localhost` or `127.0.0.1`, it posts to the same local server through the dedicated `0.0.0.0` loopback origin; non-local and HTTPS deployments keep the relative `/setup/save` URL. The existing management-token fetcher remains authoritative for authentication.

The transport supplies an abort signal and a 15-second timeout so the footer always settles to success or failure. The management-token challenge is CORS-readable and contains no secret, allowing the existing token dialog and retry flow to operate across the dedicated local origin. It does not persist data, construct a second payload, or change the server API.

### 5. Correct Figma documentation to describe compatibility, not new semantics

The Figma large-modal frame remains the visual source for spacing, hierarchy, density, and component composition. Before visual acceptance, update its interaction and storage boards to:

- remove the proposed dirty-close choice;
- show the actual global save order: existing local preferences first, then `/setup/save`;
- show current test/save side effects instead of describing tests as universally non-persistent;
- retain the independent Feishu, Chat, and OSS action boundaries;
- label behavior as current compatibility rather than a future persistence target.

Figma nodes map to MP-SET-01 for interaction compatibility and MP-SET-02 for visual acceptance; they do not create an additional product specification.

### 6. Verify structure, behavior isolation, and rendered layout

Add `tests/test_settings_modal_ui.js` with a minimal DOM harness to verify:

- all seven categories exist;
- every current section has exactly one owner;
- original form and save-button node identity is retained;
- field values survive category changes;
- category navigation invokes no business handler;
- mount is idempotent;
- unknown future sections remain visible under Advanced.

Add `tests/check_settings_modal_wiring.mjs` to verify:

- stylesheet and script order;
- all English and Chinese locale keys;
- the existing settings ID inventory is not reduced;
- the presentation module contains no `/setup/save`, localStorage access, or business endpoint implementation;
- the OSS section is still mounted under the preserved panel/body contract.

Run the focused tests plus existing OSS, module-split, and provider-runtime checks. The provider-runtime check must validate the active `app/game.js` entry loaded by `app/index.html`, rather than the currently unloaded `app/main-menu-settings.js` split artifact.

Perform browser visual verification at 1512 x 742 and at a narrow desktop viewport. Check dialog boundaries, content/footer reachability, navigation selection, scrolling, conditional controls, status text, and absence of clipping. Compare the result to the corrected Figma reference.

### 7. Scenario traceability

| Spec scenario group | Modification point | Implementation | Verification |
| --- | --- | --- | --- |
| Open/close large modal without new close semantics | MP-SET-01, MP-SET-02 | `settings-modal-ui.js`, `settings-modal.css` | DOM contract and browser checks |
| Task navigation and value-preserving category switches | MP-SET-01, MP-SET-03 | category definitions, activation, locale keys | `test_settings_modal_ui.js` |
| Complete control and conditional-field parity | MP-SET-01 | original-node reparenting | section ownership and ID inventory checks |
| Existing action and test behavior compatibility | MP-SET-01 | no business-handler replacement | isolation/static checks and existing focused tests |
| Hybrid save and immediate preference behavior | MP-SET-01 | existing payload/local-first behavior plus one config runtime persistence entry | payload, disk and single-entry contract tests |
| Perceptible and functionally verified save result | MP-SET-01, MP-SET-02 | `settings-save-feedback.js`, `settings-save-transport.js`, minimal `mmSaveSettings` lifecycle notifications | save outcome unit tests and isolated browser status check |
| Clear action/status presentation | MP-SET-02 | scoped card, button, and status styles | desktop screenshots |
| Dense desktop and narrow-desktop accessibility | MP-SET-02 | responsive dialog/layout rules | two-viewport browser verification |
| Figma traceability and visual acceptance | MP-SET-01, MP-SET-02 | corrected Figma boards and CSS reference | Figma-to-runtime review |

## Risks / Trade-offs

- **Ancestor-selector risk:** reparenting can change CSS selectors that depend on ancestry. Mitigation: preserve `#main-menu-panel` and `.main-menu-body`, scope new rules to the mounted root, and test node ownership and rendered behavior.
- **Dynamic OSS timing:** mounting before OSS insertion would omit Storage. Mitigation: require script order after `oss-settings.js` and assert it statically.
- **Dirty-worktree overlap:** index and locale files already contain user changes. Mitigation: use minimal contextual patches, avoid whole-file formatting, and review the final diff specifically for Personal Assets and OSS preservation.
- **Future section drift:** selector-based ownership needs maintenance when settings are added. Mitigation: fail the current inventory contract for ambiguous ownership and keep truly unknown future sections visible under Advanced.
- **Compatibility over ideal semantics:** retaining test side effects and local-first global save may be less desirable than a redesigned transaction model. This change deliberately does not combine persistence migration with UI migration.
- **Duplicate-submit risk:** users may click Save repeatedly while a request is pending. Mitigation: `mmSaveSettings` retains and returns one in-flight promise, while the feedback module disables the existing button until settlement.
- **HTTP/1.x connection starvation:** long-lived event streams can consume the primary local origin's connection pool. Mitigation: local saves use a dedicated loopback origin and a bounded timeout; non-local deployments retain the relative endpoint.
- **Split-brain persistence risk:** retaining the legacy `server.py` implementation would allow tests and runtime to use different entry points. Mitigation: remove the legacy definitions and enforce the service-only boundary with a static contract.
- **Accessibility boundary:** the modal will add dialog/nav ARIA and keyboard-reachable category controls, but it will not introduce an Escape shortcut because that would change close behavior. Focus trapping is limited to what can be added without interfering with existing controls and handlers.
- **Known baseline failure:** the provider-runtime static check already fails outside this change's files. It must remain separately identified so it neither blocks visual work incorrectly nor becomes hidden by the new tests.

## Migration Plan

1. Correct the Figma interaction and storage boards while retaining the approved large-modal visual frame.
2. Add the focused DOM and wiring contract tests against the approved category and behavior boundaries.
3. Implement `settings-modal-ui.js` and `settings-modal.css` as isolated progressive enhancement.
4. Apply minimal resource wiring and locale additions.
5. Run focused and existing regression checks, then perform both viewport visual checks against Figma.
6. Review the final diff for unrelated dirty-worktree preservation and scenario traceability.

UI rollback remains data-migration-free: remove the modal, feedback and transport resource references and revert the small `mmSaveSettings` lifecycle hook. The service consolidation can be reverted independently because it preserves the same `/setup/save` payload and on-disk format.

## Open Questions

No blocking technical questions remain. Final pixel values inside the approved responsive bounds will be settled during Figma alignment and visual verification; they do not alter the accepted module, behavior, storage, or API boundaries.
