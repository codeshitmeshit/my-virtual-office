# Personal Assets and Alibaba Cloud OSS

> Status: current operations guide, verified against code on 2026-08-10. Chinese version: [PERSONAL_ASSETS_AND_OSS.md](PERSONAL_ASSETS_AND_OSS.md).

## Boundaries

Personal Assets stores profile, career, interests, chat preferences, office goals, and extensible information for this single-user deployment.

- Local authority: `VO_STATUS_DIR/personal-assets.json`
- OSS credentials: `VO_STATUS_DIR/oss-settings.json`, atomically written with owner-only permissions
- OSS synchronization: optional, asynchronous, local-first weak sync; cloud failure never reverses a successful local mutation
- Sensitive data: excluded from profile outlines, logs, notifications, exported configuration, and ordinary Agent responses
- Sensitive reads: authorized through HUMAN DECISIONS for one-time or current-task disclosure

## Management API

These routes require the existing management session/token boundary:

- `GET /api/personal-assets`
- `POST /api/personal-assets/entries`
- `POST /api/personal-assets/entries/<entryId>` with `operation=update|delete`
- `POST /api/personal-assets/suggestions/<suggestionId>/accept`
- `POST /api/personal-assets/suggestions/<suggestionId>/reject`

Writes use `expectedRevision` for optimistic concurrency. A conflict must preserve the draft and reload the baseline instead of silently overwriting another write.

## Agent API and skill

Agents must read `skills/vo-personal-assets/SKILL.md` and use the Agent identity boundary, never a management token.

- `POST /api/agent/personal-assets/profile-outline`
- `POST /api/agent/personal-assets/request-context`
- `POST /api/agent/personal-assets/suggest-change`
- `POST /api/agent/personal-assets/apply-confirmed-onboarding`
- `POST /api/agent/personal-assets/feishu-onboarding-form`

Onboarding drafts stay in conversation context until the user gives exact confirmation. Idempotency keys are bound to the canonical change set and cannot be reused for different content.

## OSS configuration and synchronization

OSS is configured only through Settings. It does not read OSS environment variables or generic `vo-config.json` values.

- `GET /api/settings/oss`: masked configuration status
- `POST /api/settings/oss/test-and-activate`: validate credentials and bucket access, then atomically activate
- `GET /api/personal-assets/sync/availability`: lazy availability check
- `POST /api/personal-assets/sync/preferences`: `{"enabled": true|false}`
- `POST /api/personal-assets/sync/now`: queue synchronization with an empty body
- `POST /api/personal-assets/sync/conflict`: choose `{"resolution":"local"}` or `{"resolution":"remote"}`

`start.sh` attempts to install `alibabacloud-oss-v2` when missing. Divergent local and remote snapshots enter `conflict`; the system never chooses an overwrite automatically.

## Verification

```bash
.venv/bin/python -m pytest -q \
  tests/test_personal_asset_store.py \
  tests/test_personal_asset_service.py \
  tests/test_personal_asset_http.py \
  tests/test_personal_asset_server_wiring.py \
  tests/test_personal_asset_sync_state.py \
  tests/test_personal_asset_sync_service.py \
  tests/test_oss_settings_live_server_routes.py \
  tests/test_aliyun_oss_storage.py
node tests/check_personal_assets_ui.mjs
```
