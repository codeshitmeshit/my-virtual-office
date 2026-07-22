"""Claude Code environment helpers.

Only known Claude/provider variables are imported from user shell rc files.
Values are used for subprocess execution, while public diagnostics expose names
only.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Any


CLAUDE_THIRD_PARTY_ENV_NAMES = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "MOONSHOT_API_KEY",
    "MOONSHOT_BASE_URL",
    "KIMI_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_BASE_URL",
    "QWEN_API_KEY",
    "ZHIPUAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "ANTHROPIC_VERTEX_REGION",
}

CLAUDE_THIRD_PARTY_CREDENTIAL_ENV_NAMES = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "MOONSHOT_API_KEY",
    "KIMI_API_KEY",
    "DASHSCOPE_API_KEY",
    "QWEN_API_KEY",
    "ZHIPUAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_PROFILE",
    "GOOGLE_APPLICATION_CREDENTIALS",
}

_ASSIGNMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHELL_RC_FILES = (".bashrc", ".zshrc", ".profile")


def merge_user_claude_env(env: dict[str, str], home_path: str | None = None) -> dict[str, str]:
    """Return env plus missing Claude provider variables from user rc files."""
    merged = dict(env)
    for rc_path in _candidate_rc_paths(merged, home_path):
        for name, value in _read_known_assignments(rc_path).items():
            if str(merged.get(name) or "").strip():
                continue
            merged[name] = value
    return merged


def third_party_env_auth(env: dict[str, str]) -> dict[str, Any]:
    configured = sorted(
        name
        for name in CLAUDE_THIRD_PARTY_ENV_NAMES
        if str(env.get(name) or "").strip()
    )
    credential_names = [
        name
        for name in configured
        if name in CLAUDE_THIRD_PARTY_CREDENTIAL_ENV_NAMES
    ]
    if not credential_names and "CLAUDE_CODE_USE_BEDROCK" in configured:
        credential_names = [
            name
            for name in configured
            if name in {"AWS_REGION", "AWS_DEFAULT_REGION"}
        ]
    if not credential_names and "CLAUDE_CODE_USE_VERTEX" in configured:
        credential_names = [
            name
            for name in configured
            if name in {"GOOGLE_CLOUD_PROJECT", "ANTHROPIC_VERTEX_PROJECT_ID"}
        ]
    return {
        "authConfigured": bool(credential_names),
        "configuredEnv": configured,
    }


def _candidate_rc_paths(env: dict[str, str], home_path: str | None) -> list[str]:
    homes: list[str] = []
    if home_path:
        expanded = os.path.abspath(os.path.expanduser(home_path))
        if os.path.basename(expanded.rstrip(os.sep)) == ".claude":
            homes.append(os.path.dirname(expanded.rstrip(os.sep)))
    homes.append(env.get("HOME") or "")

    paths: list[str] = []
    seen: set[str] = set()
    for home in homes:
        if not home:
            continue
        for rc_name in _SHELL_RC_FILES:
            path = os.path.abspath(os.path.join(os.path.expanduser(home), rc_name))
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
    return paths


def _read_known_assignments(path: str) -> dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = list(f)
    except OSError:
        return {}

    values: dict[str, str] = {}
    for raw in lines:
        for name, value in _parse_assignment_line(raw).items():
            if name in CLAUDE_THIRD_PARTY_ENV_NAMES and value.strip():
                values[name] = value
    return values


def _parse_assignment_line(line: str) -> dict[str, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return {}
    if stripped.startswith("export "):
        stripped = stripped[len("export "):].strip()
    elif "=" not in stripped:
        return {}
    try:
        parts = shlex.split(stripped, comments=True, posix=True)
    except ValueError:
        return {}

    values: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        if _ASSIGNMENT_NAME.match(name or ""):
            values[name] = value
    return values
