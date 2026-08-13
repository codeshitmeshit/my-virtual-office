import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.agent_event_repository import AgentEventRepository


def event(sequence, *, agent="a1", conversation="c1"):
    return {
        "id": f"e{sequence}", "agentId": agent, "conversationId": conversation,
        "sequence": sequence, "providerSequence": sequence, "type": "turn",
        "status": "running", "ts": sequence,
    }


def test_append_uses_one_insert_and_scope_query(tmp_path):
    repository = AgentEventRepository(tmp_path, max_events=5)
    repository.append(event(1))
    statements = []
    import services.agent_event_repository as module
    original_connect = module.connect_sqlite

    def traced(path, **kwargs):
        connection = original_connect(path, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    module.connect_sqlite = traced
    repository.append(event(2))
    assert sum("INSERT INTO agent_events" in statement for statement in statements) == 1
    assert not any("DELETE FROM agent_events" in statement and "ordinal" not in statement for statement in statements)
    assert [item["sequence"] for item in repository.list_scope("a1", "c1", after=1)] == [2]
def test_bounded_store_and_legacy_cutover_gate(tmp_path):
    repository = AgentEventRepository(tmp_path, max_events=2)
    repository.append(event(1))
    repository.append(event(2))
    repository.append(event(3))
    assert [item["sequence"] for item in repository.load_all()] == [2, 3]
    legacy_dir = tmp_path / "legacy"; legacy_dir.mkdir()
    (legacy_dir / "codex-activity.json").write_text(json.dumps([event(1)]))
    try:
        AgentEventRepository(legacy_dir).load_all()
        assert False
    except RuntimeError as error:
        assert "migration is required" in str(error)
