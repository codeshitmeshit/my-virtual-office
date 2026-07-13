# Phase 8 startup and runtime acceptance

Date: 2026-07-13

Every application process in this acceptance was started with `./start.sh`. No server was started by invoking Python directly. Each case used an isolated `VO_STATUS_DIR` and ports `8190/8191`; candidate processes were stopped with `Ctrl+C` before changing state.

## Authority gate

- Legacy data without `meeting-domain.json`: `GET /api/meetings/store-status` and a Meeting mutation returned HTTP 409 with `meeting_store_migration_required`; no unified file was created.
- Unknown unified schema version 99: the same requests returned HTTP 500 with `meeting_store_invalid`.
- Migrated legacy fixture: dry-run returned `validated`, apply returned `migrated`, counts were Meeting 1 / request 1 / event bucket 1 / occupancy 2, and every relationship check passed. After `start.sh`, Store status was `unified` schema 1, the active Meeting and linked request were readable, and reconcile retained both valid occupancy claims.

## Runtime workflows

Against a clean candidate started through `start.sh`:

- `tests/test_workflow_e2e.py`: **20/20 passed** with management token 4285.
- `tests/test_crud_projects.sh`: **5/5 passed** after the script was corrected to send the configured management-token header.
- `tests/meeting_phase8_acceptance.py`: passed health, management authorization denial, Meeting creation/intervention/agenda/terminalization, recovery and occupancy cleanup, request confirmation and atomic conversion, Project resume, action-item existing-task projection, and missing-webhook notification degradation.
- Trusted callback authenticity, replay and concurrent delivery are covered by the deterministic callback regression from Phase 7; no external Feishu credential was configured during runtime acceptance, so no real callback or irreversible delivery was emitted.

The startup report confirmed HTTP and WebSocket listeners. Gateway and browser-CDP health were unavailable because no local gateway token or Docker/CDP service was configured; these optional integrations did not affect Meeting-domain acceptance.
