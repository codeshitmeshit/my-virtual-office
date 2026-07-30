## Codex Chat Fast-Path Harness Failure and Resolution

Command:

```bash
.venv/bin/python tests/codex_chat_fast_path_performance.py --warmups 10 --runs 100 --output openspec/changes/optimize-chat-performance-cleanup/evidence/codex-chat-fast-path-performance.json
```

Result:

```text
AssertionError: expected 100 measured turns, got 0; failures=[{'index': 0, 'stage': 'terminal_sse_timeout'}, {'index': 1, 'stage': 'terminal', 'status': 'busy'}, ...]
```

Thread dump during the first timeout showed the provider worker blocked inside `app/providers/codex_app_server.py` waiting for the fake app-server execute response, while the SSE thread waited in `ProviderEventJournal.wait_for_run_events`. Focused Codex SSE, fast-path, journal, and coalescer tests passed after the journal/coordinator changes.

Resolution:

The performance harness reused the broad fake Codex server from `tests/test_codex_bridge.py`. The normal VO prompt guidance text can include approval-related wording, which triggered the fake server's approval scenario and intentionally waited for approval instead of completing the warm chat turn. The harness now patches `_with_vo_provider_guidance` to an identity function inside the fixture so it measures the intended warm Codex chat path rather than the fake approval branch.

Follow-up command passed and wrote `evidence/codex-chat-fast-path-performance.json`:

```bash
.venv/bin/python tests/codex_chat_fast_path_performance.py --warmups 10 --runs 100 --output openspec/changes/optimize-chat-performance-cleanup/evidence/codex-chat-fast-path-performance.json
```
