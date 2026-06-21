#!/usr/bin/env python3
"""Seed a realistic Archive Room phase 8 acceptance project in the active data dir."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import server


def write_file(path, data, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if binary else "w"
    kwargs = {} if binary else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as f:
        f.write(data)


def main():
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
    pending_rule = next(item for item in detail["pendingConfirmations"] if item["title"] == "发布规则")
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

    detail = server._handle_archive_room_project(project["id"])["project"]
    print(project["id"])
    print(detail["title"])


if __name__ == "__main__":
    main()
