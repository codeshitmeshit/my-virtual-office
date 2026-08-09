## 1. Baseline and enforcement harness

- [x] 1.1 Record the current frontend entry-point, stylesheet, token, inline-style, and domain-visual-exception inventory before changing production files.
  - Scenario / design / modification point: `Static UI-system validation runs`; D11; `MP-11` with evidence from `MP-01`, `MP-05`, `MP-09`, and `MP-10`.
  - Files / symbols / variables: create `tests/test_frontend_ui_system_contract.py`; define `ENTRY_POINTS: tuple[Path, ...]`, `SYSTEM_TOKENS: dict[str, str]`, `DOMAIN_VISUAL_EXCEPTIONS: dict[Path, set[str]]`, and `PROHIBITED_GLOBAL_ROOTS: set[Path]`; read `app/index.html`, `app/setup.html`, `app/models.html`, `app/cron.html`, `website/index.html`, and their CSS imports.
  - Reuse / new-file reason: reuse the repository's `Path.read_text()` static-test pattern; a new focused test file is required because no existing test owns cross-entry UI-system enforcement.
  - Implementation: inventory all entry points; parse `var(--name[,fallback])` references and definitions; report undefined properties, competing global roots, missing shared-layer ordering, and unapproved static inline presentation; explicitly distinguish runtime geometry and documented domain visuals.
  - Chinese comments / observability: add Chinese comments only beside the allowlist rules explaining why canvas/pipeline/runtime geometry is an exception; assertion output must name the entry point, stylesheet, selector/property, and violated rule.
  - Must not modify: production CSS/JS/HTML, backend files, or existing dirty worktree content.
  - Verification: `pytest -q tests/test_frontend_ui_system_contract.py`; capture the expected baseline failures as implementation evidence rather than weakening assertions.
  - Rollback: remove only the new static-test file and its evidence record.

- [x] 1.2 Record baseline behavior for dialogs, feedback, settings, management, projects, meetings, catalogs, standalone pages, and website.
  - Scenario / design / modification point: `A migrated action is invoked`; `A keyboard user operates a migrated workflow`; D3-D11; `MP-03` through `MP-11`.
  - Files / symbols / variables: existing tests for `vo-dialogs.js`, `settings-save-feedback.js`, `settings-save-transport.js`, `AgentManagement.state`, `HumanResources.state`, `PersonalAssets.state`, `ProjMgr.state`, `MeetingCenter.selected`, `_sklSkills`, and `_mcpServers`; create `openspec/changes/unify-all-frontend-ui/evidence/baseline.md`.
  - Reuse / new-file reason: run existing characterization/UI tests; create only the OpenSpec evidence file because baseline results must not be stored in production code.
  - Implementation: run the focused commands listed by later tasks; record pass/fail and whether a failure predates this change; capture representative desktop/narrow screenshots where the local app is available.
  - Chinese comments / observability: no code comments or production logs; evidence must identify command, exit status, date, viewport, route, and surface state.
  - Must not modify: implementation, fixtures owned by other changes, backend state, or user data.
  - Verification: `openspec validate unify-all-frontend-ui --strict` and review `evidence/baseline.md` for every surface group.
  - Rollback: delete the evidence file only; baseline commands are read-only.

## 2. Canonical foundation

- [x] 2.1 Create the canonical semantic token and typography layer and wire it into the main application.
  - Scenario / design / modification point: `A frontend surface resolves foundation values`; `A domain visual needs specialized presentation`; D1; `MP-01`.
  - Files / symbols / variables: create `app/ui-system.css`; update `app/index.html` stylesheet `href` ordering, `app/style.css:138-147` (`--ui-bg`, `--ui-surface`, `--ui-border`, `--ui-text`), and `app/fonts.css:9-20` (`--vo-pixel-ui-font`, `html[lang="zh"] body *`).
  - Reuse / new-file reason: reuse Figma local variables and existing legacy names as aliases; the new focused file is required to avoid expanding `app/style.css` and to establish one ownership boundary.
  - Implementation: define canonical colors, type ramp, spacing, radii, focus ring, and reduced-motion primitives; map legacy `--ui-*` to aliases; make Noto/system Chinese UI typography the default; scope pixel and technical fonts explicitly; load the layer before feature styles.
  - Chinese comments / observability: document the canvas/pixel-art and technical-value font exceptions in Chinese next to their scopes; no runtime logging.
  - Must not modify: canvas drawing colors, avatars, office layout data, locale content, API calls, or backend configuration.
  - Verification: `pytest -q tests/test_frontend_ui_system_contract.py`; `node tests/test_font_assets.js`; `node tests/test_font_scale.js`.
  - Rollback: remove the `ui-system.css` import and file, then restore only the touched legacy token/font declarations.

