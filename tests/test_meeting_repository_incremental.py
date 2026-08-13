import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.meeting_repository import MeetingDomainRepository


def test_event_append_only_inserts_new_event_row(tmp_path, monkeypatch):
    repository = MeetingDomainRepository(tmp_path)
    repository.create_meeting(lambda data: (
        data["meetings"].update({"m1": {"id": "m1", "stage": "active_discussion", "participants": ["a1"]}}),
        data["events"].update({"m1": [{"type": "opened", "sequence": 1}]}),
    ))
    statements = []
    import services.meeting_repository as module
    original = module.connect_sqlite

    def traced(path, **kwargs):
        connection = original(path, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(module, "connect_sqlite", traced)
    repository.mutate_meeting("m1", lambda data: data["events"]["m1"].append({"type": "message", "sequence": 2}))
    inserts = [statement for statement in statements if "INSERT OR REPLACE INTO meeting_events" in statement]
    assert len(inserts) == 1
    assert not any("DELETE FROM meeting_events" in statement for statement in statements)
    assert repository.list_events("m1")[-1] == {"type": "message", "sequence": 2}


def test_mutator_failure_does_not_open_write_transaction(tmp_path, monkeypatch):
    repository = MeetingDomainRepository(tmp_path)
    repository.initialize_empty()
    before = repository.export_for_migration()
    try:
        repository.create_meeting(lambda data: (_ for _ in ()).throw(ValueError("invalid transition")))
        assert False
    except ValueError:
        pass
    assert repository.export_for_migration() == before
