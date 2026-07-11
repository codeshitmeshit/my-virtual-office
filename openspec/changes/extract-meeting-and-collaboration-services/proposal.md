## Why

Meeting lifecycle, AI meeting requests, action items, Agent occupancy restoration, notifications, and Feishu callbacks are tightly coupled inside the main server module. Isolating them after project extraction will make safety gates, recovery, and callback idempotency easier to verify.

## What Changes

- Extract meeting lifecycle and turn orchestration into meeting-domain services.
- Separate AI meeting request confirmation and action-item-to-task workflows.
- Separate notification delivery from Feishu callback/action processing.
- Preserve human confirmation requirements, Agent occupancy/restoration rules, callback idempotency, project linkage, API contracts, and stored records.
- This change starts only after the project execution service change is accepted and archived.

## Capabilities

### New Capabilities

- `meeting-collaboration-service-boundaries`: Defines independently testable ownership for meetings, requests, action items, notifications, and callback actions.

### Modified Capabilities

None currently; detailed review must reassess meeting behavior specs before implementation.

## Impact

- Expected code: `app/server.py`, Feishu integration modules, new meeting/collaboration service modules, and meeting/notification tests.
- No intentional API, persistence, confirmation-gate, or Agent-state behavior changes.
- Detailed design and tasks are deferred until preceding service boundaries are proven.