- [x] 2.2 Add focused foundation tests for exact Figma values, aliases, font boundaries, and stylesheet ordering.
  - Scenario / design / modification point: `Static UI-system validation runs`; D1 and D11; `MP-01`, `MP-11`.
  - Files / symbols / variables: extend `tests/test_frontend_ui_system_contract.py`, `tests/test_font_assets.js`, and `tests/test_font_scale.js`; assert the `SYSTEM_TOKENS` mapping and entry import order.
  - Reuse / new-file reason: reuse the harness from 1.1 and existing font tests; no second token test framework.
  - Implementation: assert the exact Canvas/Surface/Toolbar/Panel/Text/Accent/Success/Info/Warning/Danger values; assert no undefined `--ui-*`; assert Chinese body UI is not globally forced to the pixel font; assert domain/technical scopes remain available.
  - Chinese comments / observability: comments explain only why a domain font exception is valid; assertion messages name the variable and expected Figma role.
  - Must not modify: production behavior or broaden exceptions to silence failures.
  - Verification: `pytest -q tests/test_frontend_ui_system_contract.py && node tests/test_font_assets.js && node tests/test_font_scale.js`.
  - Rollback: revert only assertions introduced by this task if the production task is rolled back.

## 3. Shared components, dialogs, and feedback

- [x] 3.1 Create the shared component compatibility layer and correct close-versus-danger semantics.
  - Scenario / design / modification point: `Equivalent controls appear on different surfaces`; `Close and destructive actions are presented`; `A form control changes state`; D2; `MP-02`.
  - Files / symbols / variables: create `app/ui-components.css`; update `app/index.html` import order, `app/window-controls.css:2-96` (`--vo-close-*`), `app/style.css:58-102` (`.mm-input`, `.mm-btn`), and overlapping settings navigation rules in `app/settings-modal.css:73-148`.
  - Reuse / new-file reason: reuse existing classes through compatibility selectors and current `disabled`/`aria-busy`/invalid attributes; the new file owns cross-feature component semantics.
  - Implementation: define button, nav, form, toggle, card, badge, status, and icon-control states; make close neutral; keep delete danger; keep clear/remove distinct; avoid DOM class mass-renaming.
  - Chinese comments / observability: add a Chinese comment above action-semantic compatibility mappings; no runtime logs.
  - Must not modify: `onclick`, event listeners, DOM ids, confirmation calls, or feature layout geometry.
  - Verification: `pytest -q tests/test_frontend_ui_component_contract.py tests/test_agent_management_ui.py`; `node tests/test_settings_modal_ui.js`; `node tests/test_hr_accessibility_ui.mjs`.
  - Rollback: remove the shared import/file and restore the exact touched close/component declarations.

- [x] 3.2 Implement static component-state enforcement.
  - Scenario / design / modification point: `A form control changes state`; `Static UI-system validation runs`; D2 and D11; `MP-02`, `MP-11`.
  - Files / symbols / variables: create `tests/test_frontend_ui_component_contract.py`; inspect shared selectors and compatibility maps for default/hover/active/focus-visible/disabled/loading/error/success coverage.
  - Reuse / new-file reason: reuse the 1.1 source scanner; a focused component contract test keeps state assertions separate from token inventory.
  - Implementation: enforce neutral close and danger delete; ensure focus-visible exists; ensure invalid/disabled/error meaning has a non-color signal; reject feature-local global component systems.
  - Chinese comments / observability: comments explain semantic distinctions, and failures print the missing state and owning selector.
  - Must not modify: production code or allowlists unrelated to domain visuals.
  - Verification: `pytest -q tests/test_frontend_ui_component_contract.py`.
  - Rollback: remove only this test file if task 3.1 is reverted.

- [x] 3.3 Move generic dialog presentation into a focused stylesheet without changing `VODialogs` results or keyboard behavior.
  - Scenario / design / modification point: `Close and destructive actions are presented`; `A keyboard user operates a migrated workflow`; `A migrated action is invoked`; D3; `MP-03`.
  - Files / symbols / variables: create `app/ui-dialogs.css` and `tests/test_vo_dialogs_ui.js`; update `app/index.html`, standalone imports, and `app/vo-dialogs.js::ensureStyles`, `activeDialog`, `removeActive(result)`, and `show(options)`.
  - Reuse / new-file reason: reuse the existing `VODialogs` public adapter and state machine; the new stylesheet removes the competing injected CSS string.
  - Implementation: externalize styles; preserve Promise results, Enter/Escape, initial focus, selection, cleanup, and absence of generic backdrop close; add canonical shell/actions/focus/title association.
  - Chinese comments / observability: add a Chinese invariant comment beside `activeDialog` cleanup explaining exactly-once resolve/focus behavior; no logs because dialog results are user-visible and may contain sensitive text.
  - Must not modify: caller return contracts, confirmation strength, backend calls, or feature-specific complex dialog state.
  - Verification: `node tests/test_vo_dialogs_ui.js` plus existing project delete/reset and cron/model dialog tests selected in baseline evidence.
  - Rollback: restore `ensureStyles()` CSS injection, remove the stylesheet import/file, and keep the unchanged behavior tests.

