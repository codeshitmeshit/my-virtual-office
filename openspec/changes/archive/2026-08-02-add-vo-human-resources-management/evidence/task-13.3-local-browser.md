# Task 13.3 Local Browser Acceptance

Date: 2026-07-19

## Environment

- Browser: Google Chrome 149.0.7827.54, headless mode
- CDP endpoint: `127.0.0.1:9224`
- Viewport: 1440 x 1000, device scale factor 1
- Data: deterministic fake provider fixture in `tests/fixtures/hr-browser-acceptance.json`
- Command: `HR_ACCEPTANCE_SCREENSHOT_DIR=openspec/changes/add-vo-human-resources-management/evidence/screenshots node tests/hr_ui_browser_acceptance.mjs`

## Assertions

The live CDP run completed with `ok: true` and verified:

- Happy path: first-level modal opened, two roster entries rendered, daily status and recent activity were visible, pause/resume each issued exactly once, and lifecycle state refreshed.
- Detail path: one report and one separate assessment rendered, normalized content, evidence, access history, and report/access pagination were present.
- Permissions: both management reads returned `management_token_required`; retained overview and both roster entries remained browsable, and the UI recorded only the expected denial code.
- Partial failure: roster export returned `hr_repository_unavailable`; the last valid overview and roster remained rendered with a degraded banner.
- Degraded read: access-history pagination failed after a valid Agent detail load; the existing Agent, report, assessment, and history remained browsable.
- Request accounting: 17 total requests, one pause, one resume, one report-page request, and two access-page requests.

## Screenshots

- `screenshots/hr-happy-path.png`
- `screenshots/hr-permission-denied.png`
- `screenshots/hr-partial-failure.png`
- `screenshots/hr-degraded-read.png`

All four screenshots were visually inspected after generation. They show retained data in denial/failure states and no blank modal or destructive refresh regression.

## Script defects found by live execution

Live execution caught two fixture-runner defects that static validation could not expose: a relative URL was resolved against non-hierarchical `about:blank`, and raw report assertions used `innerText` even though the report was intentionally inside a closed `details` element. The runner now uses an explicit HTTP base and DOM `textContent` for structural presence assertions. No product assertion was weakened.

The static browser check and all four focused HR Node UI suites passed after the correction.
