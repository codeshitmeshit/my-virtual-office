import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services.json_array_event_store import JsonArrayEventStore


def test_event_store_reuses_cached_parse_and_bounds_writes(tmp_path, monkeypatch):
    path = tmp_path / "events.json"
    path.write_text(json.dumps([{"id": 1}]), encoding="utf-8")
    store = JsonArrayEventStore(max_events=2)

    calls = 0
    original_load = json.load

    def counted(stream):
        nonlocal calls
        calls += 1
        return original_load(stream)

    monkeypatch.setattr(json, "load", counted)
    first = store.load(str(path))
    second = store.load(str(path))
    assert first is second
    assert calls == 1

    store.save(str(path), [{"id": 1}, {"id": 2}, {"id": 3}])
    assert store.load(str(path)) == [{"id": 2}, {"id": 3}]
    assert calls == 1
    assert path.read_text(encoding="utf-8") == '[{"id":2},{"id":3}]'


def test_event_store_invalidates_when_an_external_writer_replaces_the_file(tmp_path):
    path = tmp_path / "events.json"
    path.write_text('[{"id":1}]', encoding="utf-8")
    store = JsonArrayEventStore(max_events=10)
    assert store.load(str(path)) == [{"id": 1}]

    replacement = tmp_path / "replacement.json"
    replacement.write_text('[{"id":2}]', encoding="utf-8")
    os.replace(replacement, path)

    assert store.load(str(path)) == [{"id": 2}]