- [x] 3.4 Add the shared feedback queue and keep every legacy feedback function as an adapter.
  - Scenario / design / modification point: `Multiple transient results occur`; `An error requires continued user attention`; D4; `MP-04`.
  - Files / symbols / variables: create `app/ui-feedback.js`, `app/ui-feedback.css`, and `tests/test_ui_feedback.js`; update `app/index.html`; adapt `app/projects.js::toast`, `app/agent-creator-panel.js::_acpShowToast`, `app/game.js::_archiveToast`, `app/game.js::_showOfficeToast`, `app/skills-library-ui.js::_sklToast`, organization toast lookups, and `app/settings-save-feedback.js::currentState` presentation.
  - Reuse / new-file reason: reuse every public function name and settings inline status; new files are required for one queue/state owner and one presentation owner.
  - Implementation: implement `feedbackQueue: FeedbackItem[]`, explicit tones, stacking, duration/persistence, optional action, `role=status|alert`, and removal; update touched callers to explicit tones while preserving single-argument compatibility.
  - Chinese comments / observability: comment queue replacement/expiry invariants in Chinese; do not console-log message content or secrets; tests observe DOM, queue length, timers, and ARIA.
  - Must not modify: success/failure branches, retry calls, reload behavior, API order, or settings save transport.
  - Verification: `node tests/test_ui_feedback.js tests/test_settings_save_feedback.js tests/test_skill_library_organization_ui_states.js`; run the project feedback-focused test from baseline evidence.
  - Rollback: remove new imports/files and restore legacy function bodies; callers remain compatible because names are unchanged.

- [x] 3.5 Review the shared-layer diff and run the first CR gate before migrating feature surfaces.
  - Scenario / design / modification point: all shared-component and feedback scenarios; D1-D4; `MP-01` through `MP-04`.
  - Files / symbols / variables: review only files touched by tasks 2.1-3.4 and their tests; confirm legacy aliases, `activeDialog`, feedback adapters, and import order.
  - Reuse / new-file reason: reuse repository diff/test tools; no implementation file is created by this review task.
  - Implementation: inspect for specificity leaks, duplicated state owners, missing focus states, secret-bearing feedback, and changes to event/API boundaries; fix only findings within confirmed modification points.
  - Chinese comments / observability: verify comments explain invariants rather than restating code; record CR evidence in `openspec/changes/unify-all-frontend-ui/evidence/reviews/shared-layer.md`.
  - Must not modify: feature surface layout or any backend file.
  - Verification: `git diff --check`; commands from tasks 2.2, 3.2, 3.3, and 3.4; `openspec validate unify-all-frontend-ui --strict`.
  - Rollback: revert only shared-layer task changes as a unit; retain the review evidence for diagnosis.

## 4. Main application surface migration

- [x] 4.1 Migrate the persistent Virtual Office shell while preserving canvas and panel state behavior.
  - Scenario / design / modification point: `The main Virtual Office application is audited`; `A domain visual needs specialized presentation`; `A migrated surface is rendered at a narrow viewport`; D5; `MP-05`.
  - Files / symbols / variables: create `app/ui-main-shell.css`; update `app/index.html` and main-shell rule families in `app/style.css` for body/toolbar/sidebar/modal/chat/SMS/browser/monitor; preserve JS-written classes and variables including `--sms-toolbar-clearance`.
  - Reuse / new-file reason: reuse current DOM/class/state writes in `game.js`, `chat.js`, `sms-panel.js`, `browser-panel.js`, and `sidebar-ui.js`; the focused stylesheet prevents further growth of `style.css`.
  - Implementation: map chrome to shared tokens/components; unify scrollbars, typography, spacing, focus, responsive reachability, and overlays; leave canvas/furniture/weather/avatar rendering intact.
  - Chinese comments / observability: comment the canvas/domain-visual and runtime-geometry exceptions in Chinese; no production logs.
  - Must not modify: `app/game.js` business logic, canvas coordinates, localStorage keys, polling, chat, drag/resize, or notification behavior.
  - Verification: affected browser/SMS/chat/sidebar static and interaction tests; `node tests/test_meeting_history_card_layout.js`; desktop/narrow shell screenshots.
  - Rollback: remove `ui-main-shell.css` import/file and restore only moved shell declarations.

- [x] 4.2 Migrate settings modal chrome and controls on top of the existing settings behavior baseline.
  - Scenario / design / modification point: `The main Virtual Office application is audited`; `In-progress frontend work is migrated`; `A migrated action is invoked`; D6; `MP-06`.
  - Files / symbols / variables: update `app/settings-modal.css`, `app/settings-modal-ui.js::mountSettingsModal`, `app/settings-save-feedback.js::currentState` presentation, and `app/index.html`; preserve `VOSettingsSaveTransport.request` and `_mmSaveSettingsRequest`.
  - Reuse / new-file reason: reuse the active settings implementation and D1-D4; no new settings state module because the current change is the baseline.
  - Implementation: replace hard-coded system colors/fonts/components with canonical contracts; preserve category draft behavior, persistent footer actions, saving/success/error status, dirty-close behavior, and narrow layout.
  - Chinese comments / observability: comments only where existing behavior differs from a pure Test (save-before-test); keep feedback user-visible and secret-free, with no new logs.
  - Must not modify: `/setup/save`, timeout/endpoint logic, payload construction, masked secret rules, save order, feature toggles, or branding application.
  - Verification: `node tests/test_settings_modal_ui.js tests/test_settings_save_feedback.js tests/test_settings_save_transport.js tests/test_main_menu_settings_save.js`; relevant static checks under `tests/check_settings_*`.
  - Rollback: restore CSS presentation and shared imports only; keep settings behavior files at their pre-task state.

