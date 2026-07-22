"""Side-effect-free checks for workspace preparation results used by authoring."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def prepared_execution_workspace_error(value: Any) -> str | None:
    """Return a safe validation error when an enabled workspace is unusable."""

    if not isinstance(value, Mapping):
        return "Workspace preparation returned an invalid result"
    if value.get("ok") is not True:
        return str(value.get("error") or "Workspace preparation failed")
    path = str(value.get("workspacePath") or "").strip()
    if not path:
        return "Workspace preparation did not return a workspace path"
    status = value.get("workspaceStatus")
    if isinstance(status, Mapping) and status.get("ok") is False:
        return str(status.get("error") or "Prepared workspace validation failed")
    return None
