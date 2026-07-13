# Section 2 whole-section CR

## Verdict

Pass. The unified in-process run repository and event journal are ready for the shared run coordinator migration. No blocking correctness, security, data-consistency, compatibility, or performance finding remains.

## Implemented ownership

- `ProviderRunRepository` is the sole owner of run metadata and both legacy idempotency namespaces.
- `ProviderEventJournal` is the sole owner of the global event cursor, 4,000 retained events, scope indexes, and bounded terminal dedupe markers.
- `ProviderRunBridge`, Claude compatibility maps/queues, and Codex/provider idempotency globals are copying delegates over those owners.
- HTTP status/header/SSE framing remains in `app/server.py`; neither service imports server, HTTP, SSE, or a concrete adapter.

## Findings and resolution

1. **Resolved — terminal event could commit an incomplete result.** Some workers emit a terminal event before writing their final result. Terminal event claiming now fences publication without replacing the result; the matching final result commits afterward.
2. **Resolved — Codex `cancelling` compatibility.** Existing Codex cancellation returns `status=cancelling` but publishes `run.cancelled`. Terminal normalization now recognizes both `cancelling/canceling` and `cancelled/canceled`.
3. **Resolved — terminal dedupe disappeared after event eviction.** Bounded terminal markers now survive journal event eviction and remain capped at the configured event capacity.
4. **Resolved — incomplete event allowlist.** Every event alias frozen in Section 1 is retained; only `run.canceled` is canonicalized to the existing `run.cancelled` spelling.
5. **Resolved — embedded absolute paths could survive redaction.** Path detection now handles a path embedded in an error string, in addition to values beginning with a path.
6. **Resolved — compatibility `pop(default)` sentinel identity.** Missing-key defaults are returned without deep-copying, matching mapping semantics.
7. **Resolved — legacy completed run registration.** A remembered `done` run immediately receives terminal and cleanup metadata so late SSE reads and retention remain correct.

## Correctness and consistency evidence

- Atomic duplicate reservation: one launch owner under 20 concurrent same-scope callers.
- Independent ownership: 100 different scopes produce 100 runs without shared state.
- One terminal winner: completion/cancellation race produces one state result and one terminal event.
- Late completion and stale cleanup generation cannot overwrite/remove a newer owner.
- Snapshot and compatibility map reads are copies; the legacy queue handle is the only intentional compatibility projection.
- 0/1/4,000/4,001 event fixtures prove monotonic IDs, exact retention, and eviction-consistent run/conversation indexes.

## Security evidence

- Sensitive keys, bearer/API-key/private-key patterns, disallowed absolute paths, oversized strings/lists/maps, malformed payloads, and unsafe field names are bounded or removed before journal persistence.
- Secret/path scan over current and Section 2 evidence found no match.
- Static service-boundary tests prove no reverse dependency on server/HTTP/concrete adapters.

## Regression and performance evidence

- Baseline characterization manifest: 21/21 commands passed.
- Provider/SSE/history/Feishu Python suite: 195 passed; 2 third-party deprecation warnings only.
- Provider-related JavaScript/static suite: 7/7 passed.
- Repository/event/boundary focused suite: 22/22 passed.
- Fixed performance comparison: 24/24 gates passed; provider launch and terminal counts did not increase.
- Mixed 4,000-event/100-scope fixture: run-scoped replay inspects 40 target events, not all 4,000 retained events.
- OpenSpec strict validation, Python compilation, inventory reproducibility, and `git diff --check` passed.

## Intentional defect correction

The Section 1 barrier fixture originally reproduced two terminal events for cancel-vs-complete. It now asserts exactly one terminal winner. This is the confirmed, specification-backed defect correction for this slice; no product policy or frontend behavior changed.

## Gate to Section 3

Proceed with `provider_ports.py` and `provider_runs.py`. Provider processes, history I/O, Project/Meeting calls, notifications, JSON serialization, and socket writes must continue to execute outside repository locks.