- [x] 4.3 Migrate Agent Management, Human Resources, and Agent Configuration surfaces without changing state ownership.
  - Scenario / design / modification point: `The main Virtual Office application is audited`; `A form control changes state`; `A keyboard user operates a migrated workflow`; D6; `MP-06`.
  - Files / symbols / variables: update `app/agent-management.css`, `app/human-resources.css`, `app/human-resources-figma.css`, `app/agent-configuration.css`, and `app/agent-configuration-figma.css`; preserve `AgentManagement.state`, `HumanResources.state`, `embeddedContext`, and existing render/open/close functions.
  - Reuse / new-file reason: reuse D1-D4 and existing renderer classes; no new JS state or competing design file.
  - Implementation: migrate modal shell, tabs, roster, summaries, detail panels, forms, command states, dialogs, badges, loading/error, and focus states; retain feature-specific approved layout only where it does not conflict with canonical semantics.
  - Chinese comments / observability: comment only feature-layout exceptions in Chinese; preserve existing errors/notices and do not add data-bearing logs.
  - Must not modify: roster projection, mutations, HR API/commands/polling, schedule behavior, focus-return variables, or Agent configuration save/test behavior.
  - Verification: `pytest -q tests/test_agent_management_ui.py tests/test_hr_ui_shell.py tests/test_agent_configuration_figma_layout.py tests/test_agent_appearance_dropdown_ui.py`; `node tests/test_hr_accessibility_ui.mjs tests/test_hr_controls_ui.mjs tests/test_hr_detail_ui.mjs tests/test_hr_overview_ui.mjs`.
  - Rollback: revert only CSS and presentation-class changes; state and API modules remain unchanged.

- [x] 4.4 Migrate Personal Assets presentation while preserving revision, secure-value, and weak-sync behavior.
  - Scenario / design / modification point: `In-progress frontend work is migrated`; `An error requires continued user attention`; D6; `MP-06`.
  - Files / symbols / variables: update `app/personal-assets.css` and presentation-only class output in `app/personal-assets.js::renderSyncPanel`, `renderOverview`, `renderEditor`, `renderSuggestions`, and `render`; preserve `state.revision`, `state.editorDraft`, `state.sync`, `state.availability`, `state.notice`, and `state.error`.
  - Reuse / new-file reason: reuse the current untracked Personal Assets implementation and D1-D4; no replacement module or backend change.
  - Implementation: align toolbar, cards, form, suggestions, sync states, notices, error/retry, and modal chrome; keep sensitive values out of feedback and visual evidence.
  - Chinese comments / observability: comment the masked/draft-only sensitive-value boundary in Chinese near any touched presentation adapter; no new logs, and existing feedback must never include asset values.
  - Must not modify: personal-assets endpoints, revisions, conflict handling, OSS availability, sync polling, worker/service/store, or response shapes.
  - Verification: `node tests/test_personal_assets_availability.mjs tests/test_personal_assets_i18n.mjs`; `pytest -q tests/test_personal_asset_http.py tests/test_personal_asset_service.py tests/test_personal_asset_sync_http.py tests/test_personal_asset_oss_availability.py`.
  - Rollback: revert frontend CSS/class changes only; do not touch Personal Assets data or backend modules.

- [x] 4.5 Migrate Projects and Project Orchestration shared semantics while preserving approved workflow geometry.
  - Scenario / design / modification point: `Orchestration modal is rendered`; `Visual acceptance is performed`; `Modal footer is rendered`; D7; `MP-07`.
  - Files / symbols / variables: update `app/projects.css`, `app/project-orchestration.css`, presentation class output in `app/projects.js` render/dialog functions, and `app/project-orchestration.js`; preserve `ProjMgr.state`, `STAGE_PIPELINE_EXECUTION_MODEL`, workflow/poll/SSE/drag/order state, and absence of “保存编排”.
  - Reuse / new-file reason: reuse D1-D4 and the existing renderers/API module; no new orchestration state owner.
  - Implementation: align headers, toolbar, actions, forms, detail panel, confirmation, status, and feedback; retain frame `147:2`/`148:3` geometry, pipeline canvas, task grouping, parallel links, direction, and dimmed project context.
  - Chinese comments / observability: comment the pipeline domain-layout exception and no-save-action invariant in Chinese; preserve existing workflow observability and do not add business logs from CSS migration.
  - Must not modify: project API, task ordering, drag/drop behavior, start/stop/acceptance, workflow chat/SSE, cron binding, persistence, or backend project services.
  - Verification: `pytest -q tests/test_project_orchestration_css.py tests/test_project_orchestration.py tests/test_project_orchestration_commands.py`; run existing project UI/static Node tests from baseline; compare screenshot with frames `147:2`, `148:3`, and canonical system components.
  - Rollback: revert presentation changes and shared mappings; preserve project/orchestration data and state.

