## Why

Virtual Office agents can currently interpret cross-agent delegation as a reason to use provider-private discovery and messaging tools such as `sessions_list`, `sessions_send`, or `openclaw agents`. Those interactions bypass the office communication history and can target stale or unverified agent identities, so VO needs one enforceable, discoverable routing contract for ordinary agent-to-agent communication.

## What Changes

- Make the current VO agent communication contract the canonical runtime skill for office agents, replacing the divergent legacy built-in communication skill.
- Ensure eligible OpenClaw agents receive and can refresh the canonical communication skill when they are created or discovered.
- Require ordinary cross-agent requests to resolve current VO identities and provider kinds before using the VO communication endpoint.
- Prevent cross-agent routing from silently falling back to provider-private sessions or CLIs when the VO route is required or unavailable.
- Report OpenClaw availability from usable configuration and agent data instead of directory existence alone.
- Add regression coverage for skill distribution, roster availability, routing, history traceability, and forbidden private fallbacks.

## Capabilities

### New Capabilities

- `agent-communication-routing`: Defines canonical skill distribution, provider-aware VO routing, traceable conversation behavior, forbidden private fallbacks, and truthful OpenClaw availability reporting.

### Modified Capabilities

None.

## Impact

- Runtime skill seeding and Skills Library behavior in the VO server.
- OpenClaw agent discovery, creation, and workspace skill installation or refresh behavior.
- Agent-facing VO instructions and the `/api/agents` and `/api/agent-platform-communications/send` workflow.
- OpenClaw detection data exposed through `/vo-config` and related status surfaces.
- Unit and integration tests for discovery, workspace skills, communication routing, and history persistence.

No external API removal or breaking payload change is intended.
