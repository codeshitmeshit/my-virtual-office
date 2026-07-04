#!/usr/bin/env python3
"""Dashboard realtime event stream helpers.

This module owns the dashboard SSE payload shaping and stream loop so the main
server only needs thin route wiring.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable


JsonDict = dict[str, Any]


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _signature(value: Any) -> str:
    return hashlib.sha1(_stable_json(value).encode("utf-8")).hexdigest()


def _agent_status_projection(status: JsonDict) -> JsonDict:
    counts = {"working": 0, "idle": 0, "meeting": 0, "break": 0}
    agents: dict[str, JsonDict] = {}
    meetings = status.get("_meetings") if isinstance(status.get("_meetings"), list) else []
    meeting_agents = set()
    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue
        for agent_id in meeting.get("agents") or meeting.get("participants") or []:
            if agent_id:
                meeting_agents.add(str(agent_id))

    for key, entry in status.items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        state = str(entry.get("state") or "idle")
        if key in meeting_agents:
            state = "meeting"
        if state not in counts:
            state = "idle" if state in {"finishing", "available"} else state
        if state in counts:
            counts[state] += 1
        agents[key] = {
            "state": state,
            "task": str(entry.get("task") or ""),
            "thought": str(entry.get("thought") or ""),
            "speech": str(entry.get("speech") or ""),
            "speechTarget": str(entry.get("speechTarget") or ""),
            "notify": bool(entry.get("notify")),
            "lastInput": entry.get("lastInput") if isinstance(entry.get("lastInput"), dict) else None,
            "lastOutput": entry.get("lastOutput") if isinstance(entry.get("lastOutput"), dict) else None,
        }

    return {"counts": counts, "agents": agents, "meetings": meetings}


def _meeting_summary_projection(meetings: list[Any], requests: list[Any]) -> JsonDict:
    active = [m for m in meetings if isinstance(m, dict)]
    pending = [r for r in requests if isinstance(r, dict) and r.get("status") == "pending"]
    return {
        "active": active,
        "pendingRequests": pending,
        "activeCount": len(active),
        "pendingRequestCount": len(pending),
    }


def _action_required_items(meetings: list[Any], requests: list[Any]) -> list[JsonDict]:
    items: list[JsonDict] = []
    for req in requests:
        if not isinstance(req, dict) or req.get("status") != "pending":
            continue
        title = req.get("goal") or req.get("title") or req.get("expectedOutcome") or "AI meeting request"
        items.append({
            "id": f"meeting-request:{req.get('id')}",
            "type": "meeting_request_pending",
            "severity": "attention",
            "title": "Meeting request needs confirmation",
            "text": str(title),
            "meetingRequestId": req.get("id") or "",
            "projectId": (req.get("source") or {}).get("projectId") if isinstance(req.get("source"), dict) else "",
            "taskId": (req.get("source") or {}).get("taskId") if isinstance(req.get("source"), dict) else "",
        })

    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue
        meeting_id = meeting.get("id") or ""
        topic = meeting.get("topic") or "Untitled meeting"
        for conflict in meeting.get("conflicts") or []:
            if not isinstance(conflict, dict):
                continue
            if conflict.get("status") in {"resolved", "cancelled", "closed"}:
                continue
            items.append({
                "id": f"meeting-conflict:{meeting_id}:{conflict.get('id') or conflict.get('agentId')}",
                "type": "meeting_conflict",
                "severity": "attention",
                "title": "Meeting participant conflict",
                "text": str(topic),
                "meetingId": meeting_id,
                "agentId": conflict.get("agentId") or "",
            })
        for call in meeting.get("pendingCalls") or []:
            if isinstance(call, dict) and call.get("timedOut"):
                items.append({
                    "id": f"provider-timeout:{meeting_id}:{call.get('sequence')}",
                    "type": "provider_timeout",
                    "severity": "warning",
                    "title": "Meeting provider call timed out",
                    "text": str(topic),
                    "meetingId": meeting_id,
                    "agentId": call.get("speaker") or "",
                })
        if meeting.get("stage") == "awaiting_user_decision":
            reason = (meeting.get("arbitration") or {}).get("reason") if isinstance(meeting.get("arbitration"), dict) else ""
            items.append({
                "id": f"meeting-user-decision:{meeting_id}:{meeting.get('decisionForStage') or ''}:{meeting.get('decisionForRound') or 0}",
                "type": "meeting_user_decision",
                "severity": "attention",
                "title": "Meeting needs user decision",
                "text": str(reason or topic),
                "meetingId": meeting_id,
            })
        if meeting.get("moderatorFailure"):
            items.append({
                "id": f"meeting-moderator-failure:{meeting_id}",
                "type": "meeting_failure",
                "severity": "warning",
                "title": "Meeting moderator failed",
                "text": str(topic),
                "meetingId": meeting_id,
            })
    return sorted(items, key=lambda item: (item.get("type", ""), item.get("id", "")))


def build_dashboard_snapshot(status: JsonDict, meetings: list[Any], requests: list[Any]) -> JsonDict:
    status_projection = _agent_status_projection(status if isinstance(status, dict) else {})
    meeting_projection = _meeting_summary_projection(meetings if isinstance(meetings, list) else [], requests if isinstance(requests, list) else [])
    actions = _action_required_items(meeting_projection["active"], meeting_projection["pendingRequests"])
    snapshot = {
        "ts": int(time.time() * 1000),
        "status": status_projection,
        "meetings": meeting_projection,
        "actions": actions,
    }
    snapshot["signatures"] = {
        "status": _signature(status_projection),
        "meetings": _signature(meeting_projection),
        "actions": _signature(actions),
    }
    return snapshot


def diff_dashboard_events(previous: JsonDict | None, current: JsonDict) -> list[tuple[str, JsonDict]]:
    if not previous:
        return [("dashboard.snapshot", current)]
    events: list[tuple[str, JsonDict]] = []
    prev_sig = previous.get("signatures") or {}
    curr_sig = current.get("signatures") or {}
    if prev_sig.get("status") != curr_sig.get("status"):
        events.append(("dashboard.status", {"ts": current.get("ts"), "status": current.get("status"), "signature": curr_sig.get("status")}))
    if prev_sig.get("meetings") != curr_sig.get("meetings"):
        events.append(("dashboard.meetings", {"ts": current.get("ts"), "meetings": current.get("meetings"), "signature": curr_sig.get("meetings")}))
    if prev_sig.get("actions") != curr_sig.get("actions"):
        events.append(("dashboard.actions", {"ts": current.get("ts"), "actions": current.get("actions"), "signature": curr_sig.get("actions")}))
    return events


@dataclass
class DashboardRealtimeStream:
    status_loader: Callable[[], JsonDict]
    meetings_loader: Callable[[], list[Any]]
    requests_loader: Callable[[], list[Any]]
    interval_sec: float = 1.0
    heartbeat_sec: float = 15.0

    def snapshot(self) -> JsonDict:
        return build_dashboard_snapshot(
            self.status_loader() or {},
            self.meetings_loader() or [],
            self.requests_loader() or [],
        )

    def _send_event(self, handler: Any, event_name: str, payload: JsonDict) -> bool:
        try:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            handler.wfile.write(f"event: {event_name}\ndata: {encoded}\n\n".encode("utf-8"))
            handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def stream(self, handler: Any) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()

        previous: JsonDict | None = None
        last_heartbeat = 0.0
        while True:
            try:
                current = self.snapshot()
                for event_name, payload in diff_dashboard_events(previous, current):
                    if not self._send_event(handler, event_name, payload):
                        return
                previous = current
                now = time.time()
                if now - last_heartbeat >= self.heartbeat_sec:
                    if not self._send_event(handler, "dashboard.heartbeat", {"ts": int(now * 1000)}):
                        return
                    last_heartbeat = now
                time.sleep(max(0.2, self.interval_sec))
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            except Exception as exc:  # keep the stream self-reporting instead of silently dying
                if not self._send_event(handler, "dashboard.error", {"ts": int(time.time() * 1000), "error": str(exc)}):
                    return
                time.sleep(max(1.0, self.interval_sec))
