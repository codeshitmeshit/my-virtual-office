"""Guarded configuration and runtime primitives for the Codex chat fast path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class CodexFastPathSettings:
    requested_enabled: bool = False
    enabled: bool = False
    valid: bool = True
    max_concurrent_turns: int = 1
    coalesce_min_ms: int = 33
    coalesce_max_ms: int = 100
    issues: tuple[str, ...] = ()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "requestedEnabled": self.requested_enabled,
            "enabled": self.enabled,
            "valid": self.valid,
            "startupOnly": True,
            "maxConcurrentTurns": self.max_concurrent_turns,
            "streamCoalesceMinMs": self.coalesce_min_ms,
            "streamCoalesceMaxMs": self.coalesce_max_ms,
            "issues": list(self.issues),
        }


def _configured_value(environ: Mapping[str, Any], env_key: str, config: Mapping[str, Any], config_key: str, default: Any):
    raw = environ.get(env_key)
    if raw is not None and str(raw).strip() != "":
        return raw
    return config.get(config_key, default)


def _strict_bool(value: Any, default: bool, issue: str, issues: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    issues.append(issue)
    return default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int, issue: str, issues: list[str]) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        issues.append(issue)
        return default
    if parsed < minimum or parsed > maximum:
        issues.append(issue)
        return default
    return parsed


def load_codex_fast_path_settings(environ: Mapping[str, Any], codex_config: Mapping[str, Any] | None = None) -> CodexFastPathSettings:
    codex_config = codex_config if isinstance(codex_config, Mapping) else {}
    nested = codex_config.get("fastPath")
    fast_config = nested if isinstance(nested, Mapping) else codex_config
    issues: list[str] = []
    requested_enabled = _strict_bool(
        _configured_value(environ, "VO_CODEX_CHAT_FAST_PATH_ENABLED", fast_config, "enabled", False),
        False,
        "invalid_enabled",
        issues,
    )
    max_turns = _bounded_int(
        _configured_value(environ, "VO_CODEX_MAX_CONCURRENT_TURNS", fast_config, "maxConcurrentTurns", 1),
        1,
        1,
        4,
        "invalid_max_concurrent_turns",
        issues,
    )
    minimum_ms = _bounded_int(
        _configured_value(environ, "VO_CODEX_STREAM_COALESCE_MIN_MS", fast_config, "streamCoalesceMinMs", 33),
        33,
        33,
        100,
        "invalid_coalesce_min_ms",
        issues,
    )
    maximum_ms = _bounded_int(
        _configured_value(environ, "VO_CODEX_STREAM_COALESCE_MAX_MS", fast_config, "streamCoalesceMaxMs", 100),
        100,
        33,
        100,
        "invalid_coalesce_max_ms",
        issues,
    )
    if maximum_ms < minimum_ms:
        issues.append("invalid_coalesce_window")
        minimum_ms, maximum_ms = 33, 100
    valid = not issues
    return CodexFastPathSettings(
        requested_enabled=requested_enabled,
        enabled=requested_enabled and valid,
        valid=valid,
        max_concurrent_turns=max_turns,
        coalesce_min_ms=minimum_ms,
        coalesce_max_ms=maximum_ms,
        issues=tuple(dict.fromkeys(issues)),
    )
