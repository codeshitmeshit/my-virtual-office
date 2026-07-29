"""Rollout configuration for Skills Library smart organization."""

from __future__ import annotations

import os


ENV_NAME = "VO_SKILL_LIBRARY_ORGANIZATION_ENABLED"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})


def is_enabled(environ: dict[str, str] | None = None) -> bool:
    """Return whether new organization runs may be started."""

    source = os.environ if environ is None else environ
    return str(source.get(ENV_NAME) or "").strip().lower() in _TRUE_VALUES
