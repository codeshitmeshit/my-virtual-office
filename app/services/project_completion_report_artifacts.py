"""Collect the explicit final artifacts eligible for completion reporting."""

from __future__ import annotations

import os
from typing import Any, Callable, Mapping

from .artifacts import normalize_relative_path


MAX_ARTIFACT_REFS = 20
MAX_AGENT_TEXT_BYTES = 512 * 1024
INLINE_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html"})


def _path_from_ref(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("path")
    return normalize_relative_path(value)


def _candidate_paths(project: Mapping[str, Any]) -> list[str]:
    candidates: list[str] = []
    orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
    final_report = orchestration.get("finalReport") if isinstance(orchestration.get("finalReport"), Mapping) else {}
    project_report = _path_from_ref(final_report.get("markdownPath"))
    if project_report:
        candidates.append(project_report)

    tasks = [task for task in project.get("tasks") or [] if isinstance(task, Mapping)]
    tasks.sort(key=lambda task: (
        int(task.get("executionStage") or 0) if str(task.get("executionStage") or "").isdigit() else 0,
        str(task.get("id") or ""),
    ))
    for task in tasks:
        final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
        markdown_path = _path_from_ref(final_result.get("markdownPath"))
        if markdown_path:
            candidates.append(markdown_path)
        for ref in final_result.get("artifactRefs") or []:
            path = _path_from_ref(ref)
            if path:
                candidates.append(path)

    seen: set[str] = set()
    unique: list[str] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def collect_completion_report_artifacts(
    project: Mapping[str, Any],
    *,
    read_artifact: Callable[..., Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Read only explicit final refs and return bounded input plus omissions."""

    candidates = _candidate_paths(project)
    artifacts: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    if len(candidates) > MAX_ARTIFACT_REFS:
        for path in candidates[MAX_ARTIFACT_REFS:]:
            omissions.append({
                "path": path,
                "reason": "reference_limit",
                "detail": f"Only the first {MAX_ARTIFACT_REFS} final artifacts are supported",
            })
    remaining_bytes = MAX_AGENT_TEXT_BYTES
    for path in candidates[:MAX_ARTIFACT_REFS]:
        extension = os.path.splitext(path)[1].lower()
        if extension not in INLINE_TEXT_EXTENSIONS:
            artifacts.append({
                "path": path,
                "kind": "reference",
                "size": None,
                "inline": False,
                "truncated": False,
                "content": "",
            })
            continue
        result = read_artifact(path, allow_text=True, associated_only=True)
        if not result.get("ok"):
            omissions.append({
                "path": path,
                "reason": "unavailable",
                "detail": str(result.get("error") or "Artifact could not be read"),
            })
            continue
        source = result.get("artifact") if isinstance(result.get("artifact"), Mapping) else {}
        content = str(source.get("content") or "")
        raw = content.encode("utf-8")
        truncated = bool(source.get("truncated"))
        if len(raw) > remaining_bytes:
            omissions.append({
                "path": path,
                "reason": "text_limit",
                "detail": "Artifact text was truncated to the completion-report input limit",
            })
            raw = raw[:remaining_bytes]
            content = raw.decode("utf-8", errors="ignore")
            truncated = True
        remaining_bytes -= len(content.encode("utf-8"))
        if not content and raw:
            continue
        artifacts.append({
            "path": path,
            "kind": str(source.get("kind") or "text"),
            "size": source.get("size"),
            "inline": True,
            "truncated": truncated,
            "content": content,
        })
    return {"artifacts": artifacts, "omissions": omissions}