- [x] 4.6 Migrate Meetings, Archive Room, and Human Decisions shared semantics without changing lifecycle or governance flows.
  - Scenario / design / modification point: `The main Virtual Office application is audited`; `Close and destructive actions are presented`; `An error requires continued user attention`; D7; `MP-07`.
  - Files / symbols / variables: update `app/meeting-center.css`, `app/archive-room.css`, `app/human-decision-center.css`, and presentation-only class output in their render functions; preserve `MeetingCenter.selected`, meeting runtime, `ArchiveRoom.state`, governance dialog state, decision drafts, sorting weights, and resolution payloads.
  - Reuse / new-file reason: reuse D1-D4 and current render/open/close functions; no lifecycle or governance refactor.
  - Implementation: align list/detail/control panes, status, conflict, decision forms, archive manager/governance/artifact dialogs, actions, feedback, focus, and narrow layouts.
  - Chinese comments / observability: comments document only domain-state-to-semantic-tone mapping; preserve existing user-facing notices and do not log meeting/archive/decision content.
  - Must not modify: meeting transitions/interventions/requests, archive governance and artifact API, human-decision continuation, polling, storage, or backend services.
  - Verification: `pytest -q tests/test_meeting_center_ui.py tests/test_archive_room_phase_1_3.py tests/test_archive_room_phase_8.py tests/test_human_decision_meeting_continuation.py`; `node tests/test_meeting_center_mobile_layout.js tests/test_meeting_center_runtime.js tests/test_meeting_history_card_layout.js`.
  - Rollback: revert CSS/class changes only; preserve lifecycle and governance state.

- [x] 4.7 Migrate Skills, Skills Organization, MCP Registry, and Branch Agent Selector presentation and remove proven duplicate legacy rules.
  - Scenario / design / modification point: `The main Virtual Office application is audited`; `Equivalent controls appear on different surfaces`; `Multiple transient results occur`; D8; `MP-08`.
  - Files / symbols / variables: update `app/skills-library-organization.css`, `app/mcp-registry.css`, `app/branch-agent-selector.css`, dedicated Skills styles, and legacy catalog rules around `app/style.css:5132`; preserve `_sklSkills`, `_sklLibraryData`, `_sklEditingName`, `_mcpServers`, `_mcpAgentsById`, polling, and mutation fetch functions.
  - Reuse / new-file reason: reuse D1-D4 and existing catalog renderers; remove duplicate legacy declarations only when dedicated CSS and tests prove coverage.
  - Implementation: align modal/card/form/marker/status/branch selector/action/feedback; keep organization and MCP data models separate.
  - Chinese comments / observability: comment the legacy-rule removal boundary in Chinese; existing polling/status remains observable in UI, with no new data-bearing logs.
  - Must not modify: Skills/MCP APIs, organization feature flag/runs, agent assignment, polling interval, or mutation semantics.
  - Verification: `node tests/test_skill_library_organization_ui_states.js tests/test_skill_library_organization_ui_static.mjs`; `pytest -q tests/test_mcp_registry_ui_contract.py tests/test_branch_agent_selector_ui.py`.
  - Rollback: restore removed legacy declarations and revert dedicated CSS mappings; data modules remain untouched.

- [x] 4.8 Run the main-application CR gate after every surface has been migrated.
  - Scenario / design / modification point: `The main Virtual Office application is audited`; `A migrated action is invoked`; D5-D8; `MP-05` through `MP-08`.
  - Files / symbols / variables: review all app frontend files touched by tasks 4.1-4.7 and their tests; compare state variables named in each task before/after.
  - Reuse / new-file reason: reuse diff, static tests, focused feature suites, and screenshots; create `evidence/reviews/main-app.md` only for review evidence.
  - Implementation: verify no new state authority, API call, request ordering, unapproved inline decoration, undefined token, missing focus, semantic-tone error, or dirty-worktree overwrite; fix only confirmed-scope findings.
  - Chinese comments / observability: audit comments and user-facing error text for sensitive-data leakage; record findings, resolution, and commands in evidence.
  - Must not modify: any backend file or unrelated dirty file.
  - Verification: `git diff --check`; tasks 4.1-4.7 test commands; `pytest -q tests/test_frontend_ui_system_contract.py tests/test_frontend_ui_component_contract.py`; `openspec validate unify-all-frontend-ui --strict`.
  - Rollback: roll back the affected surface task independently through its shared import/class/CSS changes.

## 5. Standalone and public frontends

