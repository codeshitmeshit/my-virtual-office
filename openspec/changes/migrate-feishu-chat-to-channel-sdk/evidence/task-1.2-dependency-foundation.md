# Task 1.2 Dependency Foundation Evidence

Recorded: 2026-07-14 (Asia/Shanghai)

## Delivered contract

- Isolated private ESM package: `integrations/feishu-channel-worker`.
- Runtime declaration: Node.js 18 or newer.
- Direct dependency pin: `@larksuite/channel` exactly `0.4.0`.
- npm lockfile resolves `@larksuite/channel` to `0.4.0` with its published integrity hash.
- Preflight statuses are scoped to `feishu_chat`, set `affectsVoStartup` to `false`, and include an actionable recovery command.
- Stable dependency states covered: `dependencies_ready`, `missing_node_runtime`, `incompatible_node_runtime`, `missing_channel_sdk`, and `incompatible_channel_sdk`.

Startup installation and supervisor integration remain intentionally deferred to tasks 5.1 and 5.3. This task provides the isolated package and non-throwing preflight contract they will consume.

## Verification

```text
cd integrations/feishu-channel-worker
npm test

tests 5
pass 5
fail 0
```

Before dependency installation, the real CLI returned exit code 2 and the following Chat-only result:

```json
{"ok":false,"scope":"feishu_chat","affectsVoStartup":false,"enabled":false,"running":false,"transport":"channel-sdk-node","status":"missing_channel_sdk","requiredNodeMajor":18,"requiredChannelVersion":"0.4.0"}
```

After `npm ci --ignore-scripts --no-audit --no-fund`, the real CLI returned:

```json
{"ok":true,"scope":"feishu_chat","affectsVoStartup":false,"enabled":true,"running":false,"transport":"channel-sdk-node","status":"dependencies_ready","nodeVersion":"20.20.2","channelVersion":"0.4.0","requiredNodeMajor":18,"requiredChannelVersion":"0.4.0"}
```

The lock assertion confirmed:

```text
locked @larksuite/channel 0.4.0
```
