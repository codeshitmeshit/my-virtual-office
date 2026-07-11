"""Project execution services that do not depend on HTTP transport objects."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ServiceResult:
    status: int
    payload: dict[str, Any]


def validate_workspace(
    project_id: str,
    body: Mapping[str, Any],
    *,
    load_projects: Callable[[], dict[str, Any]],
    save_projects: Callable[[dict[str, Any]], None],
    validate_workspace_path: Callable[[Any], dict[str, Any]],
    now: Callable[[], str],
) -> ServiceResult:
    """Validate and persist a project's execution workspace configuration."""
    data = load_projects()
    project = next(
        (item for item in data.get("projects", []) if item.get("id") == project_id),
        None,
    )
    if not project:
        return ServiceResult(status=404, payload={"error": "Project not found"})

    requested_path = body.get("workspacePath") or project.get("workspacePath")
    result = validate_workspace_path(requested_path)
    if not result.get("ok"):
        project.update(
            {
                "projectExecutionEnabled": True,
                "workspacePath": requested_path,
                "workspaceStatus": result,
                "updatedAt": now(),
            }
        )
        save_projects(data)
        return ServiceResult(status=400, payload=dict(result))

    project.update(
        {
            "projectExecutionEnabled": True,
            "workspacePath": result["path"],
            "workspaceKind": result["kind"],
            "workspaceStatus": result,
            "updatedAt": now(),
        }
    )
    save_projects(data)
    return ServiceResult(status=200, payload={"ok": True, "workspace": result})
