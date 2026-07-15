# Real-tenant Acceptance Gate

Status: accepted by the user on 2026-07-16 after controlled real-tenant and local-browser verification.

Do not record App Secrets, worker tokens, authorization headers, credential-bearing URLs, message bodies containing sensitive data, or unredacted user identifiers in this file.

Evidence classification: `manual` means directly observed by the user during this acceptance session; `automated` means covered by deterministic contract/fault tests; `rehearsal` means covered by the isolated legacy → Node → failure → rollback exercise.

- [x] SDK WebSocket handshake reaches connected and command-ready state. (`manual`)
- [x] Private text reaches the selected representative Agent and replies in the same chat. (`manual`)
- [x] Image and file resources download under the managed attachment root with correct metadata. (`manual` for image; `automated` for file and metadata boundaries)
- [x] Duplicate delivery is persisted once; rapid same-chat messages preserve order. (`manual` duplicate-render verification; `automated` persistence/order)
- [x] Changing the representative Agent affects only future messages. (`automated`)
- [x] Agent failure retains/replays durable work and surfaces bounded actionable status. (`automated`)
- [x] Outbound failure categories appear without leaking credentials. (`automated`)
- [x] Network reconnect and worker restart recover pending spool without duplicate history. (`manual` restart/live recovery; `automated` pending-spool replay)
- [x] Settings UI, worker status, history, and communication ledger remain consistent. (`manual` and `automated`)
- [x] Notification receiver and card actions continue independently. (`automated`)
- [x] `legacy-python` rollback starts exactly one consumer and requires no history migration. (`rehearsal`)

Record only redacted timestamps, stable status names, counters, and pass/fail conclusions here.

## Redacted conclusion

- 2026-07-16: worker status was `connected`, `running=true`, `transport=channel-sdk-node`, `sdkConnected=true`, and `lastError` was empty after restart.
- 2026-07-16: real Feishu text and image messages reached the selected Codex Agent; replies and authoritative history appeared through SSE without manual refresh.
- 2026-07-16: duplicate optimistic/authoritative bubbles and broken attachment rendering were rechecked after fixes; the user accepted the workspace behavior.
- 2026-07-16: Node contract suite passed 22/22, Python regression passed 712/712, workflow E2E passed 20/20, and the offline rollout rehearsal completed with history preserved and legacy rollback restored.
