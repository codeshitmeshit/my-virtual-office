import threading
import tempfile

from app.services.executable_meeting_commands import ExecutableMeetingCommands, ExecutableMeetingPorts
from app.services.meeting_repository import MeetingDomainRepository


def build_ports():
    directory = tempfile.mkdtemp(prefix="typed-meeting-command-")
    repository = MeetingDomainRepository(directory)

    def append_event(data, meeting, event_type, **kwargs):
        events = data.setdefault("events", {}).setdefault(meeting["id"], [])
        event = {"sequence": len(events) + 1, "type": event_type, **kwargs}
        events.append(event)
        return event

    ports = ExecutableMeetingPorts(
        lock=threading.RLock(), repository=repository,
        clean_participants=lambda raw: list(dict.fromkeys(raw or [])),
        participant_error=lambda participant: None,
        participant_error_response=lambda participants: {"error": "blocked", "participants": participants, "_status": 400},
        project_ref=lambda project_id: {"ok": True, "projectId": project_id or "", "projectTitle": "Project"},
        now=lambda: "2026-08-13T00:00:00Z", new_id=lambda: "m1", decision_window=lambda raw: 300,
        resolution_policy=lambda raw: "user_decision", context_mode=lambda raw: "incremental",
        context_budget=lambda raw: {"maxPromptChars": 12000, "maxInitialContextChars": 4000, "maxSummaryChars": 3000, "maxRecentEvents": 6},
        preparing_timeout=lambda: 300, rebuild_occupancy=lambda *args: [], build_conflicts=lambda *args: [],
        append_event=append_event, complete_live_advisories=lambda meeting_id: None,
        ensure_action_items=lambda *args: None, release_timed_out=lambda data: [],
        project_history=lambda meeting, events: {"active": False}, project_active=lambda meeting, events: {"active": True},
        busy_context=lambda *args: {}, advisory=lambda *args: {}, original_work_snapshot=lambda *args: {},
        has_open_conflicts=lambda *args: False, mark_preparing=lambda *args: None,
        continue_decision=lambda *args: None, resume_original_work=lambda *args: None,
        award_points=lambda *args: None, apply_project_result=lambda meeting: None,
    )
    return ports, repository


def test_create_detail_and_event_filter_without_server():
    ports, repository = build_ports()
    commands = ExecutableMeetingCommands(ports)
    created = commands.create({"topic": "Decision", "participants": ["a1", "a2"]})
    assert created["ok"] is True and created["meeting"]["id"] == "m1"
    detail = commands.detail("m1")
    assert detail["ok"] is True and detail["meeting"]["active"] is True
    assert commands.events("m1", "after=0")["events"]
    assert commands.events("m1", "after=999")["events"] == []


def test_validation_and_mutation_commands_are_owned_by_service():
    ports, repository = build_ports()
    commands = ExecutableMeetingCommands(ports)
    assert commands.create({"participants": ["a1", "a2"]})["_status"] == 400
    assert commands.create({"topic": "x", "participants": ["a1"]})["_status"] == 400
    commands.create({"topic": "x", "participants": ["a1", "a2"]})
    result = commands.intervention("m1", {"text": "context", "actorId": "user"})
    assert result["ok"] is True
    assert any(event["type"] == "user_intervention" for event in repository.list_events("m1"))


def test_service_has_no_server_global_hydration():
    import app.services.executable_meeting_commands as module
    source = open(module.__file__, encoding="utf-8").read()
    assert "import server" not in source
    assert "sys.modules" not in source
    assert "_hydrate" not in source
