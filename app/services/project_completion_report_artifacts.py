"""Collect the explicit final artifacts eligible for completion reporting."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Mapping

from .artifacts import normalize_relative_path


MAX_ARTIFACT_REFS = 20
MAX_AGENT_TEXT_BYTES = 512 * 1024
INLINE_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html"})
_SENSITIVE_BASENAME_RE = re.compile(
    r"(^\.env(?:\.|$)|credential|client[-_]?secret|secret|token|private[-_]?key|id_rsa|id_ed25519)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?im)^(\s*[\"']?(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|webhook)[\"']?\s*[:=]\s*).*$"
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_EXECUTION_SUMMARY_NAMES = frozenset({"PROJECT_FINAL_REPORT.MD", "TASK_FINAL_RESULT.MD"})


def _path_from_ref(value: Any, *, workspace_path: Any = "") -> str:
    if isinstance(value, Mapping):
        value = value.get("path")
    raw = str(value or "").strip()
    workspace = os.path.realpath(os.path.expanduser(str(workspace_path or "").strip()))
    if raw and os.path.isabs(os.path.expanduser(raw)):
        absolute = os.path.realpath(os.path.expanduser(raw))
        if not workspace or (
            absolute != workspace and not absolute.startswith(workspace + os.sep)
        ):
            return ""
        raw = os.path.relpath(absolute, workspace)
    return normalize_relative_path(raw)


def scrub_sensitive_text(value: Any) -> str:
    """Remove common credential assignments before text reaches an Agent."""

    text = str(value or "")
    text = _PRIVATE_KEY_RE.sub("[REDACTED]", text)
    return _SENSITIVE_ASSIGNMENT_RE.sub(lambda match: match.group(1) + "[REDACTED]", text)


def _sensitive_path(path: str) -> bool:
    return bool(_SENSITIVE_BASENAME_RE.search(os.path.basename(path)))


def _execution_summary_path(path: str) -> bool:
    return os.path.basename(path).upper() in _EXECUTION_SUMMARY_NAMES


def _candidate_paths(project: Mapping[str, Any]) -> list[str]:
    workspace_path = project.get("workspacePath")
    business_outputs: list[str] = []
    task_summaries: list[str] = []

    tasks = [task for task in project.get("tasks") or [] if isinstance(task, Mapping)]
    tasks.sort(key=lambda task: (
        int(task.get("executionStage") or 0) if str(task.get("executionStage") or "").isdigit() else 0,
        str(task.get("id") or ""),
    ))
    for task in tasks:
        final_result = task.get("finalResult") if isinstance(task.get("finalResult"), Mapping) else {}
        for ref in final_result.get("artifactRefs") or []:
            path = _path_from_ref(ref, workspace_path=workspace_path)
            if path and not _execution_summary_path(path):
                business_outputs.append(path)
        markdown_path = _path_from_ref(
            final_result.get("markdownPath"),
            workspace_path=workspace_path,
        )
        if markdown_path and not _execution_summary_path(markdown_path):
            task_summaries.append(markdown_path)

    orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
    final_report = orchestration.get("finalReport") if isinstance(orchestration.get("finalReport"), Mapping) else {}
    project_report = _path_from_ref(
        final_report.get("markdownPath"),
        workspace_path=workspace_path,
    )
    if _execution_summary_path(project_report):
        project_report = ""

    # Explicit task artifactRefs and a genuinely authored project final report
    # are business deliverables. Known lifecycle summaries are deliberately
    # excluded so they cannot replace the result the owner asked to receive.
    candidates = [*business_outputs, *([project_report] if project_report else [])]
    if not candidates:
        candidates = task_summaries

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
        if _sensitive_path(path):
            omissions.append({
                "path": path,
                "reason": "sensitive_path",
                "detail": "Sensitive credential files are not eligible for completion reporting",
            })
            continue
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
        content = scrub_sensitive_text(source.get("content") or "")
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
