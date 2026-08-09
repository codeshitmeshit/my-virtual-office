# Final visual-acceptance matrix

Date: 2026-08-09 (Asia/Shanghai)

## References and inspection method

- Canonical system UI: [Figma node 356:240](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=356-240)
- Delivery frames: high fidelity `387:744`, interaction overview `387:745`, storage/submission `387:746`.
- Baseline captures: `screenshots/baseline-main-desktop.png` and `screenshots/baseline-main-narrow.png`.
- Final Project Orchestration capture: `screenshots/final-project-orchestration.png` (1512 x 742), generated against the canonical foundation and final project surface layer.
- Final chat-header capture: `screenshots/final-chat-header-controls.png` (760 x 180), generated with compact-context visible and all four trailing actions in the canonical fixed icon-control group.
- Final desktop inspection: local application at `http://127.0.0.1:8090/`, existing Settings-open state. Shell, modal header, category navigation, content scrolling, footer actions, typography, close semantics, and viewport reachability were inspected without submitting data.
- Final narrow proof: static responsive contracts and DOM/layout interaction tests. A fresh 390 x 844 browser capture was attempted twice, but the local browser renderer timed out and reset its runtime. This is an evidence-environment limitation, not reported as a successful screenshot.

The general interface now uses the Noto Sans/system sans stack. Monospace remains limited to technical values, and pixel typography remains limited to the office/canvas and brand exception.

## Acceptance matrix

| Surface | Desktop / narrow evidence | States and interactions covered | Visual review result | Deviation |
| --- | --- | --- | --- | --- |
| Main shell | Desktop live inspection; `final-chat-header-controls.png`; `test_font_scale.js`; shell/static contracts | toolbar, sidebar, chat compact/new/move/close group, focus, narrow reachability, canvas exception | Pass: canonical tokens and sans UI typography; all four chat actions remain visible at 32px desktop and 28px narrow; canvas geometry and pixel visuals preserved | Fresh full-app narrow capture unavailable due renderer timeout; focused chat-header narrow CDP geometry passes |
| Settings | Desktop live inspection with modal open; settings UI/save/transport tests | open/close, category navigation, clean/dirty, saving, success/error, persistent footer, save-before-test | Pass: large modal composition, stable actions, neutral close, focus and feedback semantics align | No data was submitted during visual review |
| Agent / HR / Personal Assets | Python contracts plus HR and Personal Assets DOM tests | roster/detail/forms, confirmation, degraded read, pagination, loading/error, sync/availability, draft protection | Pass: shared modal/forms/cards/status/focus semantics; sensitive draft content excluded from evidence | Programmatic responsive proof only for final state |
| Projects / Orchestration | final 1512 x 742 Chrome screenshot plus orchestration CSS/runtime/page/task-dialog tests | pipeline cards, drag/add dialog, disabled/state controls, hidden manual save, feedback | Pass: canonical sans typography and colors; approved outer modal and pipeline geometry retained | None |
| Meetings / Archive / Decisions | meeting mobile/runtime/history plus archive/decision Python contracts | mobile layout, live/history cards, decision detail, empty/loading/error/status semantics | Pass: canonical typography, cards, badges and actions; lifecycle state owners unchanged | Programmatic responsive proof only for final state |
| Skills / MCP | organization state/static tests and MCP/branch selector contracts | catalog cards, organization states, polling/error/empty states, selector focus | Pass: duplicate legacy CSS removed; shared catalog presentation is authoritative | Programmatic responsive proof only for final state |
| Setup / Models / Cron | `test_standalone_ui_contract.py` at desktop and narrow breakpoints | fields, buttons, save/test labels, focus, overflow, save-before-test behavior | Pass: shared standalone shell and per-page presentation use canonical tokens | `/cron` is not exposed by the current local server baseline (HTTP 404); static page contract passes |
| Public website | `test_website_ui_contract.py` responsive/focus/link contracts | navigation, CTA, links, mobile menu presentation state, focus | Pass: marketing composition retained while tokens, controls and focus align | Programmatic responsive proof only for final state |

## Quality checks

- No placeholder content, plaintext secret, debug overlay, or new global font system was found in the changed presentation files.
- Close actions are neutral; delete/destructive actions remain danger; clear/remove semantics are not conflated.
- Focus-visible, disabled, loading, error, success, and reduced-motion contracts are present in the shared layer.
- Runtime geometry remains an explicit exception only for the office canvas and project pipeline.
- Chat Agent/status content truncates before the fixed action group; compact, new-session, move, and close use one monochrome borderless icon-control treatment and retain their existing handlers.
- Product DOM typography uses the locally hosted `VO Sans` family for Chinese, Latin, numbers, and technical values at desktop and narrow widths; the WOFF2 request succeeds, no horizontal overflow appears, and Canvas drawing fonts remain unchanged.
- Numbered interaction and persistence coverage is retained in Figma frames `387:745` and `387:746`; implementation tests cover the corresponding keyboard, feedback, save, test, retry, and state-preservation boundaries.

## Manifest completeness check

The matrix has exactly the eight required surface groups: main shell; settings; Agent/HR/Personal Assets; projects/orchestration; meetings/archive/decisions; Skills/MCP; Setup/Models/Cron; website. Each row records a desktop/narrow evidence source, states, result, and deviation. All referenced local baseline and final Project Orchestration screenshot files exist. The final narrow-capture limitation is explicit and is not represented as a passing screenshot.

Result: visual acceptance passes with the recorded full-app narrow-renderer limitation. The focused chat-header correction has desktop screenshot evidence and a passing 390px computed-layout check.
