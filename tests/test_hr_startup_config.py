"""Startup-script and environment-template contracts for Human Resources."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
START_SCRIPT = ROOT / "start.sh"
PAGE_MANAGED_HR_SETTINGS = {
    "VO_HR_ENABLED",
    "VO_HR_SCHEDULER_ENABLED",
    "VO_HR_TIMEZONE",
    "VO_HR_DAILY_TIME",
    "VO_HR_SUBMISSION_WINDOW_MINUTES",
    "VO_HR_MAX_WORKERS",
    "VO_HR_AGENT_TIMEOUT_SECONDS",
    "VO_HR_RETRY_LIMIT",
}


def _parse_env_template() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


def test_env_example_does_not_declare_page_managed_hr_defaults():
    values = _parse_env_template()
    assert PAGE_MANAGED_HR_SETTINGS.isdisjoint(values)


def test_start_script_does_not_write_or_export_page_managed_hr_defaults():
    script = START_SCRIPT.read_text(encoding="utf-8")
    assert 'source "$SCRIPT_DIR/scripts/hr-env-defaults.sh"' not in script
    assert "ensure_hr_env_defaults" not in script
    for name in PAGE_MANAGED_HR_SETTINGS:
        assert f"export {name}=" not in script
