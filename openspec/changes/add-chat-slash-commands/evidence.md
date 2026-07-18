# Verification Evidence

Date: 2026-07-18 (Asia/Shanghai)

## Automated validation

| Command | Result |
| --- | --- |
| `openspec validate add-chat-slash-commands --strict` | PASS — change is valid |
| `openspec status --change add-chat-slash-commands` | PASS — 4/4 artifacts complete |
| Focused Python command/Provider/Feishu suite | PASS — 69 tests |
| `tests/test_feishu_notifications.py` | PASS — 75 tests |
| `tests/test_codex_server.py` | PASS — 18 tests |
| Focused status/config suite after documentation changes | PASS — 24 tests |
| Chat/history/Provider/Codex/Claude JavaScript checks | PASS — 9 scripts |
| `node --check app/chat.js` | PASS |
| `python -m py_compile app/server.py app/feishu_chat_channel.py` | PASS |
| `git diff --check` | PASS |

The focused Python runs cover exact parsing, attachment rejection, feature flags, management authentication, authoritative Agent/provider resolution, cross-Agent session rejection, VO identity switching, Provider reset isolation, Codex compaction outcomes, unsupported Providers, busy admission, durable started/terminal recording, idempotent redelivery, restart indeterminate recovery, feedback failure, Feishu private/group admission, same-group shared scope, cross-group isolation, and the representative-Provider matrix.

## Flag acceptance

- Both flags off: VO browser falls through to the pre-change ordinary send path; Feishu exact command text follows ordinary Agent dispatch.
- Global flag on, Feishu flag off: VO command endpoint is enabled while Feishu retains ordinary-message behavior.
- Both flags on: admitted VO and Feishu exact attachment-free commands route to command handling; unknown, differently cased, argument-bearing, attached, and unmentioned-group traffic retains existing behavior.
- Status projection exposes only effective booleans, bounded reservation counts, and fixed-dimension aggregate metrics.

## Self-review

Reviewed the committed change range across four dimensions:

- Security: management authentication remains the browser trust boundary; Feishu supplies trusted Agent and derived conversation IDs; caller provider overrides are rejected; status and audit projections omit credentials, raw Provider output, and raw scope labels.
- Stability: command admission is non-blocking, terminal recording follows durable started recording, restart recovery does not replay an uncertain side effect, old VO history is preserved, and mismatched browser responses cannot switch the active selection.
- Requirement and tests: every confirmed scenario has implementation and automated evidence; existing new-session buttons and ordinary-message paths remain compatible.
- Maintainability: parsing/orchestration, Provider control, and runtime state live in focused service modules; `server.py` contains transport wiring and adapters only. No P0/P1/P2 issue remained after review.

## External acceptance not executed

No real Feishu tenant credentials or live Provider sessions were used in this workspace. Before production enablement, perform the documented disposable-tenant staged check for private delivery, mentioned/unmentioned groups, duplicate callback, process restart, outbound feedback failure, same-group concurrency, cross-group isolation, and status/metric observation. Keep both flags off until that check begins.
