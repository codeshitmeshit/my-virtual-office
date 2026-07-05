#!/usr/bin/env python3
"""Feishu chat long-connection worker process.

Runs the Feishu/Lark SDK websocket client in a separate Python interpreter so
multiple Feishu apps do not share the SDK module-level asyncio loop.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from typing import Any

from feishu_long_connection import FeishuLongConnectionReceiver


def _status_path() -> str:
    status_dir = os.environ.get("VO_STATUS_DIR") or os.path.join(os.getcwd(), "data")
    return os.path.join(status_dir, "feishu-chat-worker-status.json")


def _write_status(**updates: Any) -> None:
    payload = {
        "enabled": True,
        "running": False,
        "status": "starting",
        "pid": os.getpid(),
        "updatedAt": int(time.time()),
        "lastEventAt": 0,
        "lastError": "",
    }
    payload.update(updates)
    try:
        os.makedirs(os.path.dirname(_status_path()), exist_ok=True)
        with open(_status_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True)
    except Exception:
        pass


def _callback_url() -> str:
    return (os.environ.get("VO_FEISHU_CHAT_WORKER_CALLBACK_URL") or "http://127.0.0.1:8090/api/feishu-chat/inbound-worker").strip()


def _post_message(body: dict[str, Any]) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _callback_url(),
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-VO-Feishu-Chat-Worker-Token": os.environ.get("VO_FEISHU_CHAT_WORKER_TOKEN") or "",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(4096)
            if resp.status >= 300:
                raise RuntimeError(f"callback status {resp.status}: {raw[:200]!r}")
        _write_status(running=True, status="running", lastEventAt=int(time.time()), lastError="")
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096)
        _write_status(running=True, status="callback_error", lastError=f"HTTPError {exc.code}: {detail[:200]!r}")
    except Exception as exc:
        _write_status(running=True, status="callback_error", lastError=f"{type(exc).__name__}: {exc}")


def main() -> int:
    app_id = (os.environ.get("VO_FEISHU_CHAT_APP_ID") or "").strip()
    app_secret = (os.environ.get("VO_FEISHU_CHAT_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        _write_status(enabled=False, running=False, status="missing_app_credentials")
        return 2

    _write_status(running=True, status="starting", lastError="")
    receiver = FeishuLongConnectionReceiver(
        app_id=app_id,
        app_secret=app_secret,
        message_handler=_post_message,
        name="feishu-chat-worker-long-connection",
    )
    try:
        status = receiver.start()
        _write_status(**status, pid=os.getpid())
        while True:
            current = receiver.status()
            _write_status(**current, pid=os.getpid())
            if current.get("running") is False and current.get("status") not in {"starting", "connecting", "running"}:
                return 1
            time.sleep(5)
    except KeyboardInterrupt:
        receiver.stop()
        _write_status(enabled=False, running=False, status="stopped")
        return 0
    except Exception as exc:
        _write_status(
            enabled=False,
            running=False,
            status="error",
            lastError=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(limit=5),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
