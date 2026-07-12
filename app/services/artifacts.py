"""Filesystem-safe Artifact operations independent of HTTP and ``server.py``."""

from __future__ import annotations

import os
import stat
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, BinaryIO, Iterable, Mapping


MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
TEXT_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml", ".log"})
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | {".pdf"}
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".ogg", ".mov", ".m4v"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"})
ALLOWED_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "target",
    ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "site-packages",
    "dist-packages",
})
MAX_ITEMS = 500
MAX_READ_BYTES = 512 * 1024
MAX_DEPTH = 8
MAX_SCANNED_ENTRIES = 20_000
MAX_DELETE_ENTRIES = 5_000
MAX_DELETED_FILES = 1_000


def _error(message: str, status: int) -> dict[str, Any]:
    return {"error": message, "_status": status}


def kind_for_extension(extension: str) -> str:
    extension = str(extension or "").lower()
    if extension in MARKDOWN_EXTENSIONS:
        return "markdown"
    if extension in TEXT_EXTENSIONS:
        return "text"
    if extension == ".pdf":
        return "pdf"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    return "file"


def normalize_relative_path(path: Any) -> str:
    relative = urllib.parse.unquote(str(path or "")).replace("\\", "/").lstrip("/")
    parts = [part for part in relative.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def resolve_inside_root(root: Any, relative_path: Any) -> tuple[str | None, str]:
    root_real = os.path.realpath(str(root or ""))
    relative = normalize_relative_path(relative_path)
    if not relative:
        return None, ""
    full_path = os.path.realpath(os.path.join(root_real, relative))
    if full_path != root_real and not full_path.startswith(root_real + os.sep):
        return None, relative
    return full_path, relative


@dataclass
class OpenedArtifact:
    """An already validated descriptor that cannot be replaced before streaming."""

    stream: BinaryIO
    relative_path: str
    kind: str
    size: int
    extension: str

    @property
    def closed(self) -> bool:
        return self.stream.closed

    def fileno(self) -> int:
        return self.stream.fileno()

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)

    def close(self) -> None:
        self.stream.close()

    def __enter__(self) -> "OpenedArtifact":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


class UnsafeArtifactError(OSError):
    pass


