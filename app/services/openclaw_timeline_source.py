"""Bounded OpenClaw session source for Project Execution timelines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .conversation_timeline import ConversationTimelineService, TimelineScope
from .conversation_timeline_sources import normalize_source_record, project_workflow_history


TAIL_BYTES = 256 * 1024


def _tool_summary(tool: Mapping[str, Any]) -> str:
    name = str(tool.get("name") or "?")
    arguments = tool.get("arguments") if isinstance(tool.get("arguments"), Mapping) else {}
    if name.lower() == "read" and (arguments.get("file") or arguments.get("path") or arguments.get("file_path")):
        value = str(arguments.get("file") or arguments.get("path") or arguments.get("file_path"))
        return f"Reading {value.rsplit('/', 1)[-1]}"
    if name.lower() == "edit":
        value = str(arguments.get("file") or arguments.get("path") or arguments.get("file_path") or "")
        return f"Editing {value.rsplit('/', 1)[-1]}"
    if name.lower() == "write":
        value = str(arguments.get("file") or arguments.get("path") or arguments.get("file_path") or "")
        return f"Writing {value.rsplit('/', 1)[-1]}"
    if name == "exec":
        command = str(arguments.get("command") or "")
        return f"Running: {command[:80]}" if command else "exec"
    if name == "web_search":
        query = str(arguments.get("query") or "")
        return f"Searching: {query[:60]}" if query else "web_search"
    if name == "web_fetch":
        url = str(arguments.get("url") or "")
        return f"Fetching: {url[:60]}" if url else "web_fetch"
    if name == "browser":
        action = str(arguments.get("action") or "")
        return f"Browser: {action}" if action else "browser"
    if name == "sessions_send":
        target = str(arguments.get("sessionKey") or arguments.get("label") or "")
        return f"Messaging: {target[:40]}" if target else "sessions_send"
    return name


class OpenClawWorkflowTimelineSource:
    def __init__(
        self,
        timeline: ConversationTimelineService,
        sessions_dir: str | Path,
        resolve_session: Callable[[Mapping[str, Any], str, str], Mapping[str, Any] | None],
    ) -> None:
        self._timeline = timeline
        self._sessions_dir = Path(sessions_dir).resolve()
        self._resolve_session = resolve_session

    def _session_info(self, agent_id: str, session_key: str) -> Mapping[str, Any] | None:
        try:
            data = json.loads((self._sessions_dir / "sessions.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, Mapping):
            return None
        info = self._resolve_session(data, agent_id, session_key)
        return info if isinstance(info, Mapping) else None

    def _session_file(self, info: Mapping[str, Any]) -> Path | None:
        session_id = str(info.get("sessionId") or "")
        raw_path = info.get("sessionFile") or (self._sessions_dir / f"{session_id}.jsonl" if session_id else "")
        if not raw_path:
            return None
        try:
            candidate = Path(raw_path)
            path = (candidate if candidate.is_absolute() else self._sessions_dir / candidate).resolve()
            path.relative_to(self._sessions_dir)
        except (OSError, ValueError):
            return None
        return path if path.is_file() else None

    @staticmethod
    def _tail(path: Path) -> str:
        try:
            with path.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                start = max(0, size - TAIL_BYTES)
                stream.seek(start)
                data = stream.read(TAIL_BYTES).decode("utf-8", errors="replace")
            if start > 0:
                newline = data.find("\n")
                data = data[newline + 1 :] if newline >= 0 else ""
            return data
        except OSError:
            return ""

    def read_messages(
        self,
        scope: TimelineScope,
        session_key: str,
        *,
        max_messages: int = 50,
    ) -> list[dict[str, Any]]:
        info = self._session_info(scope.agent_id, session_key)
        path = self._session_file(info or {}) if info else None
        if path is None:
            return []
        records = []
        for line in self._tail(path).splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, Mapping):
                continue
            normalized = normalize_source_record("openclaw", entry)
            if normalized.get("role") not in {"user", "assistant"}:
                continue
            records.append(
                {
                    key: value
                    for key, value in normalized.items()
                    if key not in {"message", "content", "providerKind"}
                }
            )
        messages = project_workflow_history(
            self._timeline,
            scope,
            records,
            source="openclaw",
            limit=max_messages,
        )
        for message in messages:
            if "text" in message:
                message["text"] = str(message.get("text") or "")[:2_000]
            tools = []
            for tool in message.get("tools") or ():
                if not isinstance(tool, Mapping):
                    continue
                projected = dict(tool)
                projected["canonicalName"] = str(tool.get("name") or "")
                projected["name"] = _tool_summary(tool)
                projected.setdefault("args_preview", "")
                tools.append(projected)
            if tools:
                message["tools"] = tools[:5]
        return messages

    def is_active(self, agent_id: str, session_key: str) -> bool:
        info = self._session_info(agent_id, session_key)
        return str((info or {}).get("status") or "") == "running"
