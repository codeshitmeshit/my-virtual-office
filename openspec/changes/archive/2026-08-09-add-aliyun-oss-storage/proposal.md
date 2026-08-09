## Why

VO does not yet provide a reusable remote object-storage capability, so future features that need to preserve generated files, attachments, or other materials would otherwise need to invent their own persistence and configuration paths. A shared Alibaba Cloud OSS capability establishes one secure, low-friction storage boundary that future VO modules can adopt without exposing provider credentials through environment variables.

## What Changes

- Add a backend-only object-storage capability backed by Alibaba Cloud OSS for saving, explicitly restoring, overwriting, deleting, checking, listing, and inspecting stored materials.
- Keep restoration explicit: a future user action may cause a business backend to request an object, but this change does not add automatic or background restoration.
- Support provider-scale objects without imposing a small application-level file limit or requiring callers to load an entire large object into memory.
- Isolate object keys by calling integration while leaving end-user ownership and authorization decisions to each future business integration.
- Extend the existing settings experience with an OSS configuration section for endpoint, bucket, and credentials; derive the SDK-required region internally from the endpoint instead of exposing a separate region setting.
- Persist OSS configuration through the application's settings store rather than environment variables; never return saved credential secrets to the browser or logs.
- Treat the absence of an active OSS configuration as a normal empty settings state rather than an operation failure.
- Require an explicit successful bucket-access test before a saved configuration can become active.
- Add automated behavior and failure-path verification without migrating or integrating an existing VO material workflow in this change.

### Non-goals

- A material browser, download page, sharing flow, public or signed URLs, content search, version history, or recycle bin.
- Automatic restoration, scheduled restoration, or restoration of complete VO runtime state.
- End-user authorization policy, migration of existing materials, or integration with the active personal-assets change.
- Creating, deleting, or administering Alibaba Cloud buckets from VO.
- Multi-cloud support or support for object-storage providers other than Alibaba Cloud OSS.
- Environment-variable fallback for OSS configuration.
- OSS acceleration endpoints or custom CNAME endpoints whose region cannot be derived deterministically.

## Capabilities

### New Capabilities

- `vo-object-storage`: Backend-only Alibaba Cloud OSS operations, caller isolation, explicit restoration, large-object behavior, metadata, overwrite/delete semantics, and stable failure behavior.
- `vo-oss-settings`: Existing-settings-page configuration, secret-safe persistence, bucket access testing, activation rules, and runtime use of the active configuration.

### Modified Capabilities

None.

## Impact

- The existing VO settings surface and its backend settings transport will gain OSS-specific endpoint, bucket, credential, and connection-test behavior; region remains an internal derived client value.
- A focused storage service boundary and Alibaba Cloud OSS client dependency will be introduced for future VO business modules.
- Application-owned persistent settings will contain the active OSS connection configuration; secret values must remain write-only at the browser/API boundary.
- Automated tests will cover storage operations, caller isolation, large-object streaming behavior, configuration activation, provider failures, and secret redaction.
