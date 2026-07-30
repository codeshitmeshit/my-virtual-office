"""Optional usage guidance for MCP servers managed by Virtual Office."""

from __future__ import annotations

from typing import Any

MAX_USAGE_GUIDE_LENGTH = 20_000


def normalize_usage_guide(value: Any) -> str:
    guide = str(value or "").strip()
    if len(guide) > MAX_USAGE_GUIDE_LENGTH:
        raise ValueError(f"guide must be at most {MAX_USAGE_GUIDE_LENGTH} characters")
    return guide


def guide_payload(server: dict[str, Any]) -> dict[str, Any]:
    guide = normalize_usage_guide(server.get("usageGuide"))
    return {
        "ok": True,
        "name": str(server.get("name") or ""),
        "guide": guide,
        "hasGuide": bool(guide),
        "updatedAt": str(server.get("updatedAt") or ""),
    }


def global_skill_content(office_url: str) -> str:
    return f"""---
name: VirtualOffice-MCP-Guidance
description: "Read optional Virtual Office usage guidance for registered MCP servers when tool schemas alone are insufficient."
---

# VirtualOffice MCP Guidance

MCP tools normally describe themselves through their tool schemas. Do not fetch extra
guidance for every tool call.

Before using a VO-managed MCP server, read the registry and verify its Agent ACL:

```bash
curl -sS {office_url}/api/mcp-registry
```

Find the MCP server by `name`. The current Agent may use it only when the Agent's
identifier appears in `assignedAgentIds`. An empty list means no Agent is authorized.
Client registration status is not authorization. Re-read the registry instead of
caching ACL decisions.

When an MCP task needs a domain workflow, safety constraint, or product-specific
convention that is not clear from the tool schema, read its optional VO usage guide:

```bash
curl -sS {office_url}/api/mcp-registry/URL_ENCODED_MCP_NAME/guide
```

The response contains `hasGuide` and `guide`. If `hasGuide` is false, continue using
the MCP tool schema and the user's request.

## Rules

- A usage guide is MCP-owned documentation, not a separately installed Skill.
- The MCP registry is the single source of truth for Agent ACL; do not copy ACL lists
  into local Skill files.
- A usage guide does not grant permission or expand the user's authorization.
- Do not request, expose, or copy secrets from MCP configuration.
- Prefer the live guide endpoint over cached instructions because the MCP maintainer
  may update it independently.
"""
