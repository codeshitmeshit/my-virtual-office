# Hermes Messaging Gateway Platform Adapter

Status: first implementation

## What This Is

This integration makes My Virtual Office a Hermes Messaging Gateway platform.

The flow is:

`Virtual Office user -> Hermes Gateway plugin -> Hermes agent -> Virtual Office reply`

This is separate from the Hermes API Server and Desktop/Remote Backend integrations. API Server and Desktop Backend are Virtual Office acting as a Hermes client. The platform adapter is Hermes gateway acting as a client of Virtual Office.

## Official Hermes Surface

Hermes documents third-party platform adapters through the plugin path:

- plugin directory under `~/.hermes/plugins/<name>/`
- `plugin.yaml`
- `adapter.py`
- adapter subclasses `BasePlatformAdapter`
- `register(ctx)` calls `ctx.register_platform()`
- inbound messages are delivered as `MessageEvent` and dispatched with `self.handle_message(event)`

The Virtual Office plugin lives in:

`integrations/hermes-platform/my_virtual_office/`

## Virtual Office Configuration

Set these on the Virtual Office server:

```bash
VO_HERMES_PLATFORM_ENABLED=true
VO_HERMES_PLATFORM_TOKEN=<shared-token>
VO_HERMES_PLATFORM_AGENT_ID=hermes-gateway
```

When configured, Virtual Office adds a synthetic `Hermes Gateway` office agent with provider type `gateway-platform`.

## Hermes Configuration

Copy the plugin into Hermes:

```bash
mkdir -p ~/.hermes/plugins/my_virtual_office
cp integrations/hermes-platform/my_virtual_office/adapter.py ~/.hermes/plugins/my_virtual_office/
cp integrations/hermes-platform/my_virtual_office/plugin.yaml ~/.hermes/plugins/my_virtual_office/
```

Set Hermes env vars:

```bash
MY_VIRTUAL_OFFICE_URL=http://<virtual-office-host>:8090
MY_VIRTUAL_OFFICE_TOKEN=<same-shared-token>
MY_VIRTUAL_OFFICE_ADAPTER_ID=hermes-gateway
MY_VIRTUAL_OFFICE_ALLOW_ALL_USERS=true
```

Then run:

```bash
hermes gateway
```

## Bridge Endpoints

Virtual Office exposes:

- `GET /api/hermes-platform/status`
- `GET /api/hermes-platform/poll`
- `POST /api/hermes-platform/enqueue`
- `POST /api/hermes-platform/ack`
- `POST /api/hermes-platform/reply`
- `POST /api/hermes-platform/heartbeat`

Polling and mutating endpoints require the shared token in `Authorization: Bearer <token>` or `X-Virtual-Office-Token`.

## Queue Semantics

Messages are stored under:

`VO_STATUS_DIR/hermes-platform-queue.json`

The poll endpoint leases queued messages. The plugin acknowledges a lease after it hands the message to Hermes with `handle_message()`. Hermes replies are matched back by `chatId` or message ID and logged through the existing AgentPlatform-to-AgentPlatform communication log so chat bubbles can show the conversation.

## Mode Names

Use these names in UI/docs:

- `Hermes Desktop / Remote Backend` for `hermes serve` and `/api/ws`
- `Hermes API Server` for `/v1` endpoints
- `Hermes Messaging Gateway Platform` for this plugin mode
