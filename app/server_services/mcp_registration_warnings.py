"""Stable warning payloads for MCP native-client registration."""

from __future__ import annotations

from typing import Any

WORKING_DIRECTORY_NOT_PERSISTED = "mcp_client_cwd_not_persisted"


def working_directory_not_persisted(client: str) -> dict[str, Any]:
    label = str(client or "").strip().capitalize()
    return {
        "code": WORKING_DIRECTORY_NOT_PERSISTED,
        "params": {"client": label},
        "message": f"{label} CLI does not persist the configured working directory",
    }
