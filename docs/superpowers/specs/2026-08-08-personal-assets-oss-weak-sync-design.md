# Personal Assets OSS Weak Sync Design

## Outcome

Personal Assets keeps `$STATUS_DIR/personal-assets.json` as the sole authoritative write path and uses the Virtual Office generic `OssStorageService` only as a best-effort cross-region snapshot channel. A local mutation succeeds independently of OSS availability. Upload, restore, retry, and conflict resolution are observable from the Personal Assets panel and are never configured from the global Settings UI.

## Product decisions

- The integration reuses the VO-provided OSS runtime. Personal Assets never reads, edits, exports, or displays Endpoint, Bucket, Access Key ID, or Access Key Secret.
- Automatic synchronization is enabled by default for this single-user VO profile and can be toggled from the Personal Assets panel.
- Local persistence is authoritative. A failed or slow OSS operation cannot fail `/init`, profile editing, suggestion acceptance, Agent reads, or the HTTP response for a successful local mutation.
- A newly started region with an empty local profile may restore the remote snapshot automatically.
- A remote change is applied automatically only when the local profile has not changed since the last shared ETag/fingerprint baseline.
- When both local and remote changed, synchronization pauses in `conflict`. The owner explicitly chooses **Keep local** or **Use cloud**; there is no silent overwrite.
- Sensitive entries are included in the owner-controlled profile snapshot. OSS credentials and provider internals are never included. Sensitive Agent reads remain governed by HUMAN DECISIONS and are unchanged by synchronization.

## Architecture

### Persistence domains

1. **Authoritative profile** — `PersonalAssetStore` atomically writes `$STATUS_DIR/personal-assets.json` with mode `0600`.
2. **Weak-sync state** — a new focused store atomically writes `$STATUS_DIR/personal-assets-sync.json` with mode `0600`. It records only synchronization metadata: enabled flag, state, pending/synced revisions, shared ETag and semantic fingerprint, retry metadata, origin ID, and a stable error code.
3. **Remote snapshot** — `OssStorageService` writes one stable object:
   - `integration_id = "personal-assets"`
   - `object_id = "profile-snapshot.json"`
   - `content_type = "application/json"`

### Snapshot envelope

The remote JSON envelope contains `schemaVersion`, `originId`, `updatedAt`, `localRevision`, `baseEtag`, `profileFingerprint`, `payload`, and `checksum`. `payload` contains only the public profile (`entries` and `suggestions`; the local top-level revision is metadata, not part of the semantic fingerprint). Access links, usage records, idempotency receipts, OSS settings, and secrets are excluded.

The checksum covers the canonical JSON envelope without the checksum field. Restores reject malformed JSON, unsupported schemas, oversized bodies, fingerprint mismatches, and checksum mismatches before touching the local profile.

A successful restore replaces only entries and pending suggestions. It preserves the local usage audit, but clears pre-restore access links and idempotency receipts so authority granted against an older profile cannot survive a regional restore.

### Mutation flow

1. The owner or confirmed onboarding command validates and atomically writes the local profile.
2. The HTTP request returns local success immediately.
3. A mutation observer marks the current local revision `pending` in the weak-sync state and wakes a single daemon worker. Observer failures are logged with stable codes and are swallowed so they cannot alter local success.
4. The worker compares the local semantic fingerprint and remote ETag with the last shared baseline, then uploads, restores, marks synced, or records a conflict.
5. Provider failure records `failed`/`pending`, a stable error code, and an exponential retry time. It never rolls back the profile.

### Restore and conflict rules

- **Remote absent + local non-empty:** upload the local snapshot.
- **Remote absent + local empty:** remain synchronized/empty.
- **Local empty + remote present:** validate and atomically restore remote data.
- **Remote changed + local unchanged from baseline:** validate and restore remote data.
- **Local changed + remote unchanged from baseline:** upload local data.
- **Both changed or no common baseline with different content:** enter `conflict` and pause automatic writes.
- **Keep local:** queue a force-upload of the current local profile and establish a new baseline on success.
- **Use cloud:** queue a validated remote restore using the current local revision as the atomic expected revision; establish a new baseline on success.

