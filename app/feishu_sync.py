"""Feishu message sync — tails Hermes gateway.log and parses feishu events.

Provides:
- FeishuLogTailer: async log tailer with inode+offset persistence
- FeishuEventBus: in-memory subscriber bus for parsed events
- Regex parsers for Hermes gateway.log feishu inbound/outbound lines
- Session export helper to fetch Hermes reply text
"""

import asyncio
import json
import os
import re
import sqlite3
import time
from collections import deque
from typing import Any, Callable


# ─── Regex parsers ────────────────────────────────────────────────

# Inbound: gateway.platforms.feishu: [Feishu] Inbound dm message received: id=om_xxx type=text chat_id=oc_xxx sender=user:ou_xxx text='xxx' media=0
_RE_INBOUND = re.compile(
    r"gateway\.platforms\.feishu:.*Inbound dm message received:"
    r"\s+id=(?P<message_id>\S+)"
    r"\s+type=(?P<msg_type>\S+)"
    r"\s+chat_id=(?P<chat_id>\S+)"
    r"\s+sender=(?P<sender>\S+)"
    r"\s+text='(?P<text>[^']*)'"
    r"(?:\s+media=(?P<media>\d))?",
)

# Response: gateway.run: response ready: platform=feishu chat=oc_xxx time=19.5s api_calls=4 response=595 chars
_RE_RESPONSE = re.compile(
    r"gateway\.run:.*response ready:"
    r"\s+platform=feishu"
    r"\s+chat=(?P<chat_id>\S+)"
    r"\s+time=(?P<time>[\d.]+)s"
    r"\s+api_calls=(?P<api_calls>\d+)"
    r"\s+response=(?P<chars>\d+)\s+chars",
)

# Sender display name from: sender=user:ou_xxx → extract username if possible
_RE_SENDER = re.compile(r"user:(?P<uid>\S+)")


def parse_inbound(line: str) -> dict[str, Any] | None:
    """Parse a feishu inbound log line. Returns event dict or None."""
    m = _RE_INBOUND.search(line)
    if not m:
        return None
    return {
        "type": "inbound",
        "message_id": m.group("message_id"),
        "chat_id": m.group("chat_id"),
        "sender": m.group("sender"),
        "text": m.group("text"),
        "msg_type": m.group("msg_type"),
        "media": m.group("media") or "0",
        "ts": int(time.time()),
    }


def parse_response(line: str) -> dict[str, Any] | None:
    """Parse a feishu response-ready log line. Returns event dict or None."""
    m = _RE_RESPONSE.search(line)
    if not m:
        return None
    return {
        "type": "response",
        "chat_id": m.group("chat_id"),
        "time_sec": float(m.group("time")),
        "api_calls": int(m.group("api_calls")),
        "chars": int(m.group("chars")),
        "ts": int(time.time()),
    }


def parse_feishu_line(line: str) -> dict[str, Any] | None:
    """Try parsing a log line as a feishu event. Returns event dict or None."""
    if "Inbound dm message received" in line:
        return parse_inbound(line)
    if "response ready" in line and "platform=feishu" in line:
        return parse_response(line)
    return None


# ─── Session export helper ────────────────────────────────────────

def _safe_json_loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _short_text(value: Any, max_len: int = 700) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    text = value.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def _tool_args_preview(arguments: Any) -> str:
    parsed = _safe_json_loads(arguments) if isinstance(arguments, str) else arguments
    if isinstance(parsed, dict):
        parts = []
        for key, value in parsed.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            parts.append(f"{key}={_short_text(value, 120)}")
        return ", ".join(parts)
    return _short_text(arguments, 400)


