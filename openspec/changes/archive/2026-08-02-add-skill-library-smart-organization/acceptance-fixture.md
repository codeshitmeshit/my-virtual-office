# Skills Library Organization Acceptance Fixture

## Reproducible command

From the repository root:

```bash
node tests/run_skill_library_organization_acceptance.mjs
```

The runner uses `.venv/bin/python` when present (or `PYTHON`/`python3` as a fallback), stops on the first failure, and prints machine-readable timing evidence.

## Covered scenarios

- 103 real `SKILL.md` directories initially projected into `默认标签`.
- Six sequential archive-manager batches with sizes `20, 20, 20, 20, 20, 3`.
- Partial completion with 101 direct assignments and two failures left in `默认标签`.
- Owner repair of the two failures, live failure-count reduction, and final `resolved` state.
- Exactly one terminal archive-manager activity for the organization attempt.
- Visible `working`/`activeWork` projection while the run is held open.
- Immediate busy rejection of a competing archive-count operation, with no queue or operation call.
- Recovery of a persisted `running` result after restart, with interrupted skills retained in `默认标签`.
- Management-token rejection before request-body parsing, valid-owner dispatch, interactive token prompting, shared concurrent prompt, and retry behavior.
- Skills Library DOM behavior for progress, terminal markers, failure repair, and disabled mutation controls.

## Local evidence

Run on 2026-07-30:

- Acceptance domain fixture: `3 passed`.
- Owner authorization/HTTP contract: `14 passed`.
- Management-token dialog contract and behavior: passed.
- Skills Library organization UI state contract: passed.
- Runner result: `{"ok": true}`.

This local fixture uses a deterministic archive-manager response adapter. The real OpenClaw/archive-manager invocation remains a development-environment verification item because OpenClaw is not installed on this machine.
