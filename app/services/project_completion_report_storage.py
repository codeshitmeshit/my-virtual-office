"""Safe, versioned workspace storage for Feishu completion reports."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from typing import Any


REPORT_FILENAME = "FEISHU_COMPLETION_REPORT.md"


class CompletionReportStorageError(RuntimeError):
    """Raised when a completion report cannot be stored safely."""


def _positive_version(value: Any) -> int:
    if isinstance(value, bool):
        raise CompletionReportStorageError("version must be a positive integer")
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise CompletionReportStorageError("version must be a positive integer") from exc
    if version <= 0:
        raise CompletionReportStorageError("version must be a positive integer")
    return version


def _safe_occurrence_id(value: Any) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return slug[:120] or "occurrence"


def write_completion_report(
    project: dict[str, Any],
    occurrence: dict[str, Any],
    markdown: str,
) -> dict[str, Any]:
    """Write one immutable report sidecar and update its occurrence metadata."""

    workspace_path = str(project.get("workspacePath") or "").strip()
    if not workspace_path:
        raise CompletionReportStorageError("workspacePath is required")
    root = os.path.realpath(os.path.expanduser(workspace_path))
    if not os.path.isdir(root):
        raise CompletionReportStorageError("workspacePath is not a directory")

    version = _positive_version(occurrence.get("version"))
    occurrence_slug = _safe_occurrence_id(occurrence.get("occurrenceId"))
    relative_path = (
        f".vo/project-completion-reports/v{version}-{occurrence_slug}/{REPORT_FILENAME}"
    )
    destination = os.path.realpath(os.path.join(root, *relative_path.split("/")))
    if not destination.startswith(root + os.sep):
        raise CompletionReportStorageError("report path escapes workspace")
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if not os.path.realpath(os.path.dirname(destination)).startswith(root + os.sep):
        raise CompletionReportStorageError("report directory escapes workspace")

    content = str(markdown or "")
    encoded = content.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    if os.path.lexists(destination):
        if os.path.islink(destination):
            raise CompletionReportStorageError("report destination must not be a symlink")
        with open(destination, "rb") as stream:
            existing_digest = hashlib.sha256(stream.read()).hexdigest()
        if existing_digest != digest:
            raise CompletionReportStorageError(
                "completion report already exists with different content"
            )
        created = False
    else:
        fd, temporary = tempfile.mkstemp(
            prefix=".completion-report-",
            dir=os.path.dirname(destination),
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
                created = True
            except FileExistsError:
                with open(destination, "rb") as stream:
                    existing_digest = hashlib.sha256(stream.read()).hexdigest()
                if existing_digest != digest:
                    raise CompletionReportStorageError(
                        "completion report already exists with different content"
                    )
                created = False
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    occurrence["reportMarkdownPath"] = relative_path
    occurrence["reportDigest"] = digest
    return {"markdownPath": relative_path, "digest": digest, "created": created}