def _message_row_to_activity(row: sqlite3.Row) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    ts = int(float(row["timestamp"] or time.time()))
    row_id = row["id"]

    if row["role"] == "assistant":
        reasoning = (
            row["reasoning_content"]
            or row["reasoning"]
            or row["reasoning_details"]
            or ""
        )
        reasoning = _short_text(reasoning, 4000)
        if reasoning:
            events.append({
                "type": "thinking",
                "id": f"hermes-msg-{row_id}-thinking",
                "message_row_id": row_id,
                "text": reasoning,
                "ts": ts,
            })

        calls = _safe_json_loads(row["tool_calls"])
        if isinstance(calls, list):
            for idx, call in enumerate(calls):
                fn = call.get("function") if isinstance(call, dict) else {}
                name = (fn or {}).get("name") or call.get("name") or "tool"
                call_id = call.get("id") or call.get("call_id") or f"{row_id}:{idx}"
                arguments = (fn or {}).get("arguments") or call.get("arguments") or ""
                events.append({
                    "type": "tool_call",
                    "id": f"hermes-msg-{row_id}-call-{idx}",
                    "message_row_id": row_id,
                    "tool_call_id": call_id,
                    "tool_name": name,
                    "arguments": arguments,
                    "summary": _tool_args_preview(arguments),
                    "text": _short_text(row["content"], 300),
                    "ts": ts,
                })

    if row["role"] == "tool":
        events.append({
            "type": "tool_result",
            "id": f"hermes-msg-{row_id}-result",
            "message_row_id": row_id,
            "tool_call_id": row["tool_call_id"] or "",
            "tool_name": row["tool_name"] or "tool",
            "text": _short_text(row["content"], 900),
            "ts": ts,
        })

    return events


def fetch_latest_feishu_reply(chat_id: str, hermes_home: str = "/root/.hermes") -> str | None:
    """Query Hermes state.db for the latest assistant reply from Feishu traffic."""
    hermes_home = os.path.expanduser(hermes_home)
    db_path = os.path.join(hermes_home, "state.db")
    if not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute(
            "SELECT content FROM messages "
            "JOIN sessions ON sessions.id = messages.session_id "
            "WHERE sessions.source = 'feishu' "
            "AND messages.role = 'assistant' "
            "AND messages.content IS NOT NULL AND messages.content != '' "
            "ORDER BY messages.id DESC LIMIT 1"
        )
        msg_row = c.fetchone()
        conn.close()

        if msg_row and msg_row[0] and msg_row[0].strip():
            return msg_row[0].strip()
        return None
    except Exception:
        return None


def fetch_latest_feishu_message_id(hermes_home: str = "/root/.hermes") -> int:
    hermes_home = os.path.expanduser(hermes_home)
    db_path = os.path.join(hermes_home, "state.db")
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(messages.id), 0) "
            "FROM messages JOIN sessions ON sessions.id = messages.session_id "
            "WHERE sessions.source = 'feishu'"
        )
        row = cur.fetchone()
        conn.close()
        return int(row[0] or 0)
    except Exception:
        return 0


def fetch_feishu_activity_since(hermes_home: str = "/root/.hermes", last_message_id: int = 0, limit: int = 80) -> tuple[list[dict[str, Any]], int]:
    hermes_home = os.path.expanduser(hermes_home)
    db_path = os.path.join(hermes_home, "state.db")
    if not os.path.exists(db_path):
        return [], last_message_id
    max_id = last_message_id
    events: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT messages.* "
            "FROM messages JOIN sessions ON sessions.id = messages.session_id "
            "WHERE sessions.source = 'feishu' AND messages.id > ? "
            "ORDER BY messages.id ASC LIMIT ?",
            (int(last_message_id or 0), max(1, min(int(limit or 80), 500))),
        )
        for row in cur.fetchall():
            max_id = max(max_id, int(row["id"]))
            events.extend(_message_row_to_activity(row))
        conn.close()
    except Exception:
        return [], last_message_id
    return events, max_id


def fetch_recent_feishu_activity(hermes_home: str = "/root/.hermes", limit: int = 40) -> list[dict[str, Any]]:
    hermes_home = os.path.expanduser(hermes_home)
    db_path = os.path.join(hermes_home, "state.db")
    if not os.path.exists(db_path):
        return []
    events: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT messages.* "
            "FROM messages JOIN sessions ON sessions.id = messages.session_id "
            "WHERE sessions.source = 'feishu' "
            "ORDER BY messages.id DESC LIMIT ?",
            (max(1, min(int(limit or 40), 300)),),
        )
        rows = list(reversed(cur.fetchall()))
        conn.close()
        for row in rows:
            events.extend(_message_row_to_activity(row))
    except Exception:
        return []
    return events[-limit:]


