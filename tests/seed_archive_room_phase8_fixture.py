#!/usr/bin/env python3
"""Seed a realistic Archive Room phase 8 acceptance project in the active data dir."""

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
    workspace = os.path.join(server.STATUS_DIR, "project-workspaces", "archive-room-phase8-governance-frequency")
    os.makedirs(workspace, exist_ok=True)
    write_file(
        os.path.join(workspace, "docs", "phase8", "governance", "source-comparison.md"),
        "# Phase 8 Source Comparison\n\nThis fixture validates schedule controls, auto governance notices, stale replacement, and owner-level pending decisions.\n",
    )
    write_file(
        os.path.join(workspace, "docs", "phase8", "operations", "daily-inspection.md"),
        "# Daily Inspection Notes\n\nThe archive manager should show event-triggered plus weekly scheduled inspection for this project.\n",
    )
    write_file(
        os.path.join(workspace, "media", "phase8", "preview", "image.png"),
        b"\x89PNG\r\n\x1a\n",
        binary=True,
    )
    write_file(
        os.path.join(workspace, "media", "phase8", "preview", "video.mp4"),
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
        binary=True,
    )
    write_file(
        os.path.join(workspace, "media", "phase8", "preview", "audio.mp3"),
        b"ID3\x03\x00\x00\x00\x00\x00\x21",
        binary=True,
    )

    project = server._handle_project_create({
        "title": "Archive Room Phase 8 Frequency Governance Acceptance",
        "description": "验收档案室 Phase8：维护频率配置、事件触发与计划巡检、档案管理员自动处理非人工确认内容、stale 替代关系、来源对比和 owner 级人工边界。",
        "projectExecutionEnabled": True,
        "workspacePath": workspace,
        "archiveMaintenanceEnabled": True,
        "longTermProject": True,
        "tags": ["archive-room", "phase8", "governance"],
    })["project"]

    task = server._handle_task_create(project["id"], {
        "title": "Produce Phase 8 governance fixture artifacts",
        "description": "Create source-backed documents and media artifacts for Phase 8 acceptance.",
    })["task"]
    now = server._proj_now()
    task["completedAt"] = now
    task["evidence"] = {
        "attemptId": "phase8-fixture-attempt",
        "changedFiles": [
            "docs/phase8/governance/source-comparison.md",
            "docs/phase8/operations/daily-inspection.md",
            "media/phase8/preview/image.png",
            "media/phase8/preview/video.mp4",
            "media/phase8/preview/audio.mp3",
        ],
        "summary": "Created Phase8 acceptance documents plus media preview files.",
        "capturedAt": now,
        "providerRef": {"providerKind": "codex", "agentId": "codex-local"},
    }
    task["attempts"] = [{
        "id": "phase8-fixture-attempt",
        "executor": {"id": "codex-local", "providerKind": "codex"},
        "evidence": task["evidence"],
        "finishedAt": now,
    }]

    data = server._load_projects()
    for p in data.get("projects", []):
        if p.get("id") == project["id"]:
            p["tasks"] = [task]
            p["archiveMaintenance"] = {
                **(p.get("archiveMaintenance") or {}),
                "enabled": True,
                "scheduleMode": "weekly",
                "frequency": "weekly",
                "updatedAt": now,
                "updatedBy": "phase8-seed",
            }
            p["archiveMaintenanceEnabled"] = True
            p["longTermProject"] = True
            p["updatedAt"] = now
            project = p
            break
    server._save_projects(data)

    server._archive_trigger_task_completed(project["id"], task)
    server._archive_run_inspection("daily_inspection", force=True)

    server._archive_maintenance_trigger(
        project["id"],
        "meeting_conclusion",
        source=server._archive_source_ref("meeting", "phase8-auto-old", title="旧范围会议"),
        title="当前整理范围",
        summary="当前整理范围包括维护频率展示。",
        value_level="high",
        impact="state",
        reason="旧的非人工确认会议摘要。",
    )
    server._archive_maintenance_trigger(
        project["id"],
        "meeting_conclusion",
        source=server._archive_source_ref("meeting", "phase8-auto-new", title="新范围会议"),
        title="当前整理范围",
        summary="当前整理范围包括维护频率展示、来源对比和旧资料过期标记。",
        value_level="high",
        impact="state",
        reason="更新后的会议摘要来源更强，档案管理员自动替换非人工确认内容。",
    )

    server._archive_maintenance_trigger(
        project["id"],
        "meeting_conclusion",
        source=server._archive_source_ref("meeting", "phase8-owner-rule", title="Owner 规则会议"),
        title="发布规则",
        summary="Rule: archive governance rule changes require owner approval.",
        value_level="high",
        impact="state",
        reason="Long-lived owner-level rule.",
    )
    detail = server._handle_archive_room_project(project["id"])["project"]
    pending_rule = next((item for item in detail["pendingConfirmations"] if item.get("title") == "发布规则"), None)
    if pending_rule is None and detail.get("pendingConfirmations"):
        pending_rule = detail["pendingConfirmations"][0]
    if pending_rule is not None:
        server._handle_archive_governance_action(project["id"], pending_rule["id"], {
            "action": "confirm",
            "reason": "验收种子：创建 human_confirmed 规则用于 Phase8 人工边界。",
        })
    server._archive_maintenance_trigger(
        project["id"],
        "conflict_reminder",
        source=server._archive_source_ref("meeting", "phase8-owner-conflict", title="AI 自动建议"),
        title="发布规则",
        summary="New suggestion says archive governance rule changes can be auto-approved by project AI.",
        value_level="high",
        impact="risk",
        reason="Conflicts with human-confirmed owner rule.",
    )

    now = server._proj_now()
    record = server._archive_room_load_project_record(project["id"])
    comparison = {
        "oldEntryId": "phase8-auto-old-entry",
        "newEntryId": "phase8-auto-new-entry",
        "reason": "更新后的会议摘要来源更强，档案管理员自动替换非人工确认内容。",
    }
    entries = record.setdefault("entries", [])
    entries.extend([
        {
            "id": "phase8-auto-old-entry",
            "title": "当前整理范围",
            "text": "当前整理范围包括维护频率展示。",
            "kind": "meeting_conclusion",
            "authority": server.ARCHIVE_AUTH_MANAGER,
            "confidence": server.ARCHIVE_CONFIRMED,
            "stale": True,
            "staleReason": "旧内容已标记过期。",
            "sourceComparison": comparison,
            "sources": [server._archive_source_ref("meeting", "phase8-auto-old", title="旧范围会议")],
            "updatedAt": now,
        },
        {
            "id": "phase8-auto-new-entry",
            "title": "当前整理范围",
            "text": "当前整理范围包括维护频率展示、来源对比和旧资料过期标记。",
            "kind": "meeting_conclusion",
            "authority": server.ARCHIVE_AUTH_MANAGER,
            "confidence": server.ARCHIVE_CONFIRMED,
            "replaces": "phase8-auto-old-entry",
            "sourceComparison": comparison,
            "sources": [server._archive_source_ref("meeting", "phase8-auto-new", title="新范围会议")],
            "updatedAt": now,
        },
    ])
    record["automaticGovernanceNotices"] = [{
        "id": "phase8-auto-governance-notice",
        "title": "当前整理范围",
        "summary": "档案管理员已自动处理非人工确认内容。旧内容已标记过期。",
        "action": "auto_governance_resolved",
        "sourceComparison": comparison,
        "createdAt": now,
    }]
    pending_comparison = {
        "oldEntryId": "phase8-human-rule-entry",
        "newEntryId": "phase8-owner-conflict-entry",
        "reason": "新建议与人工确认内容冲突，需要 owner 判断。",
    }
    entries.append({
        "id": "phase8-human-rule-entry",
        "title": "发布规则",
        "text": "Rule: archive governance rule changes require owner approval.",
        "kind": "meeting_conclusion",
        "authority": server.ARCHIVE_AUTH_HUMAN,
        "confidence": server.ARCHIVE_CONFIRMED,
        "confirmedBy": "phase8-seed",
        "confirmedAt": now,
        "updatedAt": now,
    })
    record["pendingConfirmations"] = [{
        "id": "phase8-owner-conflict-pending",
        "eventKey": "phase8-owner-conflict",
        "title": "发布规则",
        "text": "New suggestion says archive governance rule changes can be auto-approved by project AI.",
        "kind": "conflict_reminder",
        "authority": server.ARCHIVE_AUTH_PENDING_HUMAN,
        "confidence": server.ARCHIVE_PENDING,
        "reason": "Conflicts with human-confirmed owner rule.",
        "impact": "risk",
        "humanDecisionNeeded": "请确认、编辑确认、暂缓或拒绝该档案建议。",
        "automationInsufficientReason": "涉及人工确认内容或 owner 级决策，不能自动处理。",
        "sourceComparison": pending_comparison,
        "createdAt": now,
        "updatedAt": now,
    }]
    record["archiveUpdatedAt"] = now
    server._archive_room_save_project_record(project["id"], record)
    detail = server._handle_archive_room_project(project["id"])["project"]
    print(project["id"])
    print(detail["title"])


if __name__ == "__main__":
    main()
