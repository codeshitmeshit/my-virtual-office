# Main-application CR gate

Date: 2026-08-09 (Asia/Shanghai)

## Scope reviewed

- Persistent shell, Settings, Agent Management, Human Resources, Agent Configuration, Personal Assets, Projects, Project Orchestration, Meetings, Archive Room, Human Decisions, Skills, MCP Registry, and Branch Agent Selector.
- State owners and behavior boundaries named by tasks 4.1-4.7 were compared with the presentation changes. New focused CSS files own only visual compatibility mappings.

## Findings and resolutions

- Removed the remaining global body/button pixel-font override. General UI now inherits the Noto/system stack; only the explicitly scoped office brand keeps the pixel font. Technical values keep the shared monospace stack.
- No new state authority, request, endpoint, storage key, polling interval, event ordering, or backend mutation was introduced. CSS override modules contain no network/storage code.
- Project Orchestration variables are now scoped to the orchestration overlay and alias canonical tokens. Pipeline coordinates, card geometry, connectors, drag/drop, and auto-save remain unchanged. The hidden manual save rule remains enforced.
- Personal Assets revision/sync/availability/draft state is unchanged. Error announcements now use `role="alert"`; sensitive values are not copied to feedback or logs.
- Close controls are neutral and destructive controls remain danger. Shared focus-visible, disabled, error, and narrow-viewport states are present.
- Proven duplicate Skills/MCP rules were removed from `style.css` and moved into `ui-catalog-surfaces.css`; existing catalog state and polling remain owned by their feature modules.
- `tests/test_hr_controls_ui.mjs` was corrected to stub the current Promise-based `voConfirm` adapter rather than the retired native `confirm` test double. Production behavior was not changed.
- Desktop local visual inspection completed on `http://127.0.0.1:8090/`. The page was in the existing open Settings state and showed reachable shell/modal controls without clipping. Narrow screenshot capture timed out in the browser renderer; the same local Chromium limitation also blocks `check_project_orchestration_visual_snapshot.mjs`. Responsive contracts and Node layout tests passed, and the visual limitation remains recorded for task 6.2.
- `test_browser_viewer_url.js` retains an existing unrelated expectation mismatch (`/browser-viewer` expected, `/` produced); no browser URL code was modified.

## Verification

- Consolidated main-app Python suite — 98 passed.
- Settings modal/save/transport/main-menu Node suites — pass.
- HR accessibility/controls/detail/overview Node suites — pass.
- Personal Assets availability/i18n Node suites — pass.
- Project Orchestration runtime contract and final Chrome visual snapshot — pass.
- Meeting mobile/runtime/history layout Node suites — pass.
- Skills organization state/static Node suites — pass.
- Scoped `git diff --check` — pass.
- `openspec validate unify-all-frontend-ui --strict` — pass.

Result: main-application gate passed; standalone and public frontend migration may proceed.
