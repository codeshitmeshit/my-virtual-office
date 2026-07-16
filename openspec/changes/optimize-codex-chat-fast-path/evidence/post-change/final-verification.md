# Codex chat fast path: final verification

Captured on 2026-07-16 in the dedicated `codex/optimize-codex-chat-fast-path` worktree. All performance fixtures are deterministic and use a fake local Codex app-server; they do not use a real model or external credentials.

## Fixed warm-chat comparison

Command:

```bash
VO_CODEX_CHAT_FAST_PATH_ENABLED=1 \
VO_CODEX_MAX_CONCURRENT_TURNS=2 \
VO_CODEX_STREAM_COALESCE_MIN_MS=33 \
VO_CODEX_STREAM_COALESCE_MAX_MS=100 \
.venv/bin/python tests/codex_chat_fast_path_performance.py \
  --warmups 10 --runs 100 \
  --output openspec/changes/optimize-codex-chat-fast-path/evidence/post-change/codex-chat-fast-path-performance.json
```

The fixture identity is unchanged from baseline: warm resumed conversation, existing native thread, already-running fake app-server, 10 warm-ups, 100 measured turns, and 20 reasoning deltas per turn. All 100 measured turns completed without an error.

| Stage | Baseline p95 | Candidate p95 | Delta |
| --- | ---: | ---: | ---: |
| Working feedback | 0.000 ms | 0.000 ms | 0.000 ms |
| Provider request | 30.895 ms | 23.814 ms | -7.081 ms |
| First native event | 31.442 ms | 24.266 ms | -7.176 ms |
| First native SSE | 69.762 ms | 27.904 ms | -41.858 ms |
| First fragment SSE | 69.762 ms | 27.904 ms | -41.858 ms |
| First text SSE (observation only) | 133.724 ms | 27.992 ms | -105.732 ms |
| Provider terminal | 1063.628 ms | 29.082 ms | -1034.546 ms |
| Durable terminal commit | 1100.180 ms | 37.920 ms | -1062.260 ms |
| Terminal tail | 271.926 ms | 38.213 ms | -233.713 ms |
| Reader callback total | 1084.045 ms | 14.512 ms | -1069.533 ms |

Every listed stage has 100 samples. The simulated synchronous browser boundary is useful for exact before/after fixture identity, but is not presented as a real browser paint measurement.

The independent browser-local timing fixture excludes 10 warm-ups and measures 100 turns using one monotonic browser clock. Its p95 values are 16 ms working feedback, 86 ms first matching native event, 105 ms first fragment, and 289 ms first text. First text remains a separate observation. Deliberately extreme service timestamps do not affect these values.

## Operation counts

| Operation | Baseline total / median per turn | Candidate total / median per turn | Result |
| --- | ---: | ---: | --- |
| Activity JSON loads | 3100 / 31 | 300 / 3 | reduced by 2800 |
| Activity JSON writes | 3100 / 31 | 200 / 2 | reduced by 2900 |
| Communication history loads | 3500 / 35 | 300 / 3 | reduced by 3200 |
| Communication progress rewrites | 3300 / 33 | 0 / 0 | eliminated |
| Durable communication appends | 200 / 2 | 300 / 3 | +1 idempotent terminal outcome per turn |

The additional append is the intentional durable terminal record introduced for restart and rollback correctness. Transient activity/progress work is the optimization target and is strictly reduced. The machine-readable comparison reports 14/14 passed gates in `codex-chat-fast-path-comparison.json`.

## Capacity, compatibility, durability, and security

- Capacity 1 remains supported. Capacity 2 is approved by the deterministic multiplexing fixture: two native threads interleave start, reasoning, approval, user input, cancellation, completion, result delivery, and cleanup without cross-delivery. Capacity 3–4 remains unproven and is not approved for rollout.
- Flag-off focused regression: 128 passed. Flag-on focused regression at capacity 2 and 33–100 ms coalescing: 85 passed.
- Rollback rehearsal: passed. It writes accepted user content, approval request/resolution, final reply, terminal outcome, and thread mapping while enabled; replaces the live view with a fresh flag-off instance; reads every durable surface; and proves that recovery did not mutate any status file.
- Browser/static compatibility: Codex runs, approval UI, Provider SSE, app-server split, runtime settings, history store/navigation, chat bug regressions, Claude Code SSE, and browser timing checks passed. The in-app browser loaded the cache-busted `chat.js` and timing script with zero console errors.
- Bounded/redacted diagnostics: config, event service, coalescer, telemetry, and browser-timing tests passed. Diagnostics contain fixed-cardinality counters, bounded samples, digested/run IDs, and stage durations; prompt, reply, reasoning, credential, approval content, raw payload, and unrestricted path canaries are absent.
- Complete Python regression was split to avoid a known cross-module temporary-directory cleanup race: 671 non-Project tests passed and 100 Project Execution tests passed, for 771 passed total. Two prior monolithic attempts each reached 770 passed and failed only in a different Project Execution temporary-directory cleanup; each failed test passed immediately in isolation.
- Strict OpenSpec validation passed: one change valid, zero failed, zero issues.

## Environment-gated and unverified checks

- A real Codex model/provider, real credentials, production network latency, and real token load were not exercised. No real-Provider latency or correctness claim is made.
- `tests/chat_history_ui_e2e.mjs` requires an external Chrome CDP endpoint at `127.0.0.1:9224`; that endpoint was unavailable. The in-app browser verification is recorded separately and does not replace a real Codex conversation E2E.
- `tests/test_workflow_e2e.py` requires a management-token workflow environment and was excluded. This change does not claim that environment-gated workflow passed.
- Root-level `pytest` collection remains unusable because the pre-existing `test_review_parser.py` executes `sys.exit(0)` during collection. The supported `tests/` suite was used instead.
- Browser paint behavior was tested with deterministic browser-local timing plus in-app resource/error verification. A real user/device p95 study is not claimed.

## Evidence artifacts

- Baseline: `evidence/baseline/codex-chat-fast-path-performance.json`
- Candidate: `evidence/post-change/codex-chat-fast-path-performance.json`
- Machine comparison: `evidence/post-change/codex-chat-fast-path-comparison.json`
- Rollout and rollback runbook: `docs/CODEX_CHAT_FAST_PATH_OPERATIONS.md`