def fetch_latest_feishu_turn_activity(hermes_home: str = "/root/.hermes") -> list[dict[str, Any]]:
    """Return activity generated after the newest Feishu user message."""
    hermes_home = os.path.expanduser(hermes_home)
    db_path = os.path.join(hermes_home, "state.db")
    if not os.path.exists(db_path):
        return []
    events: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(messages.id), 0) "
            "FROM messages JOIN sessions ON sessions.id = messages.session_id "
            "WHERE sessions.source = 'feishu' AND messages.role = 'user'"
        )
        latest_user_id = int((cur.fetchone() or [0])[0] or 0)
        if latest_user_id:
            cur.execute(
                "SELECT messages.* "
                "FROM messages JOIN sessions ON sessions.id = messages.session_id "
                "WHERE sessions.source = 'feishu' AND messages.id > ? "
                "ORDER BY messages.id ASC",
                (latest_user_id,),
            )
            for row in cur.fetchall():
                events.extend(_message_row_to_activity(row))
        conn.close()
    except Exception:
        return []
    return events


def fetch_recent_feishu_log_events(log_path: str = "/root/.hermes/logs/gateway.log", hermes_home: str = "/root/.hermes", limit: int = 30) -> list[dict[str, Any]]:
    hermes_home = os.path.expanduser(hermes_home)
    log_path = os.path.expanduser(log_path)
    if not os.path.exists(log_path):
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-1000:]
    except OSError:
        return []
    for line in lines:
        event = parse_feishu_line(line)
        if event:
            if event["type"] == "response":
                reply_text = fetch_latest_feishu_reply(event.get("chat_id", ""), hermes_home)
                event["text"] = reply_text[:500] if reply_text else f"(回复 {event['chars']} 字符，内容未获取)"
                event["truncated"] = bool(reply_text and len(reply_text) > 500)
            events.append(event)
    return events[-limit:]


# ─── State persistence ────────────────────────────────────────────

def _default_state_path(data_dir: str | None = None) -> str:
    """Return path to feishu-sync-state.json."""
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "feishu-sync-state.json")


def load_sync_state(state_path: str | None = None) -> dict[str, Any]:
    """Load last known inode and offset."""
    path = state_path or _default_state_path()
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"inode": 0, "offset": 0, "last_seen_at": ""}


def save_sync_state(state: dict[str, Any], state_path: str | None = None) -> None:
    """Persist inode and offset."""
    path = state_path or _default_state_path()
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass


# ─── Event bus ────────────────────────────────────────────────────

class FeishuEventBus:
    """Simple pub-sub bus for feishu events. Subscribers get async callbacks."""

    def __init__(self):
        self._subscribers: list[Callable] = []
        self._recent_events = deque(maxlen=200)
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    def subscribe(self, callback: Callable) -> None:
        """Register an async callback that receives event dicts."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        """Remove a subscriber."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def publish(self, event: dict[str, Any]) -> None:
        """Dispatch event to all subscribers."""
        self._recent_events.append(event)
        for cb in list(self._subscribers):
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(f"[FEISHU-SYNC] subscriber error: {e}")

    def recent_events(self, limit: int = 80) -> list[dict[str, Any]]:
        count = max(1, min(int(limit or 80), self._recent_events.maxlen or 200))
        return list(self._recent_events)[-count:]


# ─── Log tailer ───────────────────────────────────────────────────

