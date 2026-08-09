# Verification Evidence

Date: 2026-08-08 (Asia/Shanghai)

## Automated gates

- Focused Python/regression suite: `99 passed in 1.53s`.
  - Personal asset store, service, Agent auth/API/access, HTTP/server wiring and Skill.
  - HUMAN DECISIONS workflow/server wiring and HR Agent auth/HTTP regressions.
- `node tests/check_personal_assets_ui.mjs`: passed.
- `node tests/check_agent_guide_static.mjs`: passed.
- `openspec validate add-personal-assets --json`: valid, 1 passed, 0 failed.
- Scoped `git diff --check`: passed with no whitespace errors.
- Skill authoring baseline and forward tests:
  - Without the Skill, an independent Agent stopped rather than guessing revision or using a management token.
  - With the Skill, it used `profile-outline`, kept drafts conversation-local, required an exact confirmation, and retained HUMAN DECISIONS for later sensitive reads.
  - Forward testing found and drove fixes for full-profile leakage in onboarding write responses and idempotency-key reuse across different confirmed batches.

## Browser evidence

Validated against an isolated local VO server on port 8192 with a synthetic management token and temporary status directory, so no owner profile or real management credential was changed.

- Toolbar entry opened the Personal Assets modal and exposed `aria-current="page"`.
- Empty overview loaded without an onboarding or authorization view.
- Editor created a sensitive `chat-preferences` entry; overview showed category, value and sensitive badge.
- Suggestions view opened and contained no sensitive authorization controls.
- After restarting the isolated server with the same status directory, the entry remained present.
- At 390×844 viewport: modal visible, no document/content horizontal overflow, and no onboarding/authorization copy.
- Agent Guide discovered `vo-personal-assets` under the existing `workspace` category.
- Temporary synthetic data was moved to Trash after the test. The user's port 8090 VO service was restored and remained listening.

## Security evidence

- `profile-outline` returns revision plus value-free entry metadata; sensitive labels are redacted.
- `apply-confirmed-onboarding` returns only `idempotent`, `revision`, and `savedScope`; neither existing sensitive values nor newly written values cross the Agent response boundary.
- Batch idempotency receipts bind canonical confirmed changes and source. Reusing a key for different changes fails with conflict; a valid replay returns the original batch revision and scope.
- B one-time and C current-task disclosure, mixed-scope fail-closed behavior, Origin/loopback/active-Agent checks, and sensitive decision linkage are covered by focused tests.
- No management token, sensitive value, confirmation transcript, or full profile was written into usage/access-link audit fixtures.

## Not covered manually

- A complete browser-driven sensitive `request-context → HUMAN DECISIONS → B/C` run was not performed because the isolated browser fixture intentionally did not provision a real active provider Agent or mutate the owner's decision store. The transport-free workflow and HTTP contracts cover these paths in automated tests.
- The optional `skill-creator` `quick_validate.py` helper could not run because its host Python lacks PyYAML. Repository tests independently validate frontmatter, discovery, required safety wording and Agent Guide loading; the helper-generated `agents/openai.yaml` was created successfully.

## Scope and rollback conclusion

- Changes are limited to MP-PA-01 through MP-PA-06: focused personal-asset modules/UI/tests, thin server/index/locale discovery wiring, one VO Skill, and OpenSpec artifacts.
- No HUMAN DECISIONS implementation, HR auth, provider prompt assembly, Dashboard SSE, `office-config.json`, or global Codex Skill was changed.
- Rollback can remove the focused modules and incremental wiring while retaining `personal-assets.json` as recoverable owner data. No owner data is deleted automatically.
