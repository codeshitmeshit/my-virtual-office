# Implementation verification

## Automated checks

- `node tests/test_settings_modal_ui.js` — PASS
- `node tests/test_settings_save_feedback.js` — PASS
- `node tests/test_settings_save_transport.js` — PASS
- `node tests/test_main_menu_settings_save.js` — PASS
- `node tests/check_settings_modal_wiring.mjs` — PASS
- `node tests/check_feishu_processing_status_ui.mjs` — PASS
- `node tests/check_feishu_group_chat_config_static.mjs` — PASS
- `node tests/check_settings_save_single_entry.mjs` — PASS
- `node tests/test_oss_settings_ui.js` — PASS
- `node tests/check_server_frontend_module_split.mjs` — PASS
- `.venv/bin/python tests/test_provider_runtime_config.py` — PASS
- `.venv/bin/python -m pytest -q tests/test_settings_save_http_contract.py tests/test_server_routes_module_split.py tests/test_feishu_notifications.py` — PASS (`111 passed`)
- `python3 -m json.tool app/locales/en.json` — PASS
- `python3 -m json.tool app/locales/zh.json` — PASS
- `git diff --check -- <scoped files>` — PASS
- `openspec validate redesign-settings-large-modal --json` — PASS (`valid: true`)

The final verification run above completed after save-feedback and single-entry implementation.

## Resolved historical baseline

The historical provider-runtime failure was traced to a stale test target: the check inspected unloaded `app/main-menu-settings.js`, while `app/index.html` loads `app/game.js` and the active implementation already reads and saves `routeApprovalsThroughVo`. The gate now checks the active runtime entry and passes.

Repository-wide verification also removed the long-standing pytest collection blocker by defining the supported pytest boundary, corrected two archived OpenSpec evidence paths, refreshed the deterministic Provider inventory, and replaced a load-sensitive multiplex polling loop with condition-based waiting. A fresh full run completed with `2926 passed`.

## Browser evidence

The local VO was discovered at `http://127.0.0.1:8090` through the instance-provided skill index. A first in-app browser pass verified:

- closed state keeps the mounted overlay hidden (`visibility: hidden`, `opacity: 0`);
- opening through the existing menu button preserves the `open` class contract;
- the desktop dialog rendered at 960 × 672 px inside the observed 1280 × 720 viewport;
- all 13 current `.mm-section` nodes were assigned exactly once as `3 / 1 / 2 / 3 / 1 / 1 / 2` across the seven approved categories;
- content scroll was independent (`clientHeight: 536`, `scrollHeight: 1717`), with the footer remaining fixed;
- no console errors were present during that pass;
- the screenshot visually matched the approved dark overlay, gold boundary, left navigation, two-column cards and fixed footer.

The pass exposed that navigation labels mounted before `i18n:ready`; a regression test was added first, then the module was corrected to refresh on both `i18n:ready` and `i18n:changed`.

Subsequent attempts to capture the exact 1512 × 742 and narrow viewport evidence repeatedly timed out in the in-app browser connection during local navigation. Tasks 6.1 and 6.2 remain unchecked rather than claiming evidence that was not captured.

### Overall three-column iteration

Desktop feedback clarified that “three columns” means one navigation column plus two internal content columns, not navigation plus three content columns. The dialog maximum width remains 1240px, while the category content now uses a two-column continuous flow. Each settings card uses `break-inside: avoid`, so unequal card heights no longer create a shared Grid row gap.

A fresh local-browser pass verified:

- at 1280 × 720, the overall layout was a 204px navigation column plus a 1026px content region;
- the content region reported exactly two columns, with the three Tools & Browser cards laid out as two cards continuously stacked in the first 489px column and one card in the second 489px column;
- at 800 × 720, the content fell back to one column and the navigation became horizontal;
- neither viewport produced document-level horizontal overflow;
- the 1280px desktop pass had no console errors.

The CSS wiring contract now requires the overall navigation/content split, exactly two internal columns, `break-inside: avoid`, and the absence of a three-column content grid. This prevents regression to an unintended four-column overall layout.

### Settings card title hierarchy

Desktop feedback identified that `.mm-section-title` still inherited the legacy 7px sidebar size while explanatory `.mm-help` copy could be enlarged by the global font scaler. The mounted-modal scope now gives card titles the system component-title level (12px/16px) and restores help copy to the system metadata level (9px/14px). Both declarations multiply by `--vo-font-scale`, and their font sizes override the scaler's stale inline values so the existing 100–150% UI scaling behavior remains intact. Static contracts cover both levels, and the stylesheet asset version in `app/index.html` was advanced so existing browser caches cannot retain the previous rules.

### Office browser branding

The Office category now exposes the existing office name together with a new office icon picker. The name maps to the browser title and the icon maps to favicon links. Image files are processed in-browser to PNG, bounded to a 2 MB source and a 32 KB persisted Data URL, previewed as an unsaved draft, and included as `office.iconDataUrl` in the existing `POST /setup/save` transaction. The live title and favicon update only after a successful response; business and network failures retain both the draft and the previously applied browser branding.

