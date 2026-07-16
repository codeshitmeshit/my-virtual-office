## Task 7.2 Real-Tenant Acceptance Gate

Date checked: 2026-07-16

The running local VO instance reported, using only redacted booleans/status:

- Chat App configured: yes
- Chat App enabled: yes
- effective transport: `channel-sdk-node`
- long connection: `connected`
- representative Agent configured: yes
- `groupChatEffective`: absent, indicating the running server has not yet restarted onto this change

No disposable trusted Feishu group/chat ID was available in the task context. The acceptance requires external state changes (adding the bot to a known group and enabling the new switch) and would send messages to real people. It was therefore not executed or marked complete.

Required inputs before acceptance:

1. Restart the local VO server on this change.
2. Add the Chat App bot to a disposable trusted group whose full membership is approved for Agent/tool access.
3. Provide or identify that group as the sole acceptance target.
4. Keep broader group activation disabled until every Task 7.2 scenario passes.

No credential value, group message, member list, or chat identifier was written to this evidence.

### Provisional owner acceptance after restart

Later on 2026-07-16, the service was restarted on the completed implementation and
reported `groupChatEffective=true`, `allowedChatTypes=["p2p", "group"]`, a connected
Node Channel SDK worker, and an empty non-pressured spool. The requirement owner then
reported that no further issue had been observed and explicitly accepted the
requirement for the current push.

This owner acceptance confirms the test-result gate for the observed deployment. It
does not claim that every destructive/failure-injection item in the exhaustive Task
7.2 matrix was independently rerun, so Task 7.2 remains open and broader activation
must still follow that checklist. Final OpenSpec archival also remains a separate
explicit confirmation gate.
