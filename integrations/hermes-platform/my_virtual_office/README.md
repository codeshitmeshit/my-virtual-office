# My Virtual Office Hermes Platform Adapter

This is a Hermes Messaging Gateway platform plugin. It makes My Virtual Office a Hermes messaging destination:

`Virtual Office chat -> Hermes gateway plugin -> Hermes agent -> Virtual Office chat`

It follows Hermes' official plugin path: copy this directory to `~/.hermes/plugins/my_virtual_office/`, configure env vars, then run `hermes gateway`.

## Virtual Office Setup

Set a shared bridge token on the Virtual Office server:

```bash
VO_HERMES_PLATFORM_ENABLED=true
VO_HERMES_PLATFORM_TOKEN=replace-with-a-long-random-token
VO_HERMES_PLATFORM_AGENT_ID=hermes-gateway
```

Restart Virtual Office after changing these values. A `Hermes Gateway` agent appears in the office when the bridge is configured.

## Hermes Setup

Install the plugin:

```bash
mkdir -p ~/.hermes/plugins/my_virtual_office
cp adapter.py plugin.yaml ~/.hermes/plugins/my_virtual_office/
```

Add Hermes env vars:

```bash
MY_VIRTUAL_OFFICE_URL=http://<virtual-office-host>:8090
MY_VIRTUAL_OFFICE_TOKEN=replace-with-the-same-token
MY_VIRTUAL_OFFICE_ADAPTER_ID=hermes-gateway
MY_VIRTUAL_OFFICE_ALLOW_ALL_USERS=true
```

Then start Hermes Messaging Gateway:

```bash
hermes gateway
```

## API Surface

The adapter uses these Virtual Office endpoints:

- `GET /api/hermes-platform/poll`
- `POST /api/hermes-platform/ack`
- `POST /api/hermes-platform/reply`
- `POST /api/hermes-platform/heartbeat`

Virtual Office queues outbound messages with:

- `POST /api/hermes-platform/enqueue`

All mutating/polling endpoints require the shared token by `Authorization: Bearer <token>` or `X-Virtual-Office-Token`.
