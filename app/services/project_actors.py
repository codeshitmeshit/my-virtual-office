"""Project actor references and legacy task-role compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


LOCAL_USER_ACTOR_ID = "user:local"
SUPPORTED_ACTOR_TYPES = frozenset({"agent", "user"})

AgentLookup = Callable[[str], Mapping[str, Any] | None]
AgentExclusionCheck = Callable[[str], bool]
ActorReference = dict[str, str]


@dataclass(frozen=True)
class ActorReferenceError(ValueError):
    """Stable validation error for an authored project role."""

    code: str
    role: str
    message: str
    actor_id: str = ""

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "role": self.role, "error": self.message}
        if self.actor_id:
            result["actorId"] = self.actor_id
        return result


def normalize_actor_reference(
    value: Any,
    *,
    role: str,
    required: bool = True,
) -> ActorReference | None:
    """Normalize a typed actor reference or a legacy actor-id string."""

    if value is None or value == "":
        if required:
            raise ActorReferenceError(
                "actor_required", role, f"{role} actor is required",
            )
        return None

    if isinstance(value, Mapping):
        actor_type = str(value.get("type") or "").strip().lower()
        actor_id = str(value.get("id") or "").strip()
    elif isinstance(value, str):
        actor_id = value.strip()
        actor_type = "user" if actor_id in {"user", LOCAL_USER_ACTOR_ID} else "agent"
    else:
        raise ActorReferenceError(
            "invalid_actor_reference", role, f"{role} actor must be an object or id string",
        )

    if actor_type not in SUPPORTED_ACTOR_TYPES:
        raise ActorReferenceError(
            "unsupported_actor_type", role,
            f"{role} actor type must be one of: agent, user", actor_id,
        )
    if not actor_id:
        raise ActorReferenceError(
            "actor_id_required", role, f"{role} actor id is required",
        )
    if actor_type == "user":
        if actor_id not in {"user", LOCAL_USER_ACTOR_ID}:
            raise ActorReferenceError(
                "unsupported_user_actor", role,
                f"{role} user actor must be the current Virtual Office user", actor_id,
            )
        actor_id = LOCAL_USER_ACTOR_ID
    return {"type": actor_type, "id": actor_id}


def validate_actor_reference(
    value: Any,
    *,
    role: str,
    lookup_agent: AgentLookup,
    is_excluded_agent: AgentExclusionCheck,
    required: bool = True,
    agent_only: bool = False,
) -> ActorReference | None:
    """Validate a normalized actor against the current VO Agent roster."""

    actor = normalize_actor_reference(value, role=role, required=required)
    if actor is None:
        return None
    if actor["type"] == "user":
        if agent_only:
            raise ActorReferenceError(
                "agent_actor_required", role, f"{role} actor must be a registered Agent", actor["id"],
            )
        return actor

    agent_id = actor["id"]
    if lookup_agent(agent_id) is None:
        raise ActorReferenceError(
            "agent_not_found", role, f"{role} Agent was not found", agent_id,
        )
    if is_excluded_agent(agent_id):
        raise ActorReferenceError(
            "agent_not_assignable", role, f"{role} Agent is not assignable to ordinary project work", agent_id,
        )
    return actor


def task_actor_references(task: Mapping[str, Any]) -> dict[str, ActorReference | None]:
    """Read modern actor references, falling back to legacy task role fields."""

    responsible_value = task.get("responsibleActor") if "responsibleActor" in task else task.get("assignee")
    if "executorActor" in task:
        executor_value = task.get("executorActor")
    else:
        executor_value = task.get("executorAgentId") or task.get("assignee")
    reviewer_value = task.get("reviewerActor") if "reviewerActor" in task else task.get("reviewerAgentId")
    return {
        "responsible": normalize_actor_reference(responsible_value, role="responsible", required=False),
        "executor": normalize_actor_reference(executor_value, role="executor", required=False),
        "reviewer": normalize_actor_reference(reviewer_value, role="reviewer", required=False),
    }


def validate_task_actor_references(
    task: Mapping[str, Any],
    *,
    lookup_agent: AgentLookup,
    is_excluded_agent: AgentExclusionCheck,
) -> dict[str, ActorReference | None]:
    """Validate the one-responsible/one-executor/optional-reviewer role model."""

    actors = task_actor_references(task)
    return {
        "responsible": validate_actor_reference(
            actors["responsible"], role="responsible", lookup_agent=lookup_agent,
            is_excluded_agent=is_excluded_agent,
        ),
        "executor": validate_actor_reference(
            actors["executor"], role="executor", lookup_agent=lookup_agent,
            is_excluded_agent=is_excluded_agent,
        ),
        "reviewer": validate_actor_reference(
            actors["reviewer"], role="reviewer", lookup_agent=lookup_agent,
            is_excluded_agent=is_excluded_agent, required=False, agent_only=True,
        ),
    }


def legacy_task_role_fields(
    actors: Mapping[str, ActorReference | None],
) -> dict[str, str | None]:
    """Project typed actor roles into fields consumed by legacy project code."""

    responsible = actors.get("responsible")
    executor = actors.get("executor")
    reviewer = actors.get("reviewer")
    return {
        "assignee": responsible["id"] if responsible else None,
        "executorAgentId": executor["id"] if executor and executor.get("type") == "agent" else None,
        "reviewerAgentId": reviewer["id"] if reviewer and reviewer.get("type") == "agent" else None,
    }
