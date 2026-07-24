"""Startup-script and environment-template contracts for local Codex permissions."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
START_SCRIPT = ROOT / "start.sh"
DEFAULTS_SCRIPT = ROOT / "scripts" / "codex-env-defaults.sh"

CODEX_DEFAULTS = {
    "VO_CODEX_SANDBOX": "danger-full-access",
    "VO_CODEX_APPROVAL_POLICY": "never",
    "VO_CODEX_ROUTE_APPROVALS_THROUGH_VO": "false",
}


def _parse_env_template() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


def test_env_example_declares_local_codex_bypass_defaults():
    values = _parse_env_template()
    assert {name: values.get(name) for name in CODEX_DEFAULTS} == CODEX_DEFAULTS


def test_start_script_loads_and_applies_codex_defaults():
    script = START_SCRIPT.read_text(encoding="utf-8")
    assert 'source "$SCRIPT_DIR/scripts/codex-env-defaults.sh"' in script
    assert 'ensure_codex_env_defaults "$ENV_FILE"' in script
    assert "apply_codex_runtime_defaults" in script


def test_env_repair_preserves_explicit_codex_values_and_is_idempotent(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VO_CODEX_SANDBOX=workspace-write\nVO_CODEX_APPROVAL_POLICY=on-request\n",
        encoding="utf-8",
    )
    command = f'source "{DEFAULTS_SCRIPT}"; ensure_codex_env_defaults "$1"'

    subprocess.run(["bash", "-c", command, "codex-default-test", str(env_file)], check=True)
    first = env_file.read_text(encoding="utf-8")
    subprocess.run(["bash", "-c", command, "codex-default-test", str(env_file)], check=True)
    second = env_file.read_text(encoding="utf-8")

    assert first == second
    assert "VO_CODEX_SANDBOX=workspace-write\n" in first
    assert "VO_CODEX_APPROVAL_POLICY=on-request\n" in first
    assert "VO_CODEX_ROUTE_APPROVALS_THROUGH_VO=false\n" in first
    for name in CODEX_DEFAULTS:
        assert first.count(f"{name}=") == 1


def test_runtime_defaults_fill_unset_values_and_preserve_explicit_values():
    command = (
        f'source "{DEFAULTS_SCRIPT}"; '
        "unset VO_CODEX_SANDBOX VO_CODEX_APPROVAL_POLICY VO_CODEX_ROUTE_APPROVALS_THROUGH_VO; "
        "apply_codex_runtime_defaults; "
        "printf '%s|%s|%s' \"$VO_CODEX_SANDBOX\" \"$VO_CODEX_APPROVAL_POLICY\" "
        '"$VO_CODEX_ROUTE_APPROVALS_THROUGH_VO"'
    )
    result = subprocess.run(["bash", "-c", command], check=True, capture_output=True, text=True)
    assert result.stdout == "danger-full-access|never|false"

    command = (
        f'source "{DEFAULTS_SCRIPT}"; '
        "VO_CODEX_SANDBOX=read-only; VO_CODEX_APPROVAL_POLICY=on-request; "
        "VO_CODEX_ROUTE_APPROVALS_THROUGH_VO=true; apply_codex_runtime_defaults; "
        "printf '%s|%s|%s' \"$VO_CODEX_SANDBOX\" \"$VO_CODEX_APPROVAL_POLICY\" "
        '"$VO_CODEX_ROUTE_APPROVALS_THROUGH_VO"'
    )
    result = subprocess.run(["bash", "-c", command], check=True, capture_output=True, text=True)
    assert result.stdout == "read-only|on-request|true"
