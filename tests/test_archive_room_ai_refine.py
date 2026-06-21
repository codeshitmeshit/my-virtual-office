#!/usr/bin/env python3
"""Focused coverage for Archive Room AI refinement delegation."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-ai-refine-import-")
IMPORT_OC_HOME = tempfile.mkdtemp(prefix="vo-archive-ai-refine-openclaw-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_OPENCLAW_PATH"] = IMPORT_OC_HOME

import server
from project_store import MarkdownProjectStore


def setup_store():
    status_dir = tempfile.TemporaryDirectory()
    oc_home = tempfile.TemporaryDirectory()
    old = (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.ARCHIVE_ROOM_DIR,
        server.ARCHIVE_ROOM_PROJECTS_DIR,
        server.WORKSPACE_BASE,
        server._discovered_roster,
        server._discovered_at,
        server._gateway_rpc_call,
        server._wf_call_agent,
    )
    server.STATUS_DIR = status_dir.name
    server.PROJECT_STORE = MarkdownProjectStore(status_dir.name)
    server.ARCHIVE_ROOM_DIR = os.path.join(status_dir.name, "archive-room")
    server.ARCHIVE_ROOM_PROJECTS_DIR = os.path.join(server.ARCHIVE_ROOM_DIR, "projects")
    server.WORKSPACE_BASE = oc_home.name
    server._discovered_roster = []
    server._discovered_at = 0
    return status_dir, oc_home, old


def teardown_store(status_dir, oc_home, old):
    (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.ARCHIVE_ROOM_DIR,
        server.ARCHIVE_ROOM_PROJECTS_DIR,
        server.WORKSPACE_BASE,
        server._discovered_roster,
        server._discovered_at,
        server._gateway_rpc_call,
        server._wf_call_agent,
    ) = old
    server.refresh_agent_maps()
    status_dir.cleanup()
    oc_home.cleanup()


def install_fake_gateway(oc_home):
    def fake_rpc(method, params=None, timeout=20):
        params = params or {}
        if method == "agents.list":
            return {"ok": True, "agents": [{"id": "main", "model": "fake-model"}]}
        if method == "agents.create":
            agent_id = "archive-manager"
            workspace = params.get("workspace") or os.path.join(oc_home, "workspace-archive-manager")
            os.makedirs(os.path.join(oc_home, "agents", agent_id, "sessions"), exist_ok=True)
            os.makedirs(workspace, exist_ok=True)
            return {"ok": True, "agentId": agent_id}
        return {"ok": True}

    server._gateway_rpc_call = fake_rpc


def test_ai_refine_delegates_prompt_and_applies_json_output():
    status_dir, oc_home, old = setup_store()
    try:
        install_fake_gateway(oc_home.name)
        captured = {}

        def fake_call(agent_id, message, timeout=600, project_id=None, task_id=None):
            captured["agentId"] = agent_id
            captured["message"] = message
            captured["projectId"] = project_id
            captured["taskId"] = task_id
            return json.dumps({
                "status": "ok",
                "summary": "项目档案已完成 AI 精整，当前重点是验收反馈闭环。",
                "currentState": "档案室正在验证 AI 精整链路。",
                "nextStep": "请人工确认精整摘要是否准确。",
                "highlights": ["频率治理已上线"],
                "risks": ["仍需确认长期维护策略"],
                "gaps": ["缺少最终人工验收结论"],
                "archiveEntries": [{
                    "title": "AI 精整摘要",
                    "kind": "summary",
                    "text": "档案管理员 AI 判断当前项目重点是验收反馈闭环。",
                    "confidence": server.ARCHIVE_INFERENCE,
                }],
            }, ensure_ascii=False)

        server._wf_call_agent = fake_call
        project = server._handle_project_create({
            "title": "AI Refine Acceptance",
            "description": "Validate AI archive refinement.",
            "archiveMaintenanceEnabled": True,
        })["project"]
        result = server._handle_archive_manager_ai_refine(project["id"], {})
        assert result["ok"] is True
        assert captured["agentId"] == server.ARCHIVE_MANAGER_AGENT_ID
        assert captured["projectId"] == project["id"]
        assert captured["taskId"] == "archive-ai-refine"
        assert "稳定 JSON" in captured["message"]
        assert "不要输出 JSON 以外的文字" in captured["message"]
        detail = result["project"]
        assert detail["summary"]["currentState"] == "档案室正在验证 AI 精整链路。"
        assert any(e.get("title") == "AI 精整摘要" for e in detail["entries"])
        latest = detail["managerMaintenance"][-1]
        assert latest["eventType"] == "ai_refine"
        assert latest["prompt"] == captured["message"]
        assert latest["output"]["parsed"]["status"] == "ok"
    finally:
        teardown_store(status_dir, oc_home, old)


if __name__ == "__main__":
    test_ai_refine_delegates_prompt_and_applies_json_output()
    print("ok")
