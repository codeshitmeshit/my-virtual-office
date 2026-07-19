"""Safe parsing, rendering, and synchronization of system-Agent profiles."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from types import MappingProxyType
from typing import Any, Mapping

from .system_agent_roles import SystemAgentRole


_SECTION_RE = re.compile(r"^--- file:\s*([A-Za-z0-9_.-]+)\s*---\s*$")
_UNRESOLVED_TOKEN_RE = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")
_SAFE_AGENT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class SystemAgentProfileError(ValueError):
    """Base error for invalid templates and unsafe profile paths."""


class ProfileTemplateError(SystemAgentProfileError):
    """Raised when a profile template cannot produce a complete profile."""


class UnsafeProfilePathError(SystemAgentProfileError):
    """Raised when workspace or file resolution crosses a trusted boundary."""


@dataclass(frozen=True, slots=True)
class RenderedSystemAgentProfile:
    version: str
    files: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))


@dataclass(frozen=True, slots=True)
class ProfileSyncResult:
    workspace: str
    version: str
    updated: bool
    written_files: tuple[str, ...]
    unchanged_files: tuple[str, ...]


def _safe_filename(value: Any) -> str:
    if not isinstance(value, str):
        raise UnsafeProfilePathError("profile filename must be a string")
    path = PurePath(value)
    if (
        not value
        or path.is_absolute()
        or len(path.parts) != 1
        or path.name in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise UnsafeProfilePathError("profile filename must be one safe relative segment")
    return value


def extract_template_version(template: str, version_marker: str) -> str:
    if not isinstance(template, str):
        raise ProfileTemplateError("profile template must be text")
    marker = version_marker.strip()
    if not marker or "\n" in marker or ":" in marker:
        raise ProfileTemplateError("version marker must be one non-empty header name")
    header = re.compile(rf"^{re.escape(marker)}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    versions = [
        match.group(1).strip()
        for line in template.splitlines()[:20]
        if (match := header.match(line))
    ]
    if len(versions) != 1 or not versions[0]:
        raise ProfileTemplateError(
            f"profile template must contain exactly one {version_marker} header in its first 20 lines"
        )
    if any(character.isspace() for character in versions[0]) or "\x00" in versions[0]:
        raise ProfileTemplateError("profile version must be one non-empty token")
    return versions[0]


def parse_template_files(template: str) -> dict[str, str]:
    files: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    def finish_current() -> None:
        if current_name is None:
            return
        content = "\n".join(current_lines).strip()
        files[current_name] = f"{content}\n" if content else ""

    for line in template.splitlines():
        marker = _SECTION_RE.match(line)
        if marker:
            finish_current()
            current_name = _safe_filename(marker.group(1))
            if current_name in files:
                raise ProfileTemplateError(f"duplicate profile file section: {current_name}")
            current_lines = []
            continue
        if line.lstrip().startswith("--- file:"):
            raise ProfileTemplateError(f"malformed profile file marker: {line.strip()}")
        if current_name is not None:
            current_lines.append(line)
    finish_current()
    if not files:
        raise ProfileTemplateError("profile template has no file sections")
    return files


def _normalized_tokens(tokens: Mapping[str, Any]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for name, raw_value in tokens.items():
        if not isinstance(name, str) or not name:
            raise ProfileTemplateError("profile token names must be non-empty strings")
        token = name if name.startswith("{{") and name.endswith("}}") else f"{{{{{name}}}}}"
        if not _UNRESOLVED_TOKEN_RE.fullmatch(token):
            raise ProfileTemplateError(f"invalid profile token name: {name}")
        value = str(raw_value)
        if "\x00" in value:
            raise ProfileTemplateError(f"profile token {name} contains a null byte")
        replacements[token] = value
    return replacements


def read_profile_version(content: str, version_marker: str) -> str:
    marker = re.compile(
        rf"{re.escape(version_marker)}\s*:\s*([^\s>]+)",
        re.IGNORECASE,
    )
    match = marker.search(content[:4096])
    return match.group(1).strip() if match else ""


def render_profile_template(
    template: str,
    *,
    version_marker: str,
    required_files: tuple[str, ...],
    tokens: Mapping[str, Any],
) -> RenderedSystemAgentProfile:
    version = extract_template_version(template, version_marker)
    sections = parse_template_files(template)
    required = tuple(_safe_filename(filename) for filename in required_files)
    if not required or len(set(required)) != len(required):
        raise ProfileTemplateError("required profile files must be non-empty and unique")
    missing = sorted(set(required) - set(sections))
    if missing:
        raise ProfileTemplateError(f"profile template missing files: {', '.join(missing)}")

    replacements = _normalized_tokens(tokens)
    rendered: dict[str, str] = {}
    for filename, source in sections.items():
        content = source
        for token, value in replacements.items():
            content = content.replace(token, value)
        unresolved = sorted(set(_UNRESOLVED_TOKEN_RE.findall(content)))
        if unresolved:
            raise ProfileTemplateError(
                f"profile file {filename} has unresolved tokens: {', '.join(unresolved)}"
            )
        if filename in required and read_profile_version(content, version_marker) != version:
            raise ProfileTemplateError(
                f"required profile file {filename} does not declare {version_marker}: {version}"
            )
        rendered[filename] = content if not content or content.endswith("\n") else f"{content}\n"
    return RenderedSystemAgentProfile(version=version, files=rendered)


def load_and_render_profile(
    template_path: str | os.PathLike[str],
    role: SystemAgentRole,
    *,
    tokens: Mapping[str, Any],
) -> RenderedSystemAgentProfile:
    path = Path(template_path)
    if path.is_symlink():
        raise UnsafeProfilePathError("profile template must not be a symbolic link")
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeProfilePathError("profile template must be a regular file")
        template = path.read_text(encoding="utf-8")
    except SystemAgentProfileError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ProfileTemplateError(f"profile template cannot be read: {exc}") from exc
    return render_profile_template(
        template,
        version_marker=role.version_marker,
        required_files=role.required_files,
        tokens=tokens,
    )


def _reject_existing_symlinks(root: Path, destination: Path) -> None:
    if root.is_symlink():
        raise UnsafeProfilePathError("OpenClaw home must not be a symbolic link")
    relative = destination.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeProfilePathError(f"profile path contains a symbolic link: {current}")


def resolve_safe_workspace(
    openclaw_home: str | os.PathLike[str],
    agent_id: str,
    configured_workspace: str | os.PathLike[str] | None = None,
) -> Path:
    if not isinstance(agent_id, str) or not _SAFE_AGENT_ID_RE.fullmatch(agent_id):
        raise UnsafeProfilePathError("agent_id is not provider-safe")
    root = Path(openclaw_home).absolute()
    destination = (
        Path(configured_workspace).absolute()
        if configured_workspace is not None and str(configured_workspace)
        else root / f"workspace-{agent_id}"
    )
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise UnsafeProfilePathError("system-Agent workspace is outside OpenClaw home") from exc
    if not relative.parts:
        raise UnsafeProfilePathError("system-Agent workspace must not be the OpenClaw home itself")
    _reject_existing_symlinks(root, destination)
    resolved_root = root.resolve(strict=False)
    resolved_destination = destination.resolve(strict=False)
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafeProfilePathError("resolved system-Agent workspace escapes OpenClaw home") from exc
    return resolved_destination


def profile_needs_update(
    workspace: Path,
    profile: RenderedSystemAgentProfile,
    *,
    version_marker: str,
) -> bool:
    if workspace.is_symlink() or not workspace.is_dir():
        return True
    for filename, expected in profile.files.items():
        _safe_filename(filename)
        target = workspace / filename
        if target.is_symlink() or not target.is_file():
            return True
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return True
        if read_profile_version(content, version_marker) != profile.version or content != expected:
            return True
    return False


def _atomic_write_text(workspace: Path, filename: str, content: str) -> None:
    safe_name = _safe_filename(filename)
    target = workspace / safe_name
    if target.is_symlink():
        raise UnsafeProfilePathError(f"profile target must not be a symbolic link: {safe_name}")
    descriptor = -1
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{safe_name}.", suffix=".tmp", dir=workspace)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = -1
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o666, follow_symlinks=False)
        if target.is_symlink():
            raise UnsafeProfilePathError(f"profile target became a symbolic link: {safe_name}")
        os.replace(temporary, target)
        temporary = ""
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def sync_profile_files(
    openclaw_home: str | os.PathLike[str],
    workspace: str | os.PathLike[str],
    profile: RenderedSystemAgentProfile,
    *,
    version_marker: str,
) -> ProfileSyncResult:
    root = Path(openclaw_home).absolute()
    destination = Path(workspace).absolute()
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise UnsafeProfilePathError("system-Agent workspace is outside OpenClaw home") from exc
    if not relative.parts:
        raise UnsafeProfilePathError("system-Agent workspace must not be OpenClaw home")
    _reject_existing_symlinks(root, destination)
    root.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    _reject_existing_symlinks(root, destination)
    if not destination.is_dir():
        raise UnsafeProfilePathError("system-Agent workspace must be a directory")

    written: list[str] = []
    unchanged: list[str] = []
    for filename, expected in profile.files.items():
        safe_name = _safe_filename(filename)
        target = destination / safe_name
        if target.is_symlink():
            raise UnsafeProfilePathError(f"profile target must not be a symbolic link: {safe_name}")
        current = None
        try:
            if target.is_file():
                current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            current = None
        if current == expected and read_profile_version(current, version_marker) == profile.version:
            unchanged.append(safe_name)
            continue
        _atomic_write_text(destination, safe_name, expected)
        written.append(safe_name)
    return ProfileSyncResult(
        workspace=str(destination.resolve(strict=False)),
        version=profile.version,
        updated=bool(written),
        written_files=tuple(written),
        unchanged_files=tuple(unchanged),
    )
