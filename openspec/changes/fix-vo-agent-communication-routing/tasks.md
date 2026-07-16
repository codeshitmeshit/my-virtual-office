## 1. OpenClaw Availability

- [x] 1.1 Implement centralized OpenClaw home inspection for valid configuration, directory fallback, residual homes, and malformed configuration; use it for both roster discovery and `/vo-config.openclaw.detected`, with focused discovery/config tests.

## 2. Canonical Communication Skill

- [x] 2.1 Replace the generated legacy communication skill source with a validated loader for `skills/vo-agent-communication/SKILL.md`; seed the exact canonical content into Skills Library and safely migrate the reserved legacy library entry, with source-consistency and migration tests.
- [x] 2.2 Implement the locked, atomic, hash-based OpenClaw workspace skill synchronizer and managed marker; cover first install, no-op repeat, managed upgrade, unmarked conflict, known legacy migration, path-boundary rejection, and unrelated-file preservation.

## 3. Agent Lifecycle Integration

- [x] 3.1 Run managed communication-skill synchronization at OpenClaw discovery refresh, attach non-sensitive readiness states to roster/workspace payloads, and ensure one agent failure does not suppress other discovered agents; add focused integration tests.
- [x] 3.2 Install the canonical skill during normal OpenClaw and archive-manager creation, return precise partial-creation failures, and strengthen the new-agent `AGENTS.md` communication rules; add creation and template regression tests.

## 4. Routing and Traceability Verification

- [ ] 4.1 Add communication routing regressions that verify current roster identities, stable `conversationId`, request/reply or terminal-failure history, busy/timeout/empty-reply handling, and the canonical prohibition on private session/CLI fallback.
- [ ] 4.2 Add and execute a real OpenClaw delegation acceptance check for “让分析师看一下最近市场动向”, recording evidence that VO history contains the request/reply and the corresponding activity contains no `sessions_list`, `sessions_send`, or `openclaw agents` fallback.

## 5. Final Verification

- [ ] 5.1 Run the focused Python/JavaScript regressions, the relevant broader test suites, and strict OpenSpec validation; record commands, results, residual risks, and rollback verification in change evidence.
