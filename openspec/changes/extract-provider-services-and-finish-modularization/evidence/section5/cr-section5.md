# Section 5 whole-group code review

## Verdict

Section 5 is accepted for progression to Section 6. Conversation/history/native-ID coordination now passes through `ProviderConversationService`; existing JSON paths and shapes remain the single persistence authority. OpenClaw uses the queued-conversation capability boundary and does not synthesize background-run or SSE behavior.

## Ownership and compatibility review

- `ConversationKey` scopes state by provider kind, Agent, profile, and conversation. Reads are copies; messages, context, attachment descriptors, native IDs, and in-memory scope owners are bounded.
- Slow provider calls run outside conversation locks. Generation/version tokens reject stale continuation after reset, while an explicit Codex archived-thread recovery can refresh only its own operation token.
- Codex, Claude Code, and Hermes retain their existing history/state paths and provider-native session/thread recovery. No second store, rename, or dual write was added.
- OpenClaw retains HTTP, WebSocket, and CLI fallback order. Gateway authentication and session RPC details remain in the server adapter; the service receives only normalized scope, native session candidate, message, and bounded attachments.
- OpenClaw representative conversations map deterministically to Agent-owned Gateway sessions. Existing explicit session candidates, chat-session list/reset/delete, Project Execution task sessions, Meeting callers, history visibility, and error strings remain covered.
- OpenClaw queued delivery creates exactly one adapter call and no run repository or SSE event state.

## Confirmed findings resolved

1. **Per-conversation lock/generation ownership could grow without a bound.** Scope owners now use a 4,096-entry LRU bound and only inactive owners are evicted. Active scopes may temporarily exceed the limit but are pruned on release; evicted tokens cannot become valid after recreation.
2. **Codex archived-thread recovery was fenced as if it were an external concurrent reset.** The explicit same-operation recovery now replaces only its captured mapping token, so the fresh thread ID is saved while a real concurrent reset still rejects late writes.
3. **OpenClaw representative delivery ignored its conversation ID and reused the main session.** It now uses a deterministic, Agent-owned Gateway session candidate, preserving continuity while isolating unrelated Feishu conversations.
4. **OpenClaw representative attachments bypassed the shared descriptor checks and were not delivered as context.** They now use the same path/URL/size/count validation and bounded context format as provider chat.
5. **The queued adapter trusted any supplied native session string.** It now revalidates that reset, delete, and delivery session keys belong to the scoped OpenClaw Agent before handing off Gateway authentication or protocol work.

## Regression and performance evidence

- Isolated Python conversation/provider/Project/Meeting/Feishu regression files: **285 passed**, with two existing `lark_oapi` deprecation warnings.
- Script-style OpenClaw auth, chat-history, chat-session, Hermes Desktop/Platform/plugin, and provider-boundary suites passed.
- JavaScript/static compatibility checks: **11/11 passed**.
- Characterization manifest: **21/21 passed**.
- Conversation performance artifact covers 1/20/100 parallel scopes, retains at most 500 messages per fixture, and proves 100 queued requests produce exactly 100 adapter calls and zero synthetic run records.
- Python compilation, generated-inventory reproducibility, `git diff --check`, and strict OpenSpec validation passed.
