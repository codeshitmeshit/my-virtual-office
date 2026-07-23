"""Project and task commands independent of HTTP transport and server globals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_execution import ServiceResult
from .project_materialization import (
    ProjectMaterializationError,
    materialize_columns,
    materialize_project_base,
    materialize_task_base,
)
from .project_execution_ordering import execution_order_map
from .project_repository import ProjectAlreadyExistsError, ProjectConflictError, ProjectNotFoundError, ProjectRepository


@dataclass(frozen=True)
class CommandOutcome:
    result: ServiceResult
    post_commit: Mapping[str, Any] | None = None


def _assignment_rejection(
    candidates: tuple[Any, ...],
    policy: Callable[[Any, str], Mapping[str, Any] | None],
    scope: str,
) -> CommandOutcome | None:
    for candidate in candidates:
        rejected = policy(candidate, scope)
        if not isinstance(rejected, Mapping):
            continue
        status = int(rejected.get("_status") or 400)
        payload = {key: value for key, value in rejected.items() if key != "_status"}
        return CommandOutcome(ServiceResult(status, payload))
    return None


def create_project(
    body: Mapping[str, Any],
    *,
    repository: ProjectRepository,
    prepare_workspace: Callable[[str, Mapping[str, Any], str], dict[str, Any]],
    system_agent_assignment_error: Callable[[Any, str], Mapping[str, Any] | None],
    archive_maintenance_default: Callable[[Mapping[str, Any]], bool],
    log_activity: Callable[..., None],
    new_id: Callable[[], str],
    now: Callable[[], str],
) -> CommandOutcome:
    title = str(body.get("title") or "").strip()
    if not title:
        return CommandOutcome(ServiceResult(400, {"error": "Project title is required"}))
    if rejected := _assignment_rejection(
        tuple(body.get(field) for field in ("defaultExecutorAgentId", "defaultReviewerAgentId")),
        system_agent_assignment_error,
        "project_defaults",
    ):
        return rejected
    created_by = str(body.get("createdBy") or body.get("author") or "user").strip()
    timestamp = now()
    workspace = prepare_workspace(title, body, timestamp)
    if not workspace.get("ok"):
        return CommandOutcome(ServiceResult(int(workspace.get("_status") or 400), {k: v for k, v in workspace.items() if k != "_status"}))
    maintenance_enabled = bool(body["archiveMaintenanceEnabled"]) if "archiveMaintenanceEnabled" in body else archive_maintenance_default({"status": body.get("status", "active")})
    columns, _column_map = materialize_columns(body.get("columns"), new_id=new_id)
    project = materialize_project_base(
        {
            **body,
            "title": title,
            "createdBy": created_by,
            "executionPolicy": {"maxActiveTasks": 1},
        },
        columns=columns,
        tasks=[],
        workspace=workspace,
        new_id=new_id,
        now=now,
        timestamp=timestamp,
        archive_maintenance_enabled=maintenance_enabled,
        archive_maintenance_explicit="archiveMaintenanceEnabled" in body,
        archive_maintenance_updated_by=created_by,
    )
    log_activity(project, "project_created", created_by, f"Created project '{title}'")
    try:
        repository.create(project)
    except ProjectAlreadyExistsError:
        return CommandOutcome(ServiceResult(409, {"error": "Project already exists"}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "project": project}))


def create_task(project_id: str, body: Mapping[str, Any], *, repository: ProjectRepository, system_agent_assignment_error: Callable[[Any, str], Mapping[str, Any] | None], log_activity: Callable[..., None], new_id: Callable[[], str], now: Callable[[], str]) -> CommandOutcome:
    title = str(body.get("title") or "").strip()
    if not title:
        return CommandOutcome(ServiceResult(400, {"error": "Task title is required"}))
    if rejected := _assignment_rejection(
        tuple(body.get(field) for field in ("assignee", "executorAgentId", "reviewerAgentId")),
        system_agent_assignment_error,
        "task",
    ):
        return rejected
    created = {}
    def mutate(project):
        timestamp = now()
        task = materialize_task_base(
            {
                "title": title,
                "description": body.get("description", ""),
                "columnId": body.get("columnId"),
                "priority": body.get("priority", "medium"),
                "assignee": body.get("assignee"),
                "assigneeBranch": body.get("assigneeBranch"),
                "executorAgentId": body.get("executorAgentId"),
                "reviewerAgentId": body.get("reviewerAgentId"),
                "requiresUserAcceptance": body.get("requiresUserAcceptance", False),
                "allowReviewerlessExecution": body.get("allowReviewerlessExecution", False),
                "scheduledRepeatEnabled": body.get("scheduledRepeatEnabled", False),
                "dueDate": body.get("dueDate"),
                "tags": body.get("tags", []),
                "checklist": body.get("checklist", []),
                "meetingActionItems": body.get("meetingActionItems", []),
                "meetingDecisionHistory": body.get("meetingDecisionHistory", []),
                "meetingDiscussionPoints": body.get("meetingDiscussionPoints", []),
                "meetingRecords": body.get("meetingRecords", []),
                "source": body.get("source"),
            },
            columns=project.get("columns") or [],
            existing_tasks=project.get("tasks") or [],
            task_id=new_id(),
            timestamp=timestamp,
            new_id=new_id,
            now=now,
        )
        project.setdefault("tasks", []).append(task)
        project["updatedAt"] = timestamp
        by = body.get("by", "user")
        log_activity(project, "task_created", by, f"Created task '{title}'", task["id"])
        created.update({"task": task, "columnTitle": next((column["title"] for column in project.get("columns", []) if column["id"] == task["columnId"]), "backlog"), "by": by})
    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    except ProjectMaterializationError as exc:
        return CommandOutcome(ServiceResult(400, {"error": str(exc)}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "task": created["task"]}), created)


def add_task_comment(project_id: str, task_id: str, body: Mapping[str, Any], *, repository: ProjectRepository, log_activity: Callable[..., None], new_id: Callable[[], str], now: Callable[[], str]) -> CommandOutcome:
    text = str(body.get("text") or "").strip()
    if not text:
        return CommandOutcome(ServiceResult(400, {"error": "Comment text is required"}))
    outcome = {}
    def mutate(project):
        task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), None)
        if task is None:
            raise LookupError(task_id)
        author = str(body.get("author") or "user").strip()
        comment = {"id": new_id(), "author": author, "text": text, "createdAt": now()}
        task.setdefault("comments", []).append(comment)
        task["updatedAt"] = now(); project["updatedAt"] = now()
        log_activity(project, "task_commented", author, f"Commented on '{task['title']}'", task_id)
        outcome.update({"comment": comment, "task": task, "author": author, "columnTitle": next((c["title"] for c in project.get("columns", []) if c["id"] == task.get("columnId")), "unknown")})
    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    except LookupError:
        return CommandOutcome(ServiceResult(404, {"error": "Task not found"}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "comment": outcome["comment"]}), outcome)


def update_columns(project_id: str, body: Mapping[str, Any], *, repository: ProjectRepository, log_activity: Callable[..., None], new_id: Callable[[], str], now: Callable[[], str]) -> CommandOutcome:
    columns = body.get("columns")
    if not isinstance(columns, list):
        return CommandOutcome(ServiceResult(400, {"error": "columns must be a list"}))
    columns = [dict(column) for column in columns]
    for index, column in enumerate(columns):
        column.setdefault("id", new_id()); column["order"] = index
    try:
        repository.update(project_id, lambda project: (project.update({"columns": columns, "updatedAt": now()}), log_activity(project, "columns_updated", body.get("by", "user"), "Columns updated")))
    except ProjectNotFoundError:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "columns": columns}))


def delete_task(project_id: str, task_id: str, *, repository: ProjectRepository, now: Callable[[], str]) -> CommandOutcome:
    found = {"value": False}
    def mutate(project):
        tasks = project.get("tasks", []); remaining = [task for task in tasks if task.get("id") != task_id]
        found["value"] = len(remaining) != len(tasks)
        if found["value"]:
            project["tasks"] = remaining; project["updatedAt"] = now()
    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    if not found["value"]:
        return CommandOutcome(ServiceResult(404, {"error": "Task not found"}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "id": task_id}))


def delete_project(project_id: str, *, delete_workspace: bool, repository: ProjectRepository, remove_workspace: Callable[[str], None]) -> CommandOutcome:
    project = repository.get(project_id)
    if project is None:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    workspace_path = project.get("workspacePath"); managed_by = project.get("workspaceManagedBy"); workspace_error = None
    if delete_workspace and managed_by == "system" and workspace_path:
        try:
            remove_workspace(workspace_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            workspace_error = str(exc)
    elif delete_workspace and managed_by != "system":
        workspace_error = "Workspace was not automatically created by this project"
    if not repository.delete(project_id):
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    payload = {"ok": True, "id": project_id, "workspaceDeleted": bool(delete_workspace and managed_by == "system" and not workspace_error)}
    if workspace_error: payload["workspaceDeleteError"] = workspace_error
    return CommandOutcome(ServiceResult(200, payload))


def update_project(
    project_id: str, body: Mapping[str, Any], *, repository: ProjectRepository,
    system_agent_assignment_error: Callable[[Any, str], Mapping[str, Any] | None], execution_enabled: Callable[[dict[str, Any]], bool],
    validate_workspace: Callable[[Any], dict[str, Any]], log_activity: Callable[..., None], now: Callable[[], str],
) -> CommandOutcome:
    if rejected := _assignment_rejection(
        tuple(body.get(field) for field in ("defaultExecutorAgentId", "defaultReviewerAgentId")),
        system_agent_assignment_error,
        "project_defaults",
    ):
        return rejected
    mutable_body = dict(body)
    try:
        current_project = repository.get(project_id)
    except ProjectNotFoundError:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    if current_project is None:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    validated_workspace = None
    workspace_basis = current_project.get("workspacePath")
    if mutable_body.get("projectExecutionEnabled") or (execution_enabled(current_project) and "workspacePath" in mutable_body):
        workspace_basis = mutable_body.get("workspacePath") or current_project.get("workspacePath")
        validated_workspace = validate_workspace(workspace_basis)
        if not validated_workspace.get("ok"):
            return CommandOutcome(ServiceResult(400, {key: value for key, value in validated_workspace.items() if key != "_status"}))
        mutable_body.update({"projectExecutionEnabled": True, "workspacePath": validated_workspace.get("path"), "workspaceKind": validated_workspace.get("kind"), "workspaceStatus": validated_workspace})
    outcome = {}
    def mutate(project):
        if validated_workspace is not None and "workspacePath" not in body and project.get("workspacePath") != workspace_basis:
            raise ProjectConflictError("Workspace changed during validation")
        old_status = project.get("status"); by = mutable_body.get("by", "user")
        fields = ["title", "description", "status", "priority", "dueDate", "tags", "branch", "longTermProject", "highPriorityAiMeetingAutoApprove", "projectExecutionEnabled", "workspacePath", "workspaceKind", "workspaceStatus", "defaultExecutorAgentId", "defaultReviewerAgentId", "projectExecutionStartMode", "executionPolicy", "scheduledCronPaused", "archiveMaintenanceEnabled", "archiveMaintenance"]
        for field in fields:
            if field in mutable_body:
                old = project.get(field); project[field] = mutable_body[field]
                if old != mutable_body[field]:
                    log_activity(project, "project_updated", by, f"Changed {field}: {old} → {mutable_body[field]}")
        project["updatedAt"] = now()
        outcome.update({"project": project, "oldStatus": old_status, "statusChanged": "status" in mutable_body and mutable_body.get("status") != old_status})
    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError:
        return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    except ProjectConflictError:
        return CommandOutcome(ServiceResult(409, {"error": "Project changed during workspace validation", "code": "project_update_conflict"}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "project": outcome["project"]}), outcome)


def update_task(
    project_id: str, task_id: str, body: Mapping[str, Any], *, repository: ProjectRepository,
    system_agent_assignment_error: Callable[[Any, str], Mapping[str, Any] | None], execution_enabled: Callable[[dict[str, Any]], bool],
    column_locked: Callable[[dict[str, Any]], bool], checklist_complete: Callable[[dict[str, Any]], bool],
    can_complete_after_checklist: Callable[[dict[str, Any]], bool], mark_done: Callable[..., dict[str, Any]],
    log_activity: Callable[..., None], now: Callable[[], str], is_on_time: Callable[[Any], bool], score_values: Mapping[str, int],
) -> CommandOutcome:
    if rejected := _assignment_rejection(
        tuple(body.get(field) for field in ("assignee", "executorAgentId", "reviewerAgentId")),
        system_agent_assignment_error,
        "task",
    ):
        return rejected
    mutable_body = dict(body); post = {}
    def mutate(project):
        task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), None)
        if task is None: raise LookupError(task_id)
        if execution_enabled(project) and "assignee" in mutable_body and "executorAgentId" not in mutable_body and mutable_body.get("assignee") and not task.get("executorAgentId"):
            mutable_body["executorAgentId"] = mutable_body.get("assignee")
        by = mutable_body.get("by", "user"); timestamp = now(); was_completed = bool(task.get("completedAt")); checklist_was_complete = checklist_complete(task) if execution_enabled(project) else False
        done_columns = {column["id"] for column in project.get("columns", []) if column.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")}
        if execution_enabled(project) and "columnId" in mutable_body:
            if mutable_body.get("columnId") != task.get("columnId") and column_locked(task):
                raise PermissionError("column_locked")
            if mutable_body.get("columnId") in done_columns and task.get("executionState") != "done":
                raise PermissionError("acceptance_required")
        score = None
        if "columnId" in mutable_body and mutable_body["columnId"] != task.get("columnId"):
            old_column = next((c["title"] for c in project.get("columns", []) if c["id"] == task.get("columnId")), task.get("columnId")); new_column = next((c["title"] for c in project.get("columns", []) if c["id"] == mutable_body["columnId"]), mutable_body["columnId"])
            if mutable_body["columnId"] in done_columns and not task.get("completedAt"):
                task["completedAt"] = timestamp; assignee = task.get("assignee") or mutable_body.get("assignee")
                if assignee:
                    points = score_values["task_completed"] + score_values.get(task.get("priority", "medium"), 0)
                    if task.get("dueDate") and is_on_time(task.get("dueDate")): points += score_values["on_time"]
                    points += sum(1 for item in task.get("checklist", []) if item.get("done")) * score_values["checklist"]
                    score = {"assignee": assignee, "points": points, "reason": f"Completed: {task.get('title','')}"}
            elif mutable_body["columnId"] not in done_columns and task.get("completedAt"):
                task["completedAt"] = None
            log_activity(project, "task_moved", by, f"Moved '{task['title']}' from {old_column} to {new_column}", task_id)
        if "priority" in mutable_body and mutable_body["priority"] != task.get("priority"): log_activity(project, "task_priority_changed", by, f"Priority changed: {task.get('priority')} → {mutable_body['priority']}", task_id)
        if "assignee" in mutable_body and mutable_body["assignee"] != task.get("assignee"): log_activity(project, "task_assigned", by, f"Assigned to {mutable_body['assignee']}", task_id)
        if "executionOrder" in mutable_body:
            try:
                execution_order = int(mutable_body.get("executionOrder"))
            except (TypeError, ValueError):
                raise ValueError("invalid_execution_order")
            if execution_order <= 0:
                raise ValueError("invalid_execution_order")
            duplicate = None
            effective_orders = execution_order_map(project)
            for item in project.get("tasks", []):
                if item.get("id") == task_id:
                    continue
                other_execution_order = effective_orders.get(item.get("id"))
                if other_execution_order == execution_order:
                    duplicate = item
                    break
            if duplicate:
                raise ValueError("duplicate_execution_order")
            mutable_body["executionOrder"] = execution_order
        fields = ["title", "description", "columnId", "order", "executionOrder", "priority", "assignee", "assigneeBranch", "executorAgentId", "reviewerAgentId", "dueDate", "tags", "checklist", "meetingActionItems", "meetingDecisionHistory", "meetingDiscussionPoints", "meetingRecords", "completedAt", "requiresUserAcceptance", "allowReviewerlessExecution", "scheduledRepeatEnabled"]
        changed_fields = []
        for field in fields:
            if field in mutable_body:
                if task.get(field) != mutable_body[field]: changed_fields.append(field)
                task[field] = mutable_body[field]
        continue_flow = False
        if execution_enabled(project) and "checklist" in changed_fields and not checklist_was_complete and checklist_complete(task) and can_complete_after_checklist(task):
            review = task.get("reviewResult") if isinstance(task.get("reviewResult"), dict) else {}; done = mark_done(project, task, by, "Acceptance checklist completed after reviewer pass.", review.get("attemptId"))
            if done.get("ok"):
                continue_flow = project.get("projectExecutionStartMode") == "continuous"; project.update({"workflowActive": False, "workflowPhase": "done", "activeTaskId": None, "activeAgent": None, "projectExecutionFlowActive": continue_flow, "projectExecutionFlowStopReason": None if continue_flow else "checklist_completed"}); log_activity(project, "project_execution_checklist_completed", by, f"Completed Project Execution task '{task.get('title', '')}' after checklist completion.", task_id)
        task["updatedAt"] = timestamp; project["updatedAt"] = timestamp
        post.update({"task": task, "changedFields": changed_fields, "by": by, "score": score, "continueFlow": continue_flow, "wasCompleted": was_completed, "project": project})
    try:
        repository.update(project_id, mutate)
    except ProjectNotFoundError: return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    except LookupError: return CommandOutcome(ServiceResult(404, {"error": "Task not found"}))
    except PermissionError as exc:
        if str(exc) == "column_locked": return CommandOutcome(ServiceResult(409, {"error": "Project Execution is controlling this task column; wait for the state machine transition or stop/reset execution before moving it manually.", "code": "project_execution_column_locked"}))
        return CommandOutcome(ServiceResult(409, {"error": "Project Execution tasks require final user acceptance before Done"}))
    except ValueError as exc:
        if str(exc) == "duplicate_execution_order":
            return CommandOutcome(ServiceResult(409, {"error": "Execution order is already used by another task", "code": "duplicate_execution_order"}))
        return CommandOutcome(ServiceResult(400, {"error": "executionOrder must be a positive integer", "code": "invalid_execution_order"}))
    return CommandOutcome(ServiceResult(200, {"ok": True, "task": post["task"]}), post)


def reorder_tasks(project_id: str, body: Mapping[str, Any], *, repository: ProjectRepository, system_agent_assignment_error: Callable[[Any, str], Mapping[str, Any] | None], execution_enabled: Callable[[dict[str, Any]], bool], column_locked: Callable[[dict[str, Any]], bool], now: Callable[[], str]) -> CommandOutcome:
    updates = body.get("updates", body.get("tasks", []))
    if rejected := _assignment_rejection(
        tuple(item.get(field) for item in updates for field in ("assignee", "executorAgentId", "reviewerAgentId")),
        system_agent_assignment_error,
        "task",
    ):
        return rejected
    post = {"completedTasks": []}
    def mutate(project):
        task_map = {task["id"]: task for task in project.get("tasks", [])}; done_columns = {column["id"] for column in project.get("columns", []) if column.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")}; timestamp = now()
        for update in updates:
            task = task_map.get(update.get("id"))
            if task is None: continue
            new_column = update.get("columnId")
            if execution_enabled(project) and new_column and new_column != task.get("columnId") and column_locked(task): raise PermissionError("column_locked")
            if execution_enabled(project) and new_column in done_columns and task.get("executionState") != "done": raise PermissionError("acceptance_required")
            if new_column and new_column != task.get("columnId"):
                if new_column in done_columns and not task.get("completedAt"): task["completedAt"] = timestamp; post["completedTasks"].append(task)
                elif new_column not in done_columns and task.get("completedAt"): task["completedAt"] = None
                task["columnId"] = new_column
            if "order" in update: task["order"] = update["order"]
            task["updatedAt"] = timestamp
        project["updatedAt"] = timestamp
    try: repository.update(project_id, mutate)
    except ProjectNotFoundError: return CommandOutcome(ServiceResult(404, {"error": "Project not found"}))
    except PermissionError as exc:
        if str(exc) == "column_locked": return CommandOutcome(ServiceResult(409, {"error": "Project Execution is controlling this task column; wait for the state machine transition or stop/reset execution before moving it manually.", "code": "project_execution_column_locked"}))
        return CommandOutcome(ServiceResult(409, {"error": "Project Execution tasks require final user acceptance before Done"}))
    return CommandOutcome(ServiceResult(200, {"ok": True}), post)