The backend validates the office name, media type, Base64 encoding, and decoded size in `services/office_branding.py`; invalid branding receives `400 invalid_office_branding` and is not written. `/vo-config` returns the validated icon alongside `office.name`, while invalid legacy icon data is ignored during startup.

Figma was updated without overwriting the earlier approved screen:

- Office branding screen: `382:466`
- Interaction inventory: `338:240` (items 40–43)
- Storage and submission: `338:249` (rule 07)

Runtime browser verification confirmed the Office tab shows both controls, selecting the shipped PNG produces a Data URL preview and ready state, unsaved name/icon changes do not alter the current document title or favicon, clearing the draft restores the default preview, and the page emitted no console errors.

### Notification cards two-column split

The Notifications category now owns two sibling cards: `feishu-notifications` and `feishu-chat-app`. The existing two-column content flow places them side by side on desktop while retaining the single-column responsive fallback. Every stable input ID and the existing save, test and status handlers remain unchanged, so the split is presentation-only and does not merge the two secure persistence domains.

The focused UI test verifies that both sibling cards are classified into Notifications, the wiring contract verifies their stable markers and removes the obsolete in-card divider, and the Feishu save/processing/group-chat checks all pass. The processing-status baseline fixture was also updated to inject the shared cached configuration reader that the isolated test block depends on.

Figma was updated without overwriting the earlier approved settings screen:

- Notification two-column screen: `394:466`
- Interaction inventory: `338:240` (items 29–33 identify the left/right card)
- Storage and submission: `338:249` (rule 05 preserves independent handlers and storage boundaries)

## Behavior and scope review

- Existing header, sections, inputs and `.mm-save-all` are moved, never cloned.
- Navigation only changes presentation state and cannot call business handlers.
- Arrow keys plus Home/End use roving focus and update ARIA selection.
- The module contains no endpoint, `localStorage`, save/test implementation, or new close semantics.
- Existing global save remains localStorage-first then `/setup/save`; existing test-button save side effects and Feishu/Chat/OSS independent actions remain owned by their current modules.
- No production credentials or external notifications were used during verification.
- The later user-approved functional increment edits the active `app/game.js` save lifecycle and consolidates the duplicated backend implementation without changing the request payload or persistence format. `app/main-menu-settings.js` remains untouched; provider-runtime assertions now target the loaded `app/game.js` implementation. Existing unrelated dirty-worktree changes were preserved.

## Save feedback and functional persistence evidence

Focused tests cover the real save owner rather than a copied implementation:

- `tests/test_main_menu_settings_save.js` executes the active `mmSaveSettings()` and verifies localStorage-before-request ordering, payload fields, one in-flight request, successful runtime updates, service `{ ok:false }`, and rejected request handling.
- `tests/test_settings_save_feedback.js` verifies the single ARIA live region, pending button lock, persistent success/failure, safe error text, locale refresh, and idempotent mount.
- `tests/test_settings_save_transport.js` verifies local dedicated-origin selection, unchanged non-local relative endpoint, POST payload, abort signal, and bounded timeout.
- `tests/test_provider_runtime_config.py` calls `server_services.config_runtime` directly and verifies explicit `VO_CONFIG` disk persistence plus runtime refresh; a forced read-only write propagates `OSError` rather than returning success.
- `tests/test_server_routes_module_split.py` verifies `/setup/save` calls the config runtime service and preserves business failure status/reason.
- `tests/check_settings_save_single_entry.mjs` prevents the deleted `server.py` persistence/merge/secret implementations or direct legacy calls from returning.
- `tests/test_settings_save_http_contract.py` verifies that the management-token challenge is readable from the dedicated local origin so the existing dialog can retry the request.

The first real 8090 browser attempt exposed the original same-origin request remaining queued while several HTTP/1.x SSE streams occupied the browser connection pool. The footer correctly showed pending and locked the button, but no POST reached the server. A focused `settings-save-transport.js` was added so local saves use a dedicated local origin and always time out after 15 seconds.

A clean browser acceptance then ran on isolated ports 18090/18091 with a temporary status directory and a synthetic management token:

- click immediately showed `正在保存设置…` and disabled Save;
- the cross-local-origin 403 challenge opened the existing management-token dialog;
- entering the synthetic token retried through the same authoritative save action;
- the footer settled to `设置已保存`, Save became enabled, and the browser recorded no console errors;
- `/tmp/vo-settings-e2e-runtime/vo-config.json` existed with `_setupComplete: true`, the submitted office name, all four feature keys and the submitted OpenClaw home path;
- the isolated server was stopped, and its temporary directory was moved to the Trash; no production credentials, notifications or user configuration were used.

## Single server entry review

`app/server.py` no longer defines `_persist_setup_payload`, `_merge_setup_config`, or `_clear_setup_secret_paths`. The live POST handler delegates `/setup/save` to `server_routes.config.handle_post`, and internal settings callers invoke `server_services.config_runtime._persist_setup_payload`. The service carries the compatibility behavior that previously lived in the legacy entry, including explicit config-path selection, secret preservation/clearing, Feishu transport validation and runtime refresh.

## Rollback

Remove the modal, feedback and transport asset tags from `app/index.html` and revert the small `mmSaveSettings` lifecycle hook to return to the legacy visual/save presentation. The service consolidation is independently reversible and did not migrate or change stored data.