The generic SDK has no conditional-write primitive, so conflict prevention is best-effort rather than strong consistency. This is consistent with the explicitly weak dependency.

## HTTP surface

Existing management authentication protects all routes.

- `GET /api/personal-assets` returns `{ profile, sync }`.
- `POST /api/personal-assets/sync/preferences` with `{ enabled: boolean }` updates only the local Personal Assets synchronization preference.
- `POST /api/personal-assets/sync/now` queues a background attempt and returns `202` with the current sync state.
- `POST /api/personal-assets/sync/conflict` with `{ resolution: "local" | "remote" }` records the explicit resolution, queues the worker, and returns `202`.
- `GET /api/personal-assets/sync/availability` performs one configuration-only availability check and returns only `{ status, checkedAt, code? }`. It never returns Endpoint, Bucket, Access Key ID, Access Key Secret, region, provider objects, or raw errors.

The browser never calls the OSS settings endpoints or receives OSS configuration values.

## Lazy OSS availability

OSS availability is a transient presentation concern, separate from synchronization state. A focused availability component receives the existing `OssRuntime.active_context` boundary as an injected callable. Its check has no network side effect:

- an active runtime context produces `available`;
- `OssConfigurationUnavailable` produces `unconfigured`;
- any other safe runtime failure produces `unavailable` with a stable non-secret code.

The browser does not check OSS during page startup. Each time the owner opens Personal Assets, the panel starts at `checking` and requests `GET /api/personal-assets/sync/availability` once. Closing and reopening performs a fresh check. Profile polling does not repeat the availability request, and the result is not persisted to the profile or synchronization-state files.

Availability does not probe the Bucket, perform object operations, trigger synchronization, or alter the active OSS configuration. Therefore a slow or unavailable provider cannot enter the Personal Assets read or write path. Local profile operations remain available for every result.

## UI behavior

The Personal Assets overview adds a scoped synchronization strip with:

- automatic synchronization toggle;
- state label (`synced`, `pending`, `syncing`, `failed`, `restoring`, or `conflict`);
- last successful sync time;
- **Sync now** and context-sensitive **Retry** actions;
- conflict actions **Keep local** and **Use cloud**, both requiring explicit confirmation.

The primary badge resolves availability and synchronization without conflating them:

- while the lazy check is pending, show **Checking**;
- when synchronization is active or exceptional, show `pending`, `syncing`, `restoring`, `failed`, or `conflict`;
- otherwise show **Available**, **Not configured**, or **Unavailable** from the latest lazy check;
- `idle` remains an internal synchronization state and is no longer the default owner-facing badge.

When OSS is not configured or unavailable, **Sync now** is disabled with localized explanatory copy. Automatic synchronization remains a local preference and local profile persistence remains fully functional.

The panel polls only while open and while a transition is active. Closing the panel stops browser polling but does not cancel the server worker. Errors use stable, non-secret copy and do not replace the existing local-save success notice.

## Figma acceptance

- Screen: [05 · 个人资产｜OSS 弱同步](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=347-378)
- Interaction overview: [06 · OSS 弱同步｜交互全景](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=348-441)
- Storage and submission: [07 · OSS 弱同步｜存储与提交](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=348-516)

The frames reuse the existing Personal Assets variables, components, Noto Sans SC prototype typography, and approved navigation context. The final audit found no placeholders, missing interaction numbers, font mismatches, zero-size text, or overflow.

## Verification

- Unit-test atomic sync state, snapshot validation, weak failure behavior, restore, divergence detection, and both conflict resolutions.
- Route-test authentication-preserving management responses and stable validation errors.
- UI-test rendering and actions without exposing OSS settings.
- Run the existing Personal Assets, generic OSS, static UI, and server wiring regressions.