- [x] 5.1 Create the shared standalone stylesheet and migrate Setup, Models, and Cron static presentation.
  - Scenario / design / modification point: `Standalone and public frontends are audited`; `A migrated action is invoked`; `A migrated surface is rendered at a narrow viewport`; D9; `MP-09`.
  - Files / symbols / variables: create `app/ui-standalone.css`; update stylesheet ordering and static inline `<style>` in `app/setup.html`, `app/models.html`, and `app/cron.html`; preserve `setup-settings.js::currentStep`, `nextStep(n)`, `statusEl`, all ids, and inline handler entry points.
  - Reuse / new-file reason: reuse D1-D4 and existing markup/handlers; new focused CSS owns the common standalone layout without rewriting business scripts.
  - Implementation: migrate page shell, toolbar, cards, forms, status boxes, modals, actions, focus, and narrow layout; keep dynamic inline `display`/geometry state where it is written by handlers.
  - Chinese comments / observability: comment why dynamic state styles remain; keep existing status elements as observability and do not log secrets.
  - Must not modify: `/setup/save`, provider tests, cron/model APIs, input ids, request order, language storage, or navigation.
  - Verification: `pytest -q tests/test_standalone_ui_contract.py`; run existing setup/models/cron HTTP-contract tests from baseline; desktop/narrow screenshots for all three pages.
  - Rollback: remove the shared standalone import/file and restore moved inline static CSS.

- [x] 5.2 Add standalone behavior and presentation contract tests, including the existing save-before-test side effect.
  - Scenario / design / modification point: `A migrated action is invoked`; `A visual migration would require backend work`; D9 and D11; `MP-09`, `MP-11`.
  - Files / symbols / variables: create `tests/test_standalone_ui_contract.py`; inspect HTML ids/imports and `setup-settings.js::testCodexConnection`, `testClaudeCodeConnection`, other test handlers, `currentStep`, and `statusEl` writes.
  - Reuse / new-file reason: reuse static source-test patterns and existing settings save tests; the new test is the owner for three standalone entries.
  - Implementation: assert shared order, no competing roots, focus/responsive contracts, preserved ids/onclick, and `/setup/save` preceding Codex/Claude tests; distinguish pure Test from save-and-test labels.
  - Chinese comments / observability: comments explain the legacy side effect as a compatibility requirement; assertion output identifies the handler and request sequence.
  - Must not modify: production behavior or assertions to reinterpret side effects.
  - Verification: `pytest -q tests/test_standalone_ui_contract.py`; run the relevant setup provider test command recorded in baseline evidence.
  - Rollback: remove this focused test only if task 5.1 is rolled back.

- [x] 5.3 Align the public website tokens and shared component semantics while retaining marketing composition.
  - Scenario / design / modification point: `Standalone and public frontends are audited`; `A frontend surface resolves foundation values`; `A migrated surface is rendered at a narrow viewport`; D10; `MP-10`.
  - Files / symbols / variables: update `website/styles.css:2-24` aliases and component rule families, `website/index.html` stylesheet order, and only presentation-state classes in `website/script.js` if required; preserve `--bg`, `--surface`, `--text`, `--accent` aliases and link/menu behavior.
  - Reuse / new-file reason: reuse canonical aliases and existing website markup/script; do not import the entire app shell or create a second marketing token root.
  - Implementation: align nav, CTA, button, card, badge, form, focus, and responsive states; retain hero/demo artwork and marketing display type as documented content exceptions.
  - Chinese comments / observability: comment the marketing display/art exception; no analytics or new logging.
  - Must not modify: copy, CTA/link targets, downloads, i18n, menu/scroll behavior, or add backend dependencies.
  - Verification: `pytest -q tests/test_website_ui_contract.py`; desktop/mobile website screenshots and keyboard menu/CTA smoke.
  - Rollback: restore website alias/component declarations and import order; script behavior remains unchanged.

- [x] 5.4 Add website semantic, responsive, focus, and link-preservation tests.
  - Scenario / design / modification point: `Static UI-system validation runs`; `Visual acceptance is performed`; D10-D11; `MP-10`, `MP-11`.
  - Files / symbols / variables: create `tests/test_website_ui_contract.py`; read `website/index.html`, `website/styles.css`, and `website/script.js` link/menu contracts.
  - Reuse / new-file reason: reuse the static scanner and entry inventory; focused website assertions keep public composition exceptions explicit.
  - Implementation: assert canonical aliases, no competing system root, required focus/narrow rules, unchanged href/CTA targets, and narrowly scoped artwork/display exceptions.
  - Chinese comments / observability: comments document only public-content exceptions; failures identify selector/link/viewport rule.
  - Must not modify: production files or broaden exceptions after failures.
  - Verification: `pytest -q tests/test_website_ui_contract.py`.
  - Rollback: remove the test if the website migration is reverted.

## 6. Final acceptance and handoff

