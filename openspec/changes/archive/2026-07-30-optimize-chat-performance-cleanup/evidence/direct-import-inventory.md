# Direct import inventory

Task: `optimize-chat-performance-cleanup` 1.3

Command:

```bash
rg -n "server_services import agent_bridges|from server_services\\.agent_bridges|import server_services\\.agent_bridges|agent_bridges\\._handle_(codex|hermes|claude_code)_run_(start|events|stop)|_bridge_service\\(" app tests -S
```

Result:

- Production access to `server_services.agent_bridges` is through `app/server_routes/agent_bridges.py::_bridge_service()`.
- `_bridge_service()` calls `agent_bridges._hydrate()` before returning the service module.
- No production caller directly invokes a service-local Codex, Hermes, or Claude Code run start/events/stop handler.
- The remaining `server.py` references are route/service split compatibility markers in comments.
- Test references are static marker checks or the new route-hydration proof.

Conclusion:

The normal routed chat bridge path does not require a service-local in-memory run authority.
