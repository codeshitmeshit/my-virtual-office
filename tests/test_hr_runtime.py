"""HR application composition and late scheduler command wiring."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_runtime import HRCommandRouter
from services.hr_scheduler import HRCommandReceipt


class Commands:
    def __init__(self):
        self.calls = []

    def run(self):
        self.calls.append(("run", None))
        return HRCommandReceipt("run-1", "run", True)

    def close(self, cycle_id):
        self.calls.append(("close", cycle_id))
        return HRCommandReceipt("close-1", "close", True)

    def retry(self, cycle_id):
        self.calls.append(("retry", cycle_id))
        return HRCommandReceipt("retry-1", "retry", True)


def test_command_router_is_unavailable_until_commands_are_installed():
    router = HRCommandRouter()
    assert router.run().accepted is False
    assert router.close("cycle-1").accepted is False
    assert router.retry("cycle-1").accepted is False

    commands = Commands()
    router.install(commands)
    assert router.run().accepted is True
    assert router.close("cycle-1").accepted is True
    assert router.retry("cycle-1").accepted is True
    assert commands.calls == [
        ("run", None),
        ("close", "cycle-1"),
        ("retry", "cycle-1"),
    ]


def test_hr_http_and_runtime_modules_do_not_depend_on_legacy_server():
    for relative in (
        "services/hr_http.py",
        "services/hr_runtime.py",
        "services/hr_manual_daily_sync.py",
        "services/hr_command_status.py",
    ):
        source = (APP_DIR / relative).read_text(encoding="utf-8")
        assert "import server" not in source
        assert "OfficeHandler" not in source
