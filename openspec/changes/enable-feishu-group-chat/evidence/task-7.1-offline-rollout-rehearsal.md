## Task 7.1 Offline Rollout Rehearsal

Date: 2026-07-16

Command:

```bash
.venv/bin/python scripts/rehearse-feishu-channel-rollout.py
```

Result: `ok=true` with every rehearsal check passing:

- group default-off
- Node transport test enablement
- classified outbound timeout while preserving the Agent outcome
- switch disablement rejects new group turns
- persisted source outcome reconciles across simulated restart
- injected missing-SDK failure remains isolated from VO startup
- legacy transport rollback restores private-only behavior
- private history and group audit/source-index state remain durable
- no history migration or destructive rewrite occurs

The script uses a temporary `VO_STATUS_DIR`, redacted fake credentials, fake Agent dispatch, and no Feishu network access. The operator procedure and counter/pressure interpretation are documented in `docs/feishu-channel-worker.md`.
