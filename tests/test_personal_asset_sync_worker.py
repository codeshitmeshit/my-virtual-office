import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.personal_asset_sync_worker import PersonalAssetSyncWorker  # noqa: E402


def test_worker_wake_is_non_blocking_and_exceptions_do_not_kill_loop():
    calls = []
    completed = threading.Event()

    def run_once():
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise RuntimeError("transient")
        completed.set()

    worker = PersonalAssetSyncWorker(run_once, retry_interval=60)
    worker.start()
    try:
        worker.wake()
        for _index in range(20):
            if calls:
                break
            threading.Event().wait(0.01)
        worker.wake()
        assert completed.wait(1)
        assert calls == [1, 2]
    finally:
        worker.stop()
