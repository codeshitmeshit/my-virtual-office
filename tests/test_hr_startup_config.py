"""Startup-script and environment-template contracts for Human Resources."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
START_SCRIPT = ROOT / "start.sh"
DEFAULTS_SCRIPT = ROOT / "scripts" / "hr-env-defaults.sh"

HR_DEFAULTS = {
    "VO_HR_ENABLED": "true",
    "VO_HR_SCHEDULER_ENABLED": "false",
    "VO_HR_TIMEZONE": "",
    "VO_HR_DAILY_TIME": "18:00",
    "VO_HR_SUBMISSION_WINDOW_MINUTES": "120",
    "VO_HR_MAX_WORKERS": "2",
    "VO_HR_AGENT_TIMEOUT_SECONDS": "30",
    "VO_HR_RETRY_LIMIT": "3",
}


def _parse_env_template() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


def test_env_example_declares_every_safe_hr_default():
    values = _parse_env_template()
    assert {name: values.get(name) for name in HR_DEFAULTS} == HR_DEFAULTS


def test_start_script_loads_repair_module_with_hr_enabled_and_scheduler_disabled():
    script = START_SCRIPT.read_text(encoding="utf-8")
    assert 'source "$SCRIPT_DIR/scripts/hr-env-defaults.sh"' in script
    assert 'ensure_hr_env_defaults "$ENV_FILE"' in script
    assert 'export VO_HR_ENABLED="${VO_HR_ENABLED:-true}"' in script
    assert 'export VO_HR_SCHEDULER_ENABLED="${VO_HR_SCHEDULER_ENABLED:-false}"' in script
    assert 'export VO_HR_TIMEZONE="${VO_HR_TIMEZONE:-${VO_TIMEZONE:-${TZ:-UTC}}}"' in script


def test_start_script_exports_every_bounded_hr_runtime_setting():
    script = START_SCRIPT.read_text(encoding="utf-8")
    for name, value in HR_DEFAULTS.items():
        if name == "VO_HR_TIMEZONE":
            continue
        assert f'export {name}="${{{name}:-{value}}}"' in script


def test_env_repair_preserves_existing_values_and_is_idempotent(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("VO_HR_ENABLED=false\nVO_HR_DAILY_TIME=09:30\n", encoding="utf-8")
    command = f'source "{DEFAULTS_SCRIPT}"; ensure_hr_env_defaults "$1"'

    subprocess.run(["bash", "-c", command, "hr-default-test", str(env_file)], check=True)
    first = env_file.read_text(encoding="utf-8")
    subprocess.run(["bash", "-c", command, "hr-default-test", str(env_file)], check=True)
    second = env_file.read_text(encoding="utf-8")

    assert first == second
    assert first.count("# Human Resources (safe rollout defaults)") == 1
    assert "VO_HR_ENABLED=false\n" in first
    assert "VO_HR_DAILY_TIME=09:30\n" in first
    for name, value in HR_DEFAULTS.items():
        assert first.count(f"{name}=") == 1
        if name not in {"VO_HR_ENABLED", "VO_HR_DAILY_TIME"}:
            assert f"{name}={value}\n" in first