- [x] 6.1 Run the complete static UI-system gate across every entry point and resolve all undefined tokens, competing roots, unsupported inline presentation, and missing component states.
  - Scenario / design / modification point: `Static UI-system validation runs`; D11; `MP-11` validating `MP-01` through `MP-10`.
  - Files / symbols / variables: all frontend HTML/CSS/JS entry files plus `ENTRY_POINTS`, `SYSTEM_TOKENS`, `DOMAIN_VISUAL_EXCEPTIONS`, and `PROHIBITED_GLOBAL_ROOTS`.
  - Reuse / new-file reason: reuse tests created in tasks 1.1, 2.2, 3.2, 5.2, and 5.4; do not add another validator unless a proven gap cannot fit their ownership.
  - Implementation: run gates, fix violations at the owning shared/feature layer, and document each retained exception with selector and reason.
  - Chinese comments / observability: exception comments remain next to the relevant rule; evidence records command and failure resolution.
  - Must not modify: backend files or add broad wildcard allowlists.
  - Verification: `pytest -q tests/test_frontend_ui_system_contract.py tests/test_frontend_ui_component_contract.py tests/test_standalone_ui_contract.py tests/test_website_ui_contract.py`; font and feedback/dialog Node tests.
  - Rollback: revert only the owning task that introduced a violation; never disable the gate globally.

- [x] 6.2 Produce and inspect the final desktop/narrow visual-acceptance matrix for all major surfaces.
  - Scenario / design / modification point: `Visual acceptance is performed`; `The main Virtual Office application is audited`; `Standalone and public frontends are audited`; D11; `MP-11`.
  - Files / symbols / variables: create `openspec/changes/unify-all-frontend-ui/evidence/visual-acceptance.md` and screenshot assets/links for main shell, settings, Agent/HR/Personal Assets, projects/orchestration, meetings/archive/decisions, Skills/MCP, Setup/Models/Cron, and website.
  - Reuse / new-file reason: reuse the running local server, canonical Figma node `356:240`, feature frames `147:2`/`148:3`, and delivery frames `387:744-746`; evidence files are new because acceptance must be reviewable.
  - Implementation: exercise numbered interactions and representative clean/loading/disabled/error/success/dirty states at desktop and supported narrow widths; inspect text clipping, overflow, placeholders, fonts, hotspot numbering, focus, action semantics, and domain exceptions.
  - Chinese comments / observability: no production comments/logs; evidence records route, viewport, state, comparison reference, result, and any deviation.
  - Must not modify: application data beyond reversible test fixtures or use screenshots containing plaintext secrets.
  - Verification: manual review of every matrix row plus programmatic screenshot manifest completeness; re-run focused interaction test when a screenshot defect is fixed.
  - Rollback: remove invalid evidence and recapture; production rollback follows the owning surface task.

- [x] 6.3 Run the affected frontend behavior suites and prove no backend-facing contract or state owner changed.
  - Scenario / design / modification point: `Frontend-only behavior compatibility`; all design decisions; `MP-01` through `MP-11`.
  - Files / symbols / variables: final diff; existing state variables and handler/API boundaries listed in `analysis/modification-points.md`; all focused test files.
  - Reuse / new-file reason: reuse repository tests, `git diff`, CodeGraph, and OpenSpec; create `evidence/final-verification.md` for reproducible results.
  - Implementation: run focused suites by group, re-run CodeGraph/source verification for any changed confirmed variable, inspect diff for `app/server.py`, `app/services/**`, providers, repositories, protocols, data files, API URLs, payloads, localStorage keys, and request ordering.
  - Chinese comments / observability: final evidence distinguishes baseline failures from regressions and records commands/exit status; no new production logs.
  - Must not modify: backend or unrelated dirty changes; any accidental backend diff attributable to this change must be removed before completion.
  - Verification: all task verification commands; `git diff --check`; `openspec validate unify-all-frontend-ui --strict`; final `git status --short` ownership audit.
  - Rollback: revert the smallest owning frontend task; if a confirmed modification point became invalid, stop and return to modification-point/design confirmation.

- [x] 6.4 Complete final CR, task-evidence audit, and release/rollback handoff.
  - Scenario / design / modification point: `Repeatable UI-system acceptance`; D11; `MP-11`.
  - Files / symbols / variables: all changed frontend files, tests, `proposal.md`, specs, `analysis/modification-points.md`, `design.md`, `tasks.md`, and evidence documents.
  - Reuse / new-file reason: reuse the OpenSpec dashboard and repository review tooling; no production module is created by this task.
  - Implementation: verify each changed file maps to a scenario/design/MP/task, each task has test evidence, all screenshots are reviewable, rollback is frontend-only, and no placeholder/debug/secret content remains; stop for user test-acceptance Gate before archival.
  - Chinese comments / observability: review all comments for accuracy and all feedback/log output for sensitive-data safety; record final CR summary in `evidence/reviews/final.md`.
  - Must not modify: scope, specification, or implementation outside a confirmed finding; any scope expansion returns to an earlier Gate.
  - Verification: OpenSpec dashboard shows complete task/test evidence; `openspec validate unify-all-frontend-ui --strict`; final review checklist passes.
  - Rollback: follow per-task rollback in reverse dependency order: surfaces → shared components/feedback/dialogs → foundation imports; no backend/data rollback is required.

