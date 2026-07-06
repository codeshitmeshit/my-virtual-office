# Hermes Dangerous Command Approval With Feishu Actions

## Background

Virtual Office currently has partial Hermes approval support. Hermes native API approval requests can surface in VO, and CLI fallback can detect approval-like output and retry with `--yolo` for one turn. Hermes official behavior includes richer dangerous-command approval scopes: allow once, allow for session, always allow, and deny. The current VO implementation mainly exposes approve-once and deny, and Feishu notification does not provide the same approval actions.

Users want VO to align with Hermes approval semantics and, when Feishu bypass notifications are enabled, send an actionable Feishu approval card so the user can approve or deny from Feishu directly.

## Target Users

- VO users who run Hermes agents from the office chat or project workflows.
- Operators who rely on Feishu notifications for unattended or remote approval.
- Developers maintaining provider-neutral approval behavior across Hermes, Codex, and Claude Code.

## Goals

- Support Hermes dangerous command approval scopes in VO: `once`, `session`, `always`, and `deny`.
- Keep existing `approve_once` and `deny` behavior backward compatible.
- Render VO chat approval cards from `approval.choices` instead of hard-coding only approve-once and deny.
- Send an actionable Feishu approval card when Feishu notifications are enabled.
- Ensure VO chat and Feishu actions share the same backend approval response path.
- Avoid duplicate approval handling when the same approval is handled from both VO and Feishu.

## Scope

- Hermes native API approval events.
- Hermes CLI fallback approval detection and retry behavior.
- VO chat approval UI for Hermes.
- Feishu notification card generation and card action callback handling for Hermes approvals.
- Status/history/presence updates after approval responses.
- Tests for choice normalization, native API forwarding, Feishu card actions, idempotency, and compatibility.

## Non-Goals

- Implementing OS/root/sudo privilege escalation.
- Modifying Hermes long-term allowlist files directly from VO.
- Bypassing Hermes hardline blocklist behavior.
- Replacing Codex approval semantics.
- Creating a new independent approval system separate from existing VO approval handlers.

## Key Requirements

- REQ-001: Hermes approval choices must normalize to internal values `once`, `session`, `always`, and `deny`.
- REQ-002: Legacy choices such as `approve_once`, `approve`, `allow_once`, `cancel`, and `no` must continue to work.
- REQ-003: Native Hermes approval responses must pass the normalized choice to Hermes without collapsing all approvals to `once`.
- REQ-004: Approval payloads must preserve Hermes-provided `choices`; if missing, native API approvals default to `["once", "session", "always", "deny"]`.
- REQ-005: CLI fallback approvals must remain conservative. If no native run exists, `once` and `deny` are supported; `session` and `always` must not falsely claim persistent Hermes changes unless Hermes CLI support is explicitly available.
- REQ-006: VO chat UI must render Hermes approval buttons based on `approval.choices`.
- REQ-007: Feishu approval cards must contain actionable buttons for the same choices exposed by the approval payload.
- REQ-008: Feishu actions must call the same backend approval response logic as VO chat actions.
- REQ-009: Approval response handling must be idempotent by `approval_id`.
- REQ-010: `always` must be visually and textually treated as higher risk.

## Constraints

- Do not leak Feishu secrets, Hermes API keys, or private configuration.
- Do not auto-approve dangerous actions.
- Do not show action choices that Hermes did not offer for that approval.
- Do not create a second source of truth for approval state.
- Preserve current behavior for existing approve-once flows.

## Current Known Conclusions

- Hermes official approval semantics include `once`, `session`, `always`, and `deny`.
- VO currently has Hermes approval storage, polling, chat rendering, and native API response plumbing.
- Existing Feishu notification infrastructure supports interactive cards and card action callbacks elsewhere in the project.
- The first implementation should combine Feishu notification and approval action in one card, not a notification-only phase.
