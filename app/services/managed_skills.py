"""Generic managed-skill registry, library seeding, and workspace installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


MANAGED_SKILL_MARKER = ".vo-managed.json"
MANAGED_BY = "virtual-office"
_SYNC_LOCK = threading.RLock()


@dataclass(frozen=True, slots=True)
class ManagedSkillDefinition:
    name: str
    content_loader: Callable[[], str]
    provider_kinds: frozenset[str] = frozenset({"openclaw"})
    legacy_names: tuple[str, ...] = ()
    legacy_content_validator: Callable[[str], bool] | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.name):
            raise ValueError("managed skill name is invalid")
        if not callable(self.content_loader):
            raise ValueError("managed skill content_loader is required")
        if not self.provider_kinds:
            raise ValueError("managed skill provider_kinds must not be empty")
        if len(set(self.legacy_names)) != len(self.legacy_names):
            raise ValueError("managed skill legacy names must be unique")

    def content(self) -> str:
        content = self.content_loader()
        if not isinstance(content, str) or not content.startswith("---"):
            raise ValueError(f"Canonical managed skill {self.name} has invalid content")
        match = re.search(r"(?m)^name:\s*([^\r\n]+)\s*$", content)
        declared = match.group(1).strip().strip("'\"") if match else ""
        if declared != self.name:
            raise ValueError(f"Canonical managed skill must declare name: {self.name}")
        return content


@dataclass(frozen=True, slots=True)
class ManagedSkillSeedResult:
    paths: Mapping[str, str]
    conflicts: tuple[str, ...]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _path_is_safe(workspace: Path, target: Path) -> bool:
    workspace = Path(os.path.realpath(workspace))
    lexical = Path(os.path.abspath(target))
    try:
        relative = lexical.relative_to(workspace)
    except ValueError:
        return False
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
        if os.path.lexists(current):
            try:
                Path(os.path.realpath(current)).relative_to(workspace)
            except ValueError:
                return False
    try:
        Path(os.path.realpath(lexical)).relative_to(workspace)
    except ValueError:
        return False
    return True


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _read_marker(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _legacy_is_removable(directory: Path, definition: ManagedSkillDefinition) -> bool:
    if directory.is_symlink() or not directory.is_dir():
        return False
    try:
        entries = sorted(item.name for item in directory.iterdir())
    except OSError:
        return False
    skill_path = directory / "SKILL.md"
    if entries != ["SKILL.md"] or skill_path.is_symlink() or not skill_path.is_file():
        return False
    validator = definition.legacy_content_validator
    return bool(validator and validator(_read_text(skill_path)))


def sync_managed_skill_to_workspace(
    definition: ManagedSkillDefinition,
    agent: Mapping[str, object],
    *,
    workspace_base: str | os.PathLike[str],
    marker_name: str = MANAGED_SKILL_MARKER,
) -> dict[str, object]:
    """Install one canonical skill without overwriting unowned conflicts."""
    if (
        not isinstance(agent, Mapping)
        or str(agent.get("providerKind") or "openclaw") not in definition.provider_kinds
    ):
        return {"ready": False, "status": "not_applicable", "updated": False}
    workspace_value = str(agent.get("workspace") or "").strip()
    base = Path(os.path.realpath(os.path.abspath(workspace_base)))
    workspace = Path(os.path.realpath(os.path.abspath(workspace_value))) if workspace_value else None
    if workspace is None:
        return {"ready": False, "status": "path_rejected", "updated": False}
    try:
        workspace.relative_to(base)
    except ValueError:
        return {"ready": False, "status": "path_rejected", "updated": False}
    if workspace == base:
        return {"ready": False, "status": "path_rejected", "updated": False}
    if not workspace.is_dir():
        return {"ready": False, "status": "workspace_missing", "updated": False}

    skill_directory = workspace / "skills" / definition.name
    skill_path = skill_directory / "SKILL.md"
    marker_path = skill_directory / marker_name
    legacy_directories = tuple(workspace / "skills" / name for name in definition.legacy_names)
    paths = (workspace / "skills", skill_directory, skill_path, marker_path)
    paths += tuple(path for directory in legacy_directories for path in (directory, directory / "SKILL.md"))
    if not all(_path_is_safe(workspace, path) for path in paths):
        return {"ready": False, "status": "path_rejected", "updated": False}

    content = definition.content()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    updated = False
    with _SYNC_LOCK:
        marker = _read_marker(marker_path)
        existing = _read_text(skill_path)
        managed = marker.get("managedBy") == MANAGED_BY and marker.get("skill") == definition.name
        if existing and not managed and existing != content:
            return {"ready": False, "status": "conflict", "updated": False}
        if existing != content:
            _atomic_write(skill_path, content)
            updated = True
        desired_marker = {"managedBy": MANAGED_BY, "sha256": digest, "skill": definition.name}
        if marker != desired_marker:
            _atomic_write(
                marker_path,
                json.dumps(desired_marker, sort_keys=True, indent=2) + "\n",
            )
            updated = True
        for legacy_directory in legacy_directories:
            if not os.path.lexists(legacy_directory):
                continue
            if not _legacy_is_removable(legacy_directory, definition):
                return {
                    "ready": False,
                    "status": "legacy_conflict",
                    "updated": updated,
                    "sha256": digest,
                }
            (legacy_directory / "SKILL.md").unlink()
            legacy_directory.rmdir()
            updated = True
    return {
        "ready": True,
        "status": "updated" if updated else "ready",
        "updated": updated,
        "sha256": digest,
    }


def seed_managed_skill_library(
    library_directory: str | os.PathLike[str],
    definitions: Sequence[ManagedSkillDefinition],
) -> ManagedSkillSeedResult:
    """Atomically seed canonical skills and remove only verified legacy directories."""
    library = Path(os.path.abspath(library_directory))
    if library.is_symlink():
        raise ValueError("managed skill library must not be a symbolic link")
    library.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    conflicts: list[str] = []
    with _SYNC_LOCK:
        for definition in definitions:
            content = definition.content()
            skill_directory = library / definition.name
            skill_path = skill_directory / "SKILL.md"
            if skill_directory.is_symlink() or skill_path.is_symlink():
                raise ValueError(f"managed skill library path is unsafe: {definition.name}")
            if _read_text(skill_path) != content:
                _atomic_write(skill_path, content)
            paths[definition.name] = str(skill_path)
            for legacy_name in definition.legacy_names:
                legacy_directory = library / legacy_name
                if not os.path.lexists(legacy_directory):
                    continue
                if not _legacy_is_removable(legacy_directory, definition):
                    conflicts.append(legacy_name)
                    continue
                (legacy_directory / "SKILL.md").unlink()
                legacy_directory.rmdir()
    return ManagedSkillSeedResult(paths=dict(paths), conflicts=tuple(sorted(conflicts)))
