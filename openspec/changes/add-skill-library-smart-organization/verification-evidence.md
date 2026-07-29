# Verification Evidence

Date: 2026-07-30
Branch: `codex/skill-library-smart-organization`

## Passing gates

### Focused Skills Library Python suite

```bash
/usr/bin/time -p .venv/bin/python -m pytest -q \
  tests/test_skill_library_catalog.py \
  tests/test_skill_library_catalog_integration.py \
  tests/test_skill_library_organization_acceptance.py \
  tests/test_skill_library_organization_admin.py \
  tests/test_skill_library_organization_contract.py \
  tests/test_skill_library_organization_feature_flag.py \
  tests/test_skill_library_organization_http_contract.py \
  tests/test_skill_library_organization_routes.py \
  tests/test_skill_library_organization_runs.py
```

Result: `88 passed in 1.75s` (`2.19s` wall).

### End-to-end acceptance fixture

```bash
node tests/run_skill_library_organization_acceptance.mjs
```

Result:

- 103-skill domain flow: `3 passed`.
- Owner authorization/HTTP contract: `14 passed`.
- Management-token prompt/retry behavior: passed.
- Skills Library progress/repair DOM behavior: passed.
- Runner emitted `{"ok": true}`.

The capacity run processed six sequential batches sized `20, 20, 20, 20, 20, 3`; it committed 101 assignments, retained two failures in `默认标签`, repaired them individually, and reached `resolved`.

### Management boundary

```bash
/usr/bin/time -p .venv/bin/python -m pytest -q \
  tests/test_agent_legacy_mutation_http.py \
  tests/test_agent_legacy_mutation_policy.py \
  tests/test_skill_library_organization_http_contract.py
node tests/test_management_token_dialog.js
```

Result: `25 passed in 0.51s` (`0.66s` wall), plus all management-token dialog, domain-403, shared-prompt, and retry checks passed (`0.03s` wall).

### UI and localization contracts

```bash
node tests/test_skill_library_organization_ui_states.js
node tests/test_skill_library_organization_ui_static.mjs
python3 -m json.tool app/locales/en.json
python3 -m json.tool app/locales/zh.json
```

Result: both JavaScript contracts passed (`0.03s` and `0.02s` wall), and both locale files parsed successfully. Earlier Task 5.1 browser acceptance also verified the three-column desktop layout and one-column 600px layout without horizontal overflow.

### MCP Registry separation

```bash
env PYTHONPATH=app .venv/bin/python -m pytest -q \
  tests/test_mcp_assignment.py \
  tests/test_mcp_native_clients.py \
  tests/test_mcp_registry_live_server_routes.py \
  tests/test_mcp_registry_native_routes.py \
  tests/test_mcp_registry_service.py
```

Result: `17 passed in 0.64s` (`1.11s` wall). The Skills Library static contract also verifies that its modal has no MCP Registry action.

### Direct-filesystem, legacy CRUD, and rollback compatibility

```bash
/usr/bin/time -p .venv/bin/python -m pytest -q \
  tests/test_skill_library_catalog_integration.py \
  tests/test_skill_library_organization_feature_flag.py \
  tests/test_agent_legacy_mutation_http.py \
  tests/test_agent_legacy_mutation_policy.py \
  tests/test_agent_mutation_route_characterization.py
```

Result: `37 passed in 0.71s` (`1.19s` wall).

The feature-flag checks prove that the default-off flag rejects only new organization starts, disabled reads do not rewrite the sidecar, and existing create/list/delete operations continue to work. Direct filesystem additions project into `默认标签` without a read-time write; authorized create/import/save/delete paths update or compact metadata.

### OpenSpec structure

```bash
openspec validate add-skill-library-smart-organization --strict
```

Result: `Change 'add-skill-library-smart-organization' is valid`.

## Broader regression observations

### Archive Room suite

```bash
.venv/bin/python -m pytest -q \
  tests/test_archive_manager_coordinated_operations.py \
  tests/test_archive_manager_lifecycle_adapter.py \
  tests/test_archive_manager_lifecycle_ownership.py \
  tests/test_archive_manager_work_coordinator.py \
  tests/test_archive_room_ai_refine.py \
  tests/test_archive_room_phase_1_3.py \
  tests/test_archive_room_phase_4.py \
  tests/test_archive_room_phase_5.py \
  tests/test_archive_room_phase_6.py \
  tests/test_archive_room_phase_7.py \
  tests/test_archive_room_phase_8.py
```

Result: `58 passed, 7 failed in 2.26s` (`2.70s` wall).

All shared-coordinator and skill-organization acceptance paths passed. The seven failures are existing text-contract drift in files untouched by this branch:

- Six assertions expect legacy archive-manager profile phrases such as `<archive_manager_output` or `Manual Current-Project Maintenance Procedure`, while the current template uses `<archive_manager_instructions>` and hard output boundaries.
- One Phase 6 assertion expects the exact English sentence `does not override your identity`, while the current prompt expresses the boundary with `override="false"` and different wording.

### Route-split checks

```bash
.venv/bin/python -m pytest -q tests/test_server_routes_module_split.py
node tests/check_server_frontend_module_split.mjs
```

Results:

- Python: `15 passed, 1 failed in 0.54s` (`0.99s` wall). The pre-existing meeting-history test monkeypatch accepts no `summary` argument, but the current route calls `_meeting_history_projection(summary=summary)`.
- JavaScript: failed in `0.04s` because the existing `app/server.py` still contains `def _handle_project_create`.

Neither failure target is modified by this change.

## Residual risks and unverified environments

- OpenClaw is not installed on this machine. The real archive-manager model invocation, provider timeout behavior, and live Archive Room activity rendering must be rerun in a development environment with OpenClaw available.
- The 103-skill capacity fixture uses deterministic archive-manager JSON. It verifies batching, persistence, recovery, and correction semantics, but not real-model latency or classification quality.
- Production rollout remains default-off through `VO_SKILL_LIBRARY_ORGANIZATION_ENABLED`. Enable it only after the development-environment run passes, and retain the flag as the immediate rollback control.
- The unrelated Archive Room template assertions and route-split failures should be repaired in their owning changes; they are recorded here so they are not mistaken for regressions introduced by skill organization.

## Development-environment OpenClaw gate

Upload or check out this branch on a dedicated development instance whose `默认标签` contains no unrelated skills. Start Virtual Office with the feature enabled and a known management token, then run:

```bash
VO_TEST_URL=http://127.0.0.1:8090 \
VO_MANAGEMENT_TOKEN='<development token>' \
VO_LIVE_ACCEPTANCE_ALLOW_MUTATION=1 \
VO_LIVE_SKILL_COUNT=103 \
.venv/bin/python tests/skill_library_organization_live_acceptance.py
```

The script first verifies unauthorized rejection, creates uniquely prefixed test skills, refuses to organize if unrelated default-category skills exist, invokes the real archive manager, polls the terminal result, repairs any failed test classifications one at a time, checks the existing Archive Room activity log, and deletes its test skills in `finally`.
