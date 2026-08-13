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


def test_append_compat_uses_one_insert_and_scope_query(tmp_path):
    repository = AgentEventRepository(tmp_path, max_events=5)
    repository.save_compat([event(1)])
    loaded = repository.load_all()
    statements = []
    original = sqlite3.connect

    def traced(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    import services.sqlite_runtime as runtime
    import services.agent_event_repository as module
    module.connect_sqlite = lambda path, **kwargs: _connect_like_runtime(runtime, traced, path, **kwargs)
    loaded.append(event(2))
    repository.save_compat(loaded)
    assert sum("INSERT INTO agent_events" in statement for statement in statements) == 1
    assert not any("DELETE FROM agent_events" in statement and "ordinal" not in statement for statement in statements)
    assert [item["sequence"] for item in repository.list_scope("a1", "c1", after=1)] == [2]


def _connect_like_runtime(runtime, connect, path, **kwargs):
    original = runtime.sqlite3.connect
    runtime.sqlite3.connect = connect
    try:
        return runtime.connect_sqlite(path, **kwargs)
    finally:
        runtime.sqlite3.connect = original


def test_bounded_store_and_legacy_cutover_gate(tmp_path):
    repository = AgentEventRepository(tmp_path, max_events=2)
    repository.save_compat([event(1), event(2), event(3)])
    assert [item["sequence"] for item in repository.load_all()] == [2, 3]
    legacy_dir = tmp_path / "legacy"; legacy_dir.mkdir()
    (legacy_dir / "codex-activity.json").write_text(json.dumps([event(1)]))
    try:
        AgentEventRepository(legacy_dir).load_all()
        assert False
    except RuntimeError as error:
        assert "migration is required" in str(error)

