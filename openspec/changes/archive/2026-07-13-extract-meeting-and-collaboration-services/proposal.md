## Why

Meeting lifecycle, AI meeting requests, action items, Agent occupancy restoration, notifications, and Feishu callbacks are tightly coupled inside the main server module. Isolating them after project extraction will make safety gates, recovery, and callback idempotency easier to verify.

## What Changes

- Extract meeting lifecycle and turn orchestration into meeting-domain services.
- Separate AI meeting request confirmation and action-item projection workflows.
- Separate notification delivery from Feishu callback/action processing.
- Consolidate executable Meetings, AI meeting requests, occupancy, events, and idempotency metadata into one authoritative JSON store.
- Provide an idempotent migration script that backs up, validates, and combines both legacy JSON stores before the unified store becomes authoritative.
- Preserve human confirmation requirements, Agent occupancy/restoration rules, callback idempotency, project linkage, API contracts, and stored records.
- This change starts only after the project execution service change is accepted and archived.

## Capabilities

### New Capabilities

- `meeting-collaboration-service-boundaries`: Defines independently testable ownership for meetings, requests, action items, notifications, and callback actions.

### Modified Capabilities

None currently; detailed review must reassess meeting behavior specs before implementation.

## Impact

- Expected code: `app/server.py`, Feishu integration modules, new meeting/collaboration service modules, and meeting/notification tests.
- API, confirmation-gate, and Agent-state behavior remain compatible; the internal persistence layout intentionally changes from two JSON stores to one through the verified migration path.
- Detailed design and tasks are deferred until preceding service boundaries are proven.