def _open_component_no_follow(root: str, relative: str) -> int:
    """Open every path component relative to a trusted root descriptor."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow or not _secure_open_available():
        raise NotImplementedError("secure dir_fd open is unavailable")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | nofollow
    file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0) | nofollow
    root_fd = os.open(root, directory_flags)
    current_fd = root_fd
    try:
        parts = relative.split("/")
        for component in parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        return os.open(parts[-1], file_flags, dir_fd=current_fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _open_fallback(root: str, full_path: str) -> int:
    """Fallback for platforms without dir_fd/no-follow; revalidate inode after open."""
    before = os.stat(full_path, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise UnsafeArtifactError("not a regular file")
    descriptor = os.open(
        full_path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        after = os.fstat(descriptor)
        canonical = os.path.realpath(full_path)
        if canonical != root and not canonical.startswith(root + os.sep):
            raise UnsafeArtifactError("outside root")
        latest = os.stat(full_path, follow_symlinks=False)
        identity = (before.st_dev, before.st_ino)
        if (
            not stat.S_ISREG(after.st_mode)
            or identity != (after.st_dev, after.st_ino)
            or identity != (latest.st_dev, latest.st_ino)
        ):
            raise UnsafeArtifactError("artifact changed while opening")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_regular(root: str, full_path: str, relative: str) -> tuple[int, os.stat_result]:
    try:
        descriptor = _open_component_no_follow(root, relative)
    except (NotImplementedError, TypeError):
        descriptor = _open_fallback(root, full_path)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeArtifactError("not a regular file")
        return descriptor, metadata
    except Exception:
        os.close(descriptor)
        raise


def _secure_open_available() -> bool:
    supports = getattr(os, "supports_dir_fd", set())
    return bool(
        getattr(os, "O_NOFOLLOW", 0) and getattr(os, "O_DIRECTORY", 0)
        and os.open in supports
    )


def _secure_file_delete_available() -> bool:
    supports = getattr(os, "supports_dir_fd", set())
    return bool(_secure_open_available() and os.stat in supports and os.unlink in supports)


def _secure_directory_delete_available() -> bool:
    dir_support = getattr(os, "supports_dir_fd", set())
    fd_support = getattr(os, "supports_fd", set())
    return bool(
        _secure_file_delete_available()
        and os.rmdir in dir_support
        and os.listdir in fd_support
    )


def _root(context: Mapping[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    raw_root = context.get("root")
    if not isinstance(raw_root, (str, os.PathLike)) or not str(raw_root).strip():
        return None, _error("Artifact root is not accessible", 409)
    expanded = os.path.expanduser(str(raw_root).strip())
    if not os.path.isabs(expanded):
        return None, _error("Artifact root is not accessible", 409)
    root = os.path.realpath(expanded)
    if not root or not os.path.isdir(root):
        return None, _error("Artifact root is not accessible", 409)
    return root, None


def _validated_path(context: Mapping[str, Any], relative_path: Any) -> tuple[str | None, str, dict[str, Any] | None]:
    root, error = _root(context)
    if error:
        return None, "", error
    full_path, relative = resolve_inside_root(root, relative_path)
    if not relative:
        return None, "", _error("Artifact path is required", 400)
    if not full_path:
        return None, relative, _error("Artifact path is outside the artifact root", 403)
    return full_path, relative, None


def list_artifacts(
    context: Mapping[str, Any],
    allowed_extensions: Iterable[str] | None = None,
    associated_only: bool = False,
) -> dict[str, Any]:
    root, error = _root(context)
    if error:
        return error
    allowed = frozenset(allowed_extensions or MARKDOWN_EXTENSIONS)
    sources = context.get("sourcesByPath") if isinstance(context.get("sourcesByPath"), dict) else {}
    artifacts: list[dict[str, Any]] = []
    truncated = False
    scanned = 0
    try:
        for current_root, directories, files in os.walk(root, followlinks=False):
            scanned += len(directories) + len(files)
            if scanned > MAX_SCANNED_ENTRIES:
                truncated = True
                break
            directories[:] = [
                name for name in directories
                if name not in EXCLUDE_DIRS and not name.startswith(".git")
                and not os.path.islink(os.path.join(current_root, name))
            ]
            relative_dir = os.path.relpath(current_root, root)
            depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
            if depth > MAX_DEPTH:
                directories[:] = []
                continue
            for name in files:
                extension = os.path.splitext(name)[1].lower()
                if extension not in allowed:
                    continue
                path = os.path.join(current_root, name)
                try:
                    metadata = os.stat(path, follow_symlinks=False)
                except OSError:
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                relative = os.path.relpath(path, root).replace(os.sep, "/")
                records = sources.get(relative, [])
                if associated_only and not records:
                    continue
                artifacts.append({
                    "path": relative, "name": name, "kind": kind_for_extension(extension),
                    "extension": extension, "size": metadata.st_size,
                    "modifiedAt": datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat(),
                    "sources": records[:10], "unassociated": not bool(records),
                })
                if len(artifacts) >= MAX_ITEMS:
                    truncated = True
                    break
            if truncated:
                break
    except OSError:
        return _error("Unable to scan artifacts", 500)
    artifacts.sort(key=lambda item: (item.get("modifiedAt") or "", item.get("path") or ""), reverse=True)
    return {"ok": True, "artifacts": artifacts, "truncated": truncated}


def open_file(context: Mapping[str, Any], relative_path: Any, *, associated_only: bool = True) -> dict[str, Any]:
    full_path, relative, error = _validated_path(context, relative_path)
    if error:
        return error
    extension = os.path.splitext(relative)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return _error("Artifact type is not previewable", 415)
    sources = context.get("sourcesByPath") if isinstance(context.get("sourcesByPath"), dict) else {}
    if associated_only and not sources.get(relative):
        return _error("Artifact is not associated with this project", 403)
    root = os.path.realpath(str(context.get("root") or ""))
    try:
        descriptor, metadata = _open_regular(root, full_path, relative)
    except FileNotFoundError:
        return _error("Artifact not found", 404)
    except (OSError, UnsafeArtifactError):
        return _error("Artifact is not a safe regular file", 403)
    stream = os.fdopen(descriptor, "rb", closefd=True)
    return {
        "ok": True,
        "opened": OpenedArtifact(stream, relative, kind_for_extension(extension), metadata.st_size, extension),
    }


def read_artifact(
    context: Mapping[str, Any], relative_path: Any, *, allow_text: bool = False,
    associated_only: bool = False,
) -> dict[str, Any]:
    full_path, relative, error = _validated_path(context, relative_path)
    if error:
        return error
    extension = os.path.splitext(relative)[1].lower()
    allowed = TEXT_EXTENSIONS if allow_text else MARKDOWN_EXTENSIONS
    if extension not in allowed:
        return _error("Only text artifacts can be read inline" if allow_text else "Only Markdown artifacts can be read inline", 415)
    sources = context.get("sourcesByPath") if isinstance(context.get("sourcesByPath"), dict) else {}
    if associated_only and not sources.get(relative):
        return _error("Artifact is not associated with this project", 403)
    root = os.path.realpath(str(context.get("root") or ""))
    try:
        descriptor, metadata = _open_regular(root, full_path, relative)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            raw = stream.read(MAX_READ_BYTES + 1)
    except FileNotFoundError:
        return _error("Artifact not found", 404)
    except (OSError, UnsafeArtifactError):
        return _error("Artifact is not a safe regular file", 403)
    truncated = len(raw) > MAX_READ_BYTES
    if truncated:
        raw = raw[:MAX_READ_BYTES]
    return {"ok": True, "artifact": {
        "path": relative, "kind": kind_for_extension(extension), "size": metadata.st_size,
        "truncated": truncated, "content": raw.decode("utf-8", errors="replace"),
    }}


def delete_file(context: Mapping[str, Any], relative_path: Any) -> dict[str, Any]:
    full_path, relative, error = _validated_path(context, relative_path)
    if error:
        return error
    extension = os.path.splitext(relative)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return _error("Artifact type is not deletable here", 415)
    root = os.path.realpath(str(context.get("root") or ""))
    if not _secure_file_delete_available():
        return _delete_file_fallback(root, full_path, relative)
    parent_relative, name = os.path.split(relative)
    parent_fd = None
    try:
        parent_path = root if not parent_relative else os.path.join(root, parent_relative)
        parent_fd = _open_component_no_follow(root, parent_relative) if parent_relative else os.open(
            root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            return _error("Artifact is not a safe regular file", 403)
        os.unlink(name, dir_fd=parent_fd)
    except FileNotFoundError:
        return _error("Artifact not found", 404)
    except (OSError, UnsafeArtifactError):
        return _error("Unable to delete artifact", 500)
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    return {"ok": True, "deleted": relative}


def _delete_file_fallback(root: str, full_path: str, relative: str) -> dict[str, Any]:
    return {
        "error": "Safe artifact deletion is unavailable on this platform",
        "code": "artifact_safe_delete_unavailable",
        "_status": 409,
    }


def delete_directory(context: Mapping[str, Any], relative_directory: Any) -> dict[str, Any]:
    root, error = _root(context)
    if error:
        return error
    if relative_directory:
        full_path, relative = resolve_inside_root(root, relative_directory)
        if not relative:
            return _error("Artifact path is required", 400)
        if not full_path:
            return _error("Artifact path is outside the artifact root", 403)
    else:
        full_path, relative = root, ""
    if not _secure_directory_delete_available():
        return _delete_directory_fallback(root, full_path, relative)
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_fd = target_fd = None
    target_name = ""
    deleted = [0]
    scanned = [0]
    truncated = [False]

    def delete_allowed(directory_fd: int) -> None:
        for name in os.listdir(directory_fd):
            scanned[0] += 1
            if scanned[0] > MAX_DELETE_ENTRIES or deleted[0] >= MAX_DELETED_FILES:
                truncated[0] = True
                return
            try:
                metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(metadata.st_mode):
                if os.path.splitext(name)[1].lower() in ALLOWED_EXTENSIONS:
                    os.unlink(name, dir_fd=directory_fd)
                    deleted[0] += 1
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                continue
            child_fd = os.open(name, directory_flags, dir_fd=directory_fd)
            try:
                delete_allowed(child_fd)
            finally:
                os.close(child_fd)
            if truncated[0]:
                return
            try:
                os.rmdir(name, dir_fd=directory_fd)
            except OSError:
                pass

    try:
        if relative:
            parent_relative, target_name = os.path.split(relative)
            if parent_relative:
                parent_fd = _open_component_no_follow(root, parent_relative)
            else:
                parent_fd = os.open(root, directory_flags)
            target_fd = os.open(target_name, directory_flags, dir_fd=parent_fd)
        else:
            target_fd = os.open(root, directory_flags)
        if not stat.S_ISDIR(os.fstat(target_fd).st_mode):
            return _error("Artifact directory not found", 404)
        delete_allowed(target_fd)
        if relative:
            try:
                os.rmdir(target_name, dir_fd=parent_fd)
            except OSError:
                pass
    except FileNotFoundError:
        return _error("Artifact directory not found", 404)
    except OSError:
        return _error("Unable to delete artifact directory", 500)
    finally:
        if target_fd is not None:
            os.close(target_fd)
        if parent_fd is not None:
            os.close(parent_fd)
    return {
        "ok": True, "deletedDir": relative, "deleted": deleted[0],
        **({"truncated": True} if truncated[0] else {}),
    }


def _delete_directory_fallback(root: str, full_path: str, relative: str) -> dict[str, Any]:
    return {
        "error": "Safe artifact deletion is unavailable on this platform",
        "code": "artifact_safe_delete_unavailable",
        "_status": 409,
    }
