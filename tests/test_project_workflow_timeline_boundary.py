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
