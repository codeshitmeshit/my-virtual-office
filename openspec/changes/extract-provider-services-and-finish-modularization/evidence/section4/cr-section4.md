# Section 4 whole-group code review

## Verdict

Section 4 is accepted for progression to Section 5. Hermes API and Desktop background runs now use the shared run coordinator; Gateway Platform remains a queued-delivery capability. Hermes approval ownership is bounded, redacted, linked, and decision-fenced. Feishu parsing/authenticity remains in transport code and provider-native continuation remains in Hermes clients.

## Ownership and compatibility review

- API and Desktop starts reserve the provider/Agent/conversation/idempotency scope before one adapter launch. The repository owns active projection, retention, terminal fencing, and legacy queue snapshots.
- Desktop execution no longer belongs to an SSE connection. It starts once in the coordinator and the Hermes SSE route consumes the same journal as API runs.
- Desktop-first, API fallback, CLI fallback, and Gateway queued-message behavior retain their existing path precedence and stable provider-path values.
- Native Hermes run/session IDs are recorded as fenced state updates and are used for cancellation. Late completion cannot overwrite cancellation.
- `ProviderApprovalService` owns ordered pending records with a 1,000 global and 100 per-scope cap, 2,000 resolved-record cap, retention pruning, copy-on-read DTOs, immutable linkage, redaction, one decision token, claim lease recovery, replayed outcomes, and bounded notification intent/state.
- Existing once/session/always/deny actions, HTTP and Feishu callers, CLI one-time retry, native continuation, pending query shape, event publication, history entries, and legacy records without native linkage remain covered.

## Confirmed findings resolved

1. **Hermes API background runs still had a second idempotency/thread/terminal owner.** API start, events, timeout, terminal, retention, and stop now go through `ProviderRunCoordinator`.
2. **Desktop run execution was owned by the first SSE connection and used a separate active-run map.** Desktop now starts through the coordinator; SSE is a journal consumer and active state is projected from the shared repository.
3. **The Hermes approval queue was unbounded.** It now has explicit aggregate, per-scope, resolved-record, and retention bounds with deterministic capacity tests.
4. **Approval removal happened before the slow provider decision and repeated/concurrent delivery could call the provider again.** Resolution now claims a decision token, executes outside the lock, commits only the winning token, and replays the stored result.
5. **A supplied approval payload could target a foreign run/session or overwrite trusted linkage.** Agent/profile/session/run linkage is service-owned and missing, forged, stale, cross-run, or relinking decisions fail closed.
6. **Provider/notification failure could lose pending business state.** Notification failure is recorded without removing the approval; continuation failure is bounded and replayable.
7. **Hermes raw native event objects and secret/path-bearing errors could enter common output.** Raw event copies were removed and errors are sanitized before repository/event persistence; canary tests cover credentials and private paths.
8. **The native run ID was not captured before coordinated cancellation.** A `run.native.started` state update now records it, and cancellation calls the correct native ID exactly once.
9. **Cancellation after an approval request could leave a stale actionable approval.** Run cancellation now fences linked pending approvals as denied/cancelled; a late different decision returns a stable conflict and cannot call Hermes.
10. **Generic metadata updates could mutate approval linkage or status.** Service updates now reject immutable identity, linkage, state, and outcome fields.

## Regression and performance evidence

- Broad Provider/Codex/Claude/Hermes/Project/Meeting/Feishu/history/SSE/WebSocket Python group: **508 passed**, with two existing third-party deprecation warnings.
- Focused coordinator/approval/Hermes security and compatibility group: **38 passed** after final findings were fixed.
- JavaScript/static compatibility checks: **11/11 passed**.
- Characterization manifest: **21/21 passed**.
- Approval performance artifact: 1,000 registrations retained exactly 1,000 pending records across 10 scopes in approximately 28.84 ms; registration median/p95 were approximately 27.7/42.7 microseconds. Resolving 100 approvals produced exactly 100 provider calls; replay produced no extra calls and left 900 pending.
- Coordinator 1/20/100 performance evidence remains valid.
- Generated inventory now reports Hermes approval bounds and reproduces exactly; the frozen pre-migration baseline remains unchanged.
- Python compilation, `git diff --check`, and strict OpenSpec validation passed.

## Deferred cleanup already scoped by the change

- The now-unreachable direct Desktop SSE business handler and compatibility symbol names remain until the final zero-caller cleanup in Section 7. Runtime and static tests prove Hermes routes no longer dispatch to that handler or write a second active/approval authority.
- The two warnings originate in `lark_oapi` and are unrelated to provider orchestration.
