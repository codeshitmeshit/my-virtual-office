# HUMAN DECISIONS Operations

> Status: current operations guide, verified against code on 2026-08-10. Chinese version: [HUMAN_DECISIONS.md](HUMAN_DECISIONS.md).

HUMAN DECISIONS is the shared pause-and-resume boundary whenever Virtual Office needs an explicit user choice. It covers chat, project execution, meetings, and Personal Assets sensitive-data authorization.

## Current behavior

- Decisions are durable across browser closure and service restart.
- Chat decisions wake the original Agent and conversation at most once with a stable source message id.
- Project decisions are written to the source task comments and resume the project workflow.
- Meeting decisions remain in the originating discussion round and become authoritative context for later participants.
- Sensitive Personal Assets disclosure grants one-time or current-task access and fails closed without a valid grant.
- Feishu delivery uses bounded context and never exposes sensitive values or Provider envelopes.

## HTTP boundaries

Management surface:

- `GET /api/human-decisions`
- `POST /api/human-decisions`
- `POST /api/human-decisions/<decisionId>/resolve`
- `POST /api/human-decisions/<decisionId>/reopen`

Agent surface:

- `POST /api/agent/human-decisions`
- `POST /api/agent/human-decisions/<decisionId>/execution-started`

Agent requests are authenticated from the trusted `X-VO-Agent-Id` header, never from a self-reported body field.

## Safety and idempotency

- Every decision binds its source surface, Agent, conversation, and optional project/task/meeting context.
- Only pending decisions can be resolved. Replayed callbacks and repeated clicks do not resume work twice.
- Missing, expired, or mismatched bindings fail closed without falling back to another conversation, project, or fixed recipient.

## Verification

```bash
.venv/bin/python -m pytest -q \
  tests/test_human_decisions.py \
  tests/test_human_decision_delivery.py \
  tests/test_human_decision_runtime_pause.py \
  tests/test_human_decision_chat_continuation.py \
  tests/test_human_decision_feishu_sync.py \
  tests/test_human_decision_skill.py
node tests/check_human_decision_center.mjs
node tests/check_meeting_human_decision_record.mjs
node tests/check_project_human_decision_comment.mjs
```
