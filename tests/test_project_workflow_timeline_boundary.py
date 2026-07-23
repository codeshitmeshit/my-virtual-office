from __future__ import annotations

import ast
import inspect
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-project-timeline-boundary-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")

import server
from services import project_workflow_timeline


TIMELINE_MODULES = (
    "conversation_timeline.py",
    "conversation_timeline_sources.py",
    "conversation_timeline_events.py",
    "chat_history_timeline.py",
    "project_workflow_chat.py",
    "project_workflow_timeline.py",
    "codex_workflow_timeline_source.py",
    "openclaw_timeline_source.py",
)


def test_public_chat_readers_delegate_to_the_shared_timeline_owner():
    standard = inspect.getsource(server._handle_chat_history_page)
    project = inspect.getsource(server._wf_get_task_session_messages)
    assert "_CHAT_HISTORY_TIMELINE_SERVICE.merge_pages" in standard
    assert "_wf_timeline_router().read" in project
    assert "json.loads" not in project
    assert "_load_hermes_history" not in project
    assert "_load_claude_code_history" not in project
    assert "_get_codex_activity" not in project


def test_legacy_project_parsers_and_reasoning_accumulator_are_removed():
    source = (APP / "server.py").read_text(encoding="utf-8")
    assert "_codex_reasoning_events_to_chat_messages" not in source
    assert "Read messages from the task-specific workflow session JSONL only" not in source
    assert source.count("def _wf_get_task_session_messages") == 1


def test_project_timeline_router_has_no_server_dependency():
    source = inspect.getsource(project_workflow_timeline)
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "server" not in imports
    assert "app.server" not in imports


def test_all_timeline_modules_are_independent_of_legacy_entry_point():
    for filename in TIMELINE_MODULES:
        source = (APP / "services" / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "server" not in imports, filename
        assert "app.server" not in imports, filename


def test_native_parsing_and_client_authority_have_one_owner():
    service_sources = {
        filename: (APP / "services" / filename).read_text(encoding="utf-8")
        for filename in TIMELINE_MODULES
    }
    assert sum(source.count("def parse_openclaw_content") for source in service_sources.values()) == 1
    assert "def parse_openclaw_content" in service_sources["conversation_timeline_sources.py"]
    server_source = (APP / "server.py").read_text(encoding="utf-8")
    client_source = (APP / "chat.js").read_text(encoding="utf-8")
    history_source = (APP / "chat-history.js").read_text(encoding="utf-8")
    assert "_codex_reasoning_events_to_chat_messages" not in server_source
    assert "CodexReasoning." not in client_source
    assert "mergeLiveHistoryRecord" not in client_source
    assert "timelineItem || data.message || data" not in history_source


def test_legacy_project_entry_points_are_thin_delegates():
    read_source = inspect.getsource(server._wf_get_task_session_messages)
    active_source = inspect.getsource(server._wf_is_task_session_active)
    assert len(read_source.splitlines()) <= 10
    assert len(active_source.splitlines()) <= 3
    assert "_wf_timeline_router().read" in read_source
    assert "_wf_timeline_router().is_active" in active_source