## 7. Post-acceptance chat-header correction

- [x] 7.1 Keep the chat close action visible and unify the header action controls.
  - Scenario / design / modification point: `Chat header actions compete with status content`; D12; `MP-05`, `MP-11`.
  - Files / symbols / variables: update chat-header markup in `app/index.html` and presentation rules in `app/ui-main-shell.css`; preserve `ChatWindow` button references and click handlers in `app/chat.js`.
  - Reuse / new-file reason: reuse the canonical icon-control sizing and the focused main-shell stylesheet; add `tests/test_chat_header_controls_ui.py` because no existing test owns action-group reachability.
  - Implementation: make compact/new/move/close a fixed 32px icon-control group, let Agent/status content shrink with ellipsis, and provide accessible names without changing action order or behavior.
  - Must not modify: chat state, history, sessions, streaming, close/reset logic, APIs, persistence, or backend files.
  - Verification: `pytest -q tests/test_chat_header_controls_ui.py tests/test_frontend_ui_component_contract.py`; browser layout check with compact-context visible at desktop and narrow panel widths; `openspec validate unify-all-frontend-ui --strict`.
  - Rollback: revert the focused markup/CSS/test and retain all chat behavior code unchanged.

- [x] 7.2 Align all chat-header actions to the borderless icon-control treatment.
  - Scenario / design / modification point: `Chat header actions compete with status content`; D12; `MP-05`, `MP-11`.
  - Files / symbols / variables: update only the action-control presentation in `app/ui-main-shell.css`, its focused tests, the compact Figma addendum, and acceptance evidence.
  - Reuse / new-file reason: reuse the existing fixed action group and hover/focus tokens; no new production file or behavior owner is needed.
  - Implementation: remove the visible default border and fill from compact/new/move/close while preserving 32px/28px hit areas, subtle hover fill, keyboard focus, disabled state, and action order.
  - Must not modify: chat handlers, state, persistence, APIs, backend files, or the reachability fix from task 7.1.
  - Verification: focused static tests; computed-style and desktop/narrow geometry checks; visual screenshot inspection; Figma addendum inspection; strict OpenSpec validation.
  - Rollback: restore only the prior Secondary visual shell; keep the fixed action group and close-button reachability behavior.

## 8. Post-acceptance typography unification

- [x] 8.1 Use one locally hosted general-purpose font across every DOM frontend surface.
  - Scenario / design / modification point: `Product UI contains Chinese and Latin text`; D13; `MP-01`, `MP-09`, `MP-10`, `MP-11`.
  - Files / symbols / variables: add the licensed Noto Sans SC variable WOFF2 asset and focused source metadata; update `app/fonts.css`, `app/ui-system.css`, all five entry-point font imports, legacy CSS/DOM-authored font declarations, font tests, visual evidence, and the compact Figma typography addendum.
  - Reuse / new-file reason: reuse `--ui-font-family` as the sole runtime owner; add `tests/test_unified_frontend_font.py` because no current test rejects cross-entry hard-coded or remote DOM fonts.
  - Implementation: load local `VO Sans` weights 100–900, resolve pixel/technical compatibility aliases to the same family, remove remote font links, mechanically migrate DOM declarations to the token, and leave canvas `ctx.font` drawing metrics unchanged.
  - Must not modify: canvas rendering fonts/coordinates, handlers, APIs, persistence, backend files, copy, or interaction behavior.
  - Verification: unified-font static test; font asset/license/hash test; existing foundation/standalone/website tests; representative desktop/narrow computed-style and screenshot checks; strict OpenSpec validation.
  - Rollback: restore the prior font aliases/imports and legacy declarations, remove the new local font asset and its focused test, and leave all non-font UI changes intact.

## 9. Post-acceptance Human Resources entry correction

- [x] 9.1 Keep the Human Resources role emoji visible across language changes.
  - Scenario / design / modification point: `A localized navigation entry includes a semantic emoji`; D14; `MP-05`, `MP-06`, `MP-11`.
  - Files / symbols / variables: update only the `#btn-agent-settings` markup in `app/index.html`, its focused assertion in `tests/test_hr_ui_shell.py`, and the compact Figma addendum; preserve `openAgentManagement('humanResources')` and `data-i18n-title="agent_management"`.
  - Reuse / new-file reason: reuse the repository's existing `🧑‍💼` Human Resources system-role emoji and the existing HR shell test; no new production or test module is required.
  - Implementation: separate the decorative emoji from the localized label so `i18n.applyTranslations()` updates only the label and cannot erase the icon; hide the emoji from assistive technology.
  - Must not modify: Agent Management state, navigation behavior, locale values, APIs, persistence, backend files, or toolbar component styling.
  - Verification: `pytest -q tests/test_hr_ui_shell.py tests/test_agent_management_ui.py`; browser check in Chinese and English; strict OpenSpec validation.
  - Rollback: restore the prior single text node on `#btn-agent-settings`; no data or backend rollback is required.
