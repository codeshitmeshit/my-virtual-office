#!/usr/bin/env python3
"""Seed a realistic Archive Room phase 7 acceptance project in the active data dir."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import server


def install_fake_gateway():
    oc_home = os.path.join(server.STATUS_DIR, "openclaw-fixture")
    os.makedirs(oc_home, exist_ok=True)
    server.WORKSPACE_BASE = oc_home
    server._discovered_roster = []
    server._discovered_at = 0

    def fake_rpc(method, params=None, timeout=20):
        params = params or {}
        if method == "agents.list":
            return {"ok": True, "agents": [{"id": "main", "model": "fake-model"}]}
        if method == "agents.create":
            agent_id = "archive-manager"
            workspace = params.get("workspace") or os.path.join(oc_home, "workspace-archive-manager")
            os.makedirs(os.path.join(oc_home, "agents", agent_id, "sessions"), exist_ok=True)
            os.makedirs(workspace, exist_ok=True)
            cfg_path = os.path.join(oc_home, "openclaw.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                __import__("json").dump({"agents": {"list": [{"id": agent_id, "name": agent_id, "workspace": workspace, "model": "fake-model"}]}}, f)
            return {"ok": True, "agentId": agent_id}
        return {"ok": True}

    server._gateway_rpc_call = fake_rpc


def write_file(path, data, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as f:
        f.write(data)


def main():
    install_fake_gateway()
    workspace = os.path.join(server.STATUS_DIR, "project-workspaces", "archive-room-phase7-governance-acceptance")
    os.makedirs(workspace, exist_ok=True)
    write_file(os.path.join(workspace, "reports", "governance-summary.md"), "# Governance Summary\n\nPhase 7 archive governance fixture.\n")
    write_file(os.path.join(workspace, "media", "governance-note.txt"), "Archive manager note for phase 7.\n")
    write_file(os.path.join(workspace, "media", "pixel.png"), b"\x89PNG\r\n\x1a\n", binary=True)

    project = server._handle_project_create({
        "title": "Archive Room Phase 7 Governance Acceptance",
        "description": "验收档案室治理：系统来源确认、档案管理员确认、人工待确认、冲突处理和产物浏览。",
        "projectExecutionEnabled": True,
        "workspacePath": workspace,
        "archiveMaintenanceEnabled": True,
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Produce governance acceptance artifacts",
        "description": "Generate source-backed archive artifacts for phase 7 acceptance.",
    })["task"]
    task["completedAt"] = server._proj_now()
    task["evidence"] = {
        "changedFiles": ["reports/governance-summary.md", "media/governance-note.txt", "media/pixel.png"],
        "summary": "Created governance summary, note, and image.",
        "capturedAt": server._proj_now(),
    }
    data = server._load_projects()
    for p in data.get("projects", []):
        if p.get("id") == project["id"]:
            p["tasks"] = [task]
            p["updatedAt"] = server._proj_now()
    server._save_projects(data)

    server._archive_trigger_task_completed(project["id"], task)
    server._handle_archive_mark_important_message({
        "projectId": project["id"],
        "messageId": "phase7-manager-confirmed-message",
        "text": "档案管理员确认：这个项目用于验收 Phase 7 治理流程和 authority 标签。",
    })
    server._archive_maintenance_trigger(
        project["id"],
        "meeting_conclusion",
        source=server._archive_source_ref("meeting", "phase7-meeting-1", title="治理规则会议"),
        title="长期规则：发布策略",
        summary="长期规则建议：任何档案治理策略变更都需要项目 owner 人工确认。",
        value_level="high",
        impact="state",
        reason="Long-lived rule requires human confirmation.",
    )
    detail = server._handle_archive_room_project(project["id"])["project"]
    first_pending = detail["pendingConfirmations"][0]["id"]
    server._handle_archive_governance_action(project["id"], first_pending, {
        "action": "confirm",
        "reason": "验收种子：先创建一条 human_confirmed 规则用于冲突测试。",
    })
    server._archive_maintenance_trigger(
        project["id"],
        "conflict_reminder",
        source=server._archive_source_ref("task", task["id"], title=task["title"]),
        title="冲突提醒：发布策略",
        summary="新建议：档案治理策略变更可以由普通业务 AI 自动确认。",
        value_level="high",
        impact="risk",
        reason="Conflicts with human-confirmed archive governance rule.",
    )
    server._archive_maintenance_trigger(
        project["id"],
        "meeting_conclusion",
        source=server._archive_source_ref("meeting", "phase7-meeting-2", title="待暂缓建议"),
        title="高影响建议：重新设计治理标签",
        summary="建议：将 authority 标签重命名，需要 owner 判断。",
        value_level="high",
        impact="state",
        reason="High-impact archive context change.",
    )
    print(project["id"])


if __name__ == "__main__":
    main()
