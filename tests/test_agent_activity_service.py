import threading
from dataclasses import dataclass

from app.services import agent_activity_service
from app.services.agent_event_repository import AgentEventRepository


@dataclass
class Settings:
    enabled: bool = False


class FastPath:
    settings = Settings()

    def live_events(self, *args, **kwargs):
        return []


def normalize_approval(provider, agent_id, conversation_id, record):
    return {"provider": provider, "interactionId": record.get("interactionId"), "status": "pending"}


def test_append_sanitizes_sequences_and_queries_without_server(tmp_path):
    repository = AgentEventRepository(tmp_path)
    lock = threading.Lock()
    record = agent_activity_service.append(repository, lock, "a1", "c1", {
        "id": "e1", "sequence": 8, "type": "turn", "status": "completed",
        "authorization": "Bearer secret", "text": "Bearer abc.def",
    })
    assert record["providerSequence"] == 8 and record["sequence"] == 1
    assert record["authorization"] == "[REDACTED]"
    assert record["text"] == "Bearer [REDACTED]"
    assert agent_activity_service.list_activity(repository, lock, FastPath(), "a1", "c1") == [record]


def test_active_projection_and_resolution_are_transport_independent():
    lock = threading.Lock()
    active = {("a1", "c1"): {"conversationId": "c1", "threadId": "thr", "status": "running"}}
    pending = {"type": "interaction", "status": "pending", "interactionId": "i1", "threadId": "thr", "ts": 1}
    agent_activity_service.update_active_from_record(
        active, lock, "a1", "c1", pending, normalize_approval=normalize_approval,
    )
    assert active[("a1", "c1")]["status"] == "pending"
    assert agent_activity_service.mark_approval_resolving(active, lock, "a1", "c1", "i1") is True
    assert active[("a1", "c1")]["status"] == "resolving"
    terminal = {"type": "turn", "status": "completed", "threadId": "thr", "ts": 2}
    agent_activity_service.update_active_from_record(
        active, lock, "a1", "c1", terminal, normalize_approval=normalize_approval,
    )
    assert active[("a1", "c1")]["pending"] is None
    assert active[("a1", "c1")]["status"] == "completed"


def test_service_has_no_legacy_server_dependency():
    source = open(agent_activity_service.__file__, encoding="utf-8").read()
    assert "import server" not in source
    assert "sys.modules" not in source