class FeishuLogTailer:
    """Tails Hermes gateway.log, parses feishu events, publishes to EventBus.

    Supports:
    - Resume from saved inode+offset
    - File rotation detection (inode change → restart from offset 0)
    - Graceful handling of missing file
    """

    def __init__(
        self,
        log_path: str | None = None,
        event_bus: FeishuEventBus | None = None,
        state_path: str | None = None,
        hermes_home: str | None = None,
    ):
        self.hermes_home = os.path.expanduser(hermes_home or "/root/.hermes")
        self.log_path = os.path.expanduser(log_path or os.path.join(self.hermes_home, "logs", "gateway.log"))
        self.event_bus = event_bus or FeishuEventBus()
        self.state_path = state_path or _default_state_path()
        self._running = False
        self._state = load_sync_state(self.state_path)
        self._last_message_id = int(self._state.get("last_message_id") or 0)

    @property
    def running(self) -> bool:
        return self._running

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task:
        """Start tailing in the event loop. Returns the asyncio.Task."""
        target_loop = loop or asyncio.get_event_loop()
        self._running = True
        if not self._last_message_id:
            self._last_message_id = fetch_latest_feishu_message_id(self.hermes_home)
            self._state["last_message_id"] = self._last_message_id
            save_sync_state(self._state, self.state_path)
        task = target_loop.create_task(self._tail_loop())
        msg = f"[FEISHU-SYNC] started, watching {self.log_path}"
        print(msg, flush=True)
        return task

    async def stop(self) -> None:
        """Stop the tailer and persist state."""
        self._running = False
        save_sync_state(self._state, self.state_path)
        print(f"[FEISHU-SYNC] stopped, state saved", flush=True)

    async def _tail_loop(self) -> None:
        """Main polling loop: check for new lines, parse, publish."""
        poll_interval = 0.5  # seconds — sub-second for near-real-time
        backoff = 1.0
        max_backoff = 10.0

        while self._running:
            try:
                got_new = await self._read_new_lines()
                got_activity = await self._poll_hermes_activity()
                if got_new:
                    backoff = 1.0  # reset backoff on success
                await asyncio.sleep(poll_interval)
            except Exception as e:
                print(f"[FEISHU-SYNC] tail loop error: {e}", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, max_backoff)

    async def _read_new_lines(self) -> bool:
        """Read new lines since last offset. Returns True if any line parsed."""
        if not os.path.exists(self.log_path):
            return False

        try:
            stat = os.stat(self.log_path)
        except OSError:
            return False

        current_inode = stat.st_ino
        saved_inode = self._state.get("inode", 0)
        saved_offset = self._state.get("offset", 0)

        # Detect file rotation: inode changed → reset to start of new file
        if current_inode != saved_inode:
            print(f"[FEISHU-SYNC] file rotated (inode {saved_inode} → {current_inode}), resetting", flush=True)
            saved_offset = 0
            self._state["inode"] = current_inode
            self._state["offset"] = 0

        # Also detect if file shrank (truncated)
        if stat.st_size < saved_offset:
            print(f"[FEISHU-SYNC] file truncated ({stat.st_size} < {saved_offset}), resetting", flush=True)
            saved_offset = 0

        if saved_offset >= stat.st_size:
            return False  # nothing new

        had_event = False
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(saved_offset)
                while self._running:
                    line = f.readline()
                    if not line or line.endswith("\n") is False and f.tell() >= stat.st_size:
                        break
                    if not line.strip():
                        continue
                    pos = f.tell()
                    event = parse_feishu_line(line)
                    if event:
                        had_event = True
                        # Enrich response events with actual reply text from session export
                        if event["type"] == "response":
                            chat_id = event.get("chat_id", "")
                            reply_text = await asyncio.to_thread(fetch_latest_feishu_reply, chat_id)
                            if reply_text:
                                event["text"] = reply_text[:500]  # cap for display
                                event["truncated"] = len(reply_text) > 500
                            else:
                                event["text"] = f"(回复 {event['chars']} 字符，内容未获取)"
                        print(f"[FEISHU-SYNC] parsed {event['type']}: {event.get('text', '')[:80]}", flush=True)
                        await self.event_bus.publish(event)
                    saved_offset = pos

            self._state["inode"] = current_inode
            self._state["offset"] = saved_offset
            self._state["last_seen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            save_sync_state(self._state, self.state_path)
        except OSError as e:
            print(f"[FEISHU-SYNC] read error: {e}", flush=True)
            return False

        return had_event

    async def _poll_hermes_activity(self) -> bool:
        events, last_id = await asyncio.to_thread(
            fetch_feishu_activity_since,
            self.hermes_home,
            self._last_message_id,
        )
        if last_id != self._last_message_id:
            self._last_message_id = last_id
            self._state["last_message_id"] = last_id
            save_sync_state(self._state, self.state_path)
        for event in events:
            print(f"[FEISHU-SYNC] parsed {event['type']}: {event.get('tool_name', '')}", flush=True)
            await self.event_bus.publish(event)
        return bool(events)
