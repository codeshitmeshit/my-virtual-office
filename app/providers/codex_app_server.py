"""Live Codex bridge built on the public ``codex app-server`` protocol."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from provider_app_server import AppServerResponseError, JsonlAppServerRuntime
from providers.codex_launch_policy import build_codex_app_server_command


APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "execCommandApproval",
    "applyPatchApproval",
    "item/tool/requestUserInput",
    "mcpServer/elicitation/request",
}
MAX_PENDING_APPROVALS = 100
MAX_PRESTART_MESSAGES = 512
PRESTART_VISIBILITY_DELAY_SEC = 1.0
TURN_START_RESPONSE_TIMEOUT_SEC = 30.0
TERMINAL_DRAIN_TIMEOUT_SEC = 0.05
POST_TERMINAL_METRIC_METHODS = {"thread/tokenUsage/updated", "session/metrics"}
MAX_TERMINAL_DIAGNOSTICS = 100
MAX_LATE_START_CLEANUPS = 100
LATE_START_RECOVERY_DELAY_SEC = 5.0
LATE_START_RECOVERY_MAX_ATTEMPTS = 12
MAX_OBSERVED_TERMINAL_TURNS = 64


def _error_result(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "status": code,
        "errorCode": code,
        "error": str(message or code),
        "reply": "",
        "modifiedFiles": [],
        "needsHumanIntervention": code == "needs_human_intervention",
        **extra,
    }


def _turn_user_input(message: str, attachments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Build the version-matched app-server V2 input array."""
    inputs: list[dict[str, Any]] = [{"type": "text", "text": str(message or "")}]
    seen = set()
    for item in attachments or []:
        if not isinstance(item, dict):
            continue
        mime_type = str(item.get("mimeType") or item.get("contentType") or "").lower()
        if not mime_type.startswith("image/"):
            continue
        path = str(item.get("path") or item.get("filePath") or "").strip()
        if path:
            path = os.path.realpath(os.path.expanduser(path))
            key = ("localImage", path)
            if os.path.isfile(path) and key not in seen:
                seen.add(key)
                inputs.append({"type": "localImage", "path": path})
                continue
        url = str(item.get("url") or item.get("mediaUrl") or "").strip()
        if url and not url.startswith("/"):
            key = ("image", url)
            if key not in seen:
                seen.add(key)
                inputs.append({"type": "image", "url": url})
    return inputs


def _reasoning_item_text(item: dict[str, Any]) -> str:
    for key in ("text", "summaryText", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    summary = item.get("summary")
    if isinstance(summary, str):
        return summary
    if isinstance(summary, list):
        parts = []
        for part in summary:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n\n".join(part for part in parts if part.strip())
    return ""


def _limit_text(value: Any, limit: int = 12000) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 20)] + "\n...<truncated>"


def _normalize_status(value: Any, completed: bool = False) -> str:
    raw = str(value or "").lower()
    if raw in {"completed", "done", "success", "succeeded"}:
        return "done"
    if raw in {"failed", "error", "declined"}:
        return "error"
    if completed:
        return "done"
    return "running"


def _native_turn_id(params: dict[str, Any]) -> str:
    params = params if isinstance(params, dict) else {}
    turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
    return str(params.get("turnId") or turn.get("id") or "").strip()


class CodexAppRunState:
    """Collect Codex app-server notifications into Office chat artifacts."""

    def __init__(self) -> None:
        self.thread_id = ""
        self.turn_id = ""
        self.status = "inProgress"
        self.completed = False
        self._reply_delta = ""
        self._reply_final = ""
        self._reasoning_parts: list[str] = []
        self._plan = ""
        self._errors: list[str] = []
        self._tools: dict[str, dict[str, Any]] = {}
        self._tool_order: list[str] = []
        self._approval: dict[str, Any] | None = None
        self._token_usage: dict[str, Any] = {}

    def handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if params.get("threadId"):
            self.thread_id = str(params.get("threadId") or self.thread_id)
        if params.get("turnId"):
            self.turn_id = str(params.get("turnId") or self.turn_id)

        if method == "turn/started":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            self.turn_id = str(turn.get("id") or self.turn_id)
            self.status = str(turn.get("status") or self.status)
        elif method == "item/agentMessage/delta":
            self._reply_delta += str(params.get("delta") or "")
        elif method in {"item/reasoning/summaryTextDelta", "item/reasoning/textDelta"}:
            delta = str(params.get("delta") or "")
            if delta:
                self._reasoning_parts.append(delta)
        elif method == "turn/plan/updated":
            plan = params.get("plan") if isinstance(params.get("plan"), list) else []
            lines = []
            for step in plan:
                if isinstance(step, dict):
                    status = str(step.get("status") or "").replace("inProgress", "in progress")
                    text = str(step.get("step") or "").strip()
                    if text:
                        lines.append(f"- {text} ({status})".strip())
            explanation = str(params.get("explanation") or "").strip()
            self._plan = "\n".join([part for part in [explanation, *lines] if part]).strip()
        elif method == "thread/tokenUsage/updated":
            token_usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), dict) else {}
            if token_usage:
                self._token_usage = dict(token_usage)
        elif method in {"item/started", "item/updated", "item/completed"}:
            item = params.get("item") if isinstance(params.get("item"), dict) else {}
            self._handle_item(item, completed=(method == "item/completed"))
        elif method == "item/commandExecution/outputDelta":
            item_id = str(params.get("itemId") or "")
            delta = str(params.get("delta") or "")
            if item_id and delta:
                tool = self._tools.get(item_id)
                if tool:
                    tool["result"] = _limit_text(str(tool.get("result") or "") + delta)
        elif method == "error":
            error = params.get("error") if isinstance(params.get("error"), dict) else {}
            text = error.get("message") or params.get("message") or "Codex turn failed"
            self._errors.append(str(text))
        elif method == "turn/completed":
            turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            self.turn_id = str(turn.get("id") or self.turn_id)
            self.status = str(turn.get("status") or self.status or "completed")
            if isinstance(turn.get("error"), dict) and turn["error"].get("message"):
                self._errors.append(str(turn["error"]["message"]))
            for item in turn.get("items") or []:
                if isinstance(item, dict):
                    self._handle_item(item, completed=True)
            self.completed = True

    def snapshot(self) -> dict[str, Any]:
        return {
            "threadId": self.thread_id,
            "sessionId": self.thread_id,
            "turnId": self.turn_id,
            "runId": self.turn_id,
            "reply": self.reply_text(),
            "tools": self.tools(),
            "thinking": self.thinking(),
            "status": self.status,
            "error": self.error_text(),
            "approval": self.approval(),
            "tokenUsage": self.token_usage(),
        }

    def reply_text(self) -> str:
        return self._reply_final or self._reply_delta

    def thinking(self) -> str:
        parts = []
        if self._plan:
            parts.append(self._plan)
        reasoning = "".join(self._reasoning_parts).strip()
        if reasoning:
            parts.append(reasoning)
        return "\n\n".join(parts)[:12000]

    def tools(self) -> list[dict[str, Any]]:
        return [self._tools[k] for k in self._tool_order if k in self._tools][-60:]

    def approval(self) -> dict[str, Any] | None:
        return dict(self._approval) if isinstance(self._approval, dict) else None

    def set_approval(self, approval: dict[str, Any] | None) -> None:
        self._approval = dict(approval) if isinstance(approval, dict) else None

    def token_usage(self) -> dict[str, Any]:
        return dict(self._token_usage) if isinstance(self._token_usage, dict) else {}

    def error_text(self) -> str:
        return "\n".join(dict.fromkeys([e for e in self._errors if e]))[:2000]

    def _handle_item(self, item: dict[str, Any], completed: bool = False) -> None:
        item_type = str(item.get("type") or "")
        if item_type == "agentMessage":
            text = str(item.get("text") or "")
            if text:
                self._reply_final = text
            return
        if item_type == "reasoning":
            for part in (item.get("summary") or []) + (item.get("content") or []):
                if isinstance(part, str) and part.strip():
                    self._reasoning_parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str) and text.strip():
                        self._reasoning_parts.append(text)
            return

        tool = self._tool_from_app_item(item, completed=completed)
        if not tool:
            return
        tool_id = tool["id"]
        if tool_id not in self._tools:
            self._tool_order.append(tool_id)
        existing = self._tools.get(tool_id, {})
        existing.update({k: v for k, v in tool.items() if v not in (None, "") or k not in existing})
        self._tools[tool_id] = existing

    def _tool_from_app_item(self, item: dict[str, Any], completed: bool = False) -> dict[str, Any] | None:
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or f"codex-{len(self._tools) + 1}")
        status = _normalize_status(item.get("status"), completed)
        if item_type == "commandExecution":
            return {
                "id": item_id,
                "name": "shell",
                "status": status,
                "arguments": {"command": item.get("command") or "", "cwd": item.get("cwd") or ""},
                "result": _limit_text(item.get("aggregatedOutput") or ""),
                "error": "" if status != "error" else _limit_text(item.get("aggregatedOutput") or item.get("error") or ""),
                "source": "codex",
            }
        if item_type == "fileChange":
            changes = item.get("changes") if isinstance(item.get("changes"), list) else []
            paths = []
            for change in changes:
                if isinstance(change, dict):
                    paths.append(str(change.get("path") or change.get("file") or change.get("uri") or "file"))
            return {
                "id": item_id,
                "name": "file changes",
                "status": status,
                "arguments": {"files": paths[:20], "count": len(changes)},
                "result": f"{len(changes)} file change(s)" if changes else "",
                "error": "",
                "source": "codex",
            }
        if item_type == "mcpToolCall":
            error = item.get("error")
            return {
                "id": item_id,
                "name": ".".join(x for x in [str(item.get("server") or ""), str(item.get("tool") or "mcp")] if x),
                "status": "error" if error else status,
                "arguments": item.get("arguments") or {},
                "result": _limit_text(item.get("result") or ""),
                "error": _limit_text(error or ""),
                "source": "codex",
            }
        if item_type == "dynamicToolCall":
            return {
                "id": item_id,
                "name": item.get("tool") or "tool",
                "status": status,
                "arguments": item.get("arguments") or {},
                "result": _limit_text(item.get("contentItems") or ""),
                "error": "" if item.get("success") is not False else "Tool call failed",
                "source": "codex",
            }
        if item_type == "webSearch":
            return {
                "id": item_id,
                "name": "web search",
                "status": status,
                "arguments": {"query": item.get("query") or ""},
                "result": _limit_text(item.get("action") or ""),
                "error": "",
                "source": "codex",
            }
        return None


@dataclass
class _Operation:
    thread_id: str
    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = "turn"
    turn_id: str = ""
    reply: str = ""
    modified_files: set[str] = field(default_factory=set)
    needs_human: bool = False
    human_reason: str = ""
    completed: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    event_callback: Any = None
    allow_interaction: bool = False
    sequence: int = 0
    pending_requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    state: CodexAppRunState = field(default_factory=CodexAppRunState)
    cancel_requested: bool = False
    _callback_condition: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _active_callback_ids: set[int] = field(default_factory=set, repr=False)
    _next_callback_id: int = 0
    _terminal_target: int = 0
    _terminal_observed: bool = False
    _terminal_observed_ns: int = 0
    _terminal_completed_ns: int = 0
    _terminal_timer_started: bool = False
    terminal_fence_fallbacks: int = 0
    late_notifications: int = 0
    post_terminal_metrics: int = 0
    callback_errors: int = 0
    callback_error_category: str = ""
    stale_turn_ids: set[str] = field(default_factory=set, repr=False)
    _callbacks_drained: threading.Event = field(default_factory=threading.Event, repr=False)
    _prestart_messages: list[tuple[str, dict[str, Any]]] = field(default_factory=list, repr=False)
    _native_messages_ready: bool = False
    prestart_message_overflows: int = 0
    _prestart_visibility_timer: threading.Timer | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._callbacks_drained.set()
        self._native_messages_ready = self.kind != "turn"

    def emit(self, event_type: str, *, terminal: bool = False, **data: Any) -> bool:
        with self._callback_condition:
            if (
                event_type == "turn"
                and data.get("status") == "starting"
                and (self.cancel_requested or self.turn_id)
            ):
                return False
            if self._terminal_observed and not terminal:
                self.late_notifications += 1
                return False
            self._next_callback_id += 1
            callback_id = self._next_callback_id
            self._callbacks_drained.clear()
            self._active_callback_ids.add(callback_id)
            if terminal:
                self._terminal_observed = True
                self._terminal_target = callback_id
                self._terminal_observed_ns = self._terminal_observed_ns or time.monotonic_ns()
            self.sequence += 1
            event = {
                "id": f"codex-{uuid.uuid4().hex}",
                "sequence": self.sequence,
                "type": event_type,
                "operationId": self.operation_id,
                "threadId": self.thread_id,
                "turnId": self.turn_id,
                "ts": int(time.time() * 1000),
                **data,
            }
            if terminal and self.event_callback:
                self._start_terminal_fallback_locked()

        if terminal and self.event_callback:
            def invoke_terminal_callback() -> None:
                try:
                    self.event_callback(event)
                except Exception as exc:
                    self._record_callback_error(exc)
                finally:
                    self._finish_callback(callback_id, terminal=True)

            try:
                worker = threading.Thread(
                    target=invoke_terminal_callback,
                    name=f"codex-terminal-callback-{self.operation_id[:8]}",
                    daemon=True,
                )
                worker.start()
                return True
            except Exception as exc:
                self._record_callback_error(exc)
                self._finish_callback(callback_id, terminal=True)
                return False

        callback_ok = True
        try:
            if self.event_callback:
                self.event_callback(event)
        except Exception as exc:
            callback_ok = False
            self._record_callback_error(exc)
        finally:
            self._finish_callback(callback_id, terminal=terminal)
        return callback_ok

    def _record_callback_error(self, exc: BaseException) -> None:
        with self._callback_condition:
            self.callback_errors += 1
            self.callback_error_category = type(exc).__name__[:80]

    def _finish_callback(self, callback_id: int, *, terminal: bool) -> None:
        with self._callback_condition:
            self._active_callback_ids.discard(callback_id)
            if not self._active_callback_ids:
                self._callbacks_drained.set()
            self._release_completion_if_drained_locked()
            if terminal and not self.completed.is_set():
                self._start_terminal_fallback_locked()
            self._callback_condition.notify_all()

    def wait_for_callbacks(self, timeout: float | None = None) -> bool:
        return self._callbacks_drained.wait(timeout=timeout)

    def inherit_turn_history(self, previous: "_Operation | None") -> None:
        if previous is None:
            return
        with self._callback_condition:
            inherited = set(previous.stale_turn_ids)
            if previous.turn_id:
                inherited.add(previous.turn_id)
            self.stale_turn_ids.update(sorted(inherited)[-64:])

    def accept_turn_identity(self, params: dict[str, Any]) -> bool:
        incoming = _native_turn_id(params)
        if not incoming:
            return True
        with self._callback_condition:
            if incoming in self.stale_turn_ids or (self.turn_id and incoming != self.turn_id):
                self.late_notifications += 1
                return False
            if not self.turn_id:
                self.turn_id = incoming
            return True

    def defer_native_message(self, kind: str, payload: dict[str, Any]) -> str:
        with self._callback_condition:
            if self._native_messages_ready:
                return "ready"
            if self._terminal_observed:
                self.late_notifications += 1
                return "closed"
            if len(self._prestart_messages) >= MAX_PRESTART_MESSAGES:
                self.prestart_message_overflows += 1
                return "overflow"
            self._prestart_messages.append((str(kind or ""), dict(payload or {})))
            return "deferred"

    def defer_native_notification(self, method: str, params: dict[str, Any]) -> bool:
        return self.defer_native_message(
            "notification",
            {"method": str(method or ""), "params": dict(params or {})},
        ) != "ready"

    def confirm_turn_identity(self, turn_id: str) -> bool:
        authoritative = str(turn_id or "").strip()
        with self._callback_condition:
            if authoritative:
                if self.turn_id and self.turn_id != authoritative:
                    self.stale_turn_ids.add(self.turn_id)
                self.turn_id = authoritative
                self.state.thread_id = self.thread_id
                self.state.turn_id = authoritative
            return self.prestart_message_overflows == 0

    def take_prestart_messages(self) -> list[tuple[str, dict[str, Any]]] | None:
        with self._callback_condition:
            if self._prestart_messages:
                pending = self._prestart_messages
                self._prestart_messages = []
                return pending
            self._native_messages_ready = True
            return None

    def discard_prestart_messages(self) -> list[tuple[str, dict[str, Any]]]:
        with self._callback_condition:
            pending = self._prestart_messages
            self._prestart_messages = []
            return pending

    def prestart_turn_ids(self) -> list[str]:
        with self._callback_condition:
            turn_ids = set()
            for kind, payload in self._prestart_messages:
                params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                turn_id = _native_turn_id(params)
                if turn_id:
                    turn_ids.add(turn_id)
            return sorted(turn_ids)

    def prestart_terminal_turn_ids(self) -> set[str]:
        with self._callback_condition:
            terminal_turn_ids = set()
            for kind, payload in self._prestart_messages:
                if kind != "notification" or payload.get("method") != "turn/completed":
                    continue
                params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                turn_id = _native_turn_id(params)
                if turn_id:
                    terminal_turn_ids.add(turn_id)
            return terminal_turn_ids

    def prestart_overflowed(self) -> bool:
        with self._callback_condition:
            return self.prestart_message_overflows > 0

    def finish_without_event(self) -> None:
        with self._callback_condition:
            if not self._terminal_observed:
                self._terminal_observed = True
                self._terminal_target = self._next_callback_id
                self._terminal_observed_ns = time.monotonic_ns()
            self._release_completion_if_drained_locked()
            if not self.completed.is_set():
                self._start_terminal_fallback_locked()

    def set_prestart_visibility_timer(self, timer: threading.Timer) -> None:
        with self._callback_condition:
            self._prestart_visibility_timer = timer

    def cancel_prestart_visibility(self, *, mark_cancelled: bool = False) -> None:
        with self._callback_condition:
            if mark_cancelled:
                self.cancel_requested = True
            timer = self._prestart_visibility_timer
            self._prestart_visibility_timer = None
        if timer:
            timer.cancel()

    def emit_prestart_starting(self) -> bool:
        with self._callback_condition:
            if self.cancel_requested or self._terminal_observed or self.turn_id:
                return False
            self._prestart_visibility_timer = None
        return self.emit("turn", status="starting")

    def terminal_observed(self) -> bool:
        with self._callback_condition:
            return self._terminal_observed

    def register_pending_request(self, request_key: str, pending: dict[str, Any]) -> bool:
        with self._callback_condition:
            if self._terminal_observed or self.cancel_requested:
                return False
            self.pending_requests[request_key] = pending
            return True

    def pop_pending_request(self, request_key: str) -> dict[str, Any] | None:
        with self._callback_condition:
            return self.pending_requests.pop(request_key, None)

    def has_pending_request(self, request_key: str) -> bool:
        with self._callback_condition:
            return request_key in self.pending_requests

    def drain_pending_requests(self) -> list[tuple[str, dict[str, Any]]]:
        with self._callback_condition:
            pending = list(self.pending_requests.items())
            self.pending_requests.clear()
            return pending

    def accept_native_notification(self, method: str) -> bool:
        with self._callback_condition:
            if not self._terminal_observed:
                return True
            if method in POST_TERMINAL_METRIC_METHODS:
                self.post_terminal_metrics += 1
            else:
                self.late_notifications += 1
            return False

    def fence_diagnostics(self) -> dict[str, int | bool]:
        with self._callback_condition:
            return {
                "terminalObserved": self._terminal_observed,
                "activeCallbacks": len(self._active_callback_ids),
                "terminalFenceFallbacks": self.terminal_fence_fallbacks,
                "lateNotifications": self.late_notifications,
                "postTerminalMetrics": self.post_terminal_metrics,
                "callbackErrors": self.callback_errors,
                "prestartMessageOverflows": self.prestart_message_overflows,
                "terminalFenceWaitMs": round(max(0, self._terminal_completed_ns - self._terminal_observed_ns) / 1_000_000, 3)
                if self._terminal_observed_ns and self._terminal_completed_ns else 0.0,
            }

    def _release_completion_if_drained_locked(self) -> None:
        if not self._terminal_observed:
            return
        if any(callback_id <= self._terminal_target for callback_id in self._active_callback_ids):
            return
        self._terminal_completed_ns = self._terminal_completed_ns or time.monotonic_ns()
        self.completed.set()

    def _start_terminal_fallback_locked(self) -> None:
        if self._terminal_timer_started:
            return
        self._terminal_timer_started = True

        def fallback() -> None:
            with self._callback_condition:
                if self.completed.is_set():
                    return
                self.terminal_fence_fallbacks += 1
                self._terminal_completed_ns = self._terminal_completed_ns or time.monotonic_ns()
                self.completed.set()
                self._callback_condition.notify_all()

        timer = threading.Timer(TERMINAL_DRAIN_TIMEOUT_SEC, fallback)
        timer.daemon = True
        timer.start()


@dataclass
class _LateStartCleanup:
    event: threading.Event = field(default_factory=threading.Event)
    turn_id: str = ""
    interrupt_sent: bool = False
    observed_terminal_turn_ids: set[str] = field(default_factory=set)
    recovery_scheduled: bool = False
    recovery_attempts: int = 0
    force_recycle: bool = False


class CodexAppServerClient:
    """Small synchronous facade over app-server's bidirectional JSONL RPC."""

    def __init__(self, workspace: str, model: str = "", binary: str | None = None, max_concurrent_turns: int = 1, route_approvals_through_vo: bool = False, home_path: str | None = None, sandbox: str | None = None, approval_policy: str | None = None):
        self.workspace = os.path.abspath(workspace)
        self.model = model or ""
        self.binary = binary or os.environ.get("VO_CODEX_BIN") or shutil.which("codex") or "codex"
        self.profile = str(os.environ.get("VO_CODEX_PROFILE") or "").strip()
        self.route_approvals_through_vo = bool(route_approvals_through_vo)
        self.sandbox = self._normalize_sandbox(sandbox or os.environ.get("VO_CODEX_SANDBOX"))
        self.configured_approval_policy = self._normalize_approval_policy(
            approval_policy or os.environ.get("VO_CODEX_APPROVAL_POLICY")
        )
        self.home_path = os.path.abspath(os.path.expanduser(home_path or os.environ.get("VO_CODEX_HOME") or os.environ.get("CODEX_HOME") or "~/.codex"))
        app_server_args = self._permission_hook_disable_args() if self.route_approvals_through_vo else []
        runtime_command = build_codex_app_server_command(
            self.binary,
            sandbox=self.sandbox,
            approval_policy=self.configured_approval_policy,
            route_approvals_through_vo=self.route_approvals_through_vo,
            app_server_args=app_server_args,
        )
        runtime_env = os.environ.copy()
        runtime_env["CODEX_HOME"] = self.home_path
        try:
            self.start_timeout_sec = max(0.1, float(os.environ.get("VO_CODEX_START_TIMEOUT_SEC") or 30))
        except (TypeError, ValueError):
            self.start_timeout_sec = 30.0
        summary = str(os.environ.get("VO_CODEX_REASONING_SUMMARY") or "detailed").strip().lower()
        self.reasoning_summary = summary if summary in {"auto", "concise", "detailed", "none"} else "detailed"
        self._runtime = JsonlAppServerRuntime(
            runtime_command,
            cwd=self.workspace,
            env=runtime_env,
            name="codex-app-server",
            stderr=subprocess.PIPE,
        )
        self._runtime.on_server_request = self._handle_server_request
        self._runtime.on_notification = self._handle_notification
        self._runtime.on_exit = self._handle_runtime_exit
        self._initialize_lock = threading.Lock()
        self._runtime_generation_lock = threading.RLock()
        self._initialized = False
        self._operations: dict[str, _Operation] = {}
        self._terminal_operations: OrderedDict[str, _Operation] = OrderedDict()
        self._operations_lock = threading.Lock()
        self._owned_thread_ids: set[str] = set()
        try:
            self.max_concurrent_turns = max(1, min(int(max_concurrent_turns or 1), 4))
        except (TypeError, ValueError):
            self.max_concurrent_turns = 1
        self._turn_capacity = threading.BoundedSemaphore(self.max_concurrent_turns)
        self._thread_locks_guard = threading.Lock()
        self._thread_locks: dict[str, dict[str, Any]] = {}
        self._admission_lock = threading.Lock()
        self._admission_counters = {"acceptedTurns": 0, "busyByCapacity": 0, "activeTurns": 0, "peakActiveTurns": 0}
        self._approval_lock = threading.Condition()
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._late_start_lock = threading.Lock()
        self._late_start_cleanups: OrderedDict[str, _LateStartCleanup] = OrderedDict()
        self._recovery_admission_lock = threading.RLock()

    def _permission_hook_disable_args(self) -> list[str]:
        """Disable user PermissionRequest hooks for this VO app-server only."""
        hooks_path = os.path.join(self.home_path, "hooks.json")
        try:
            with open(hooks_path, encoding="utf-8") as source:
                config = json.load(source)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        groups = (config.get("hooks") or {}).get("PermissionRequest") if isinstance(config, dict) else None
        state_entries: list[str] = []
        for group_index, group in enumerate(groups if isinstance(groups, list) else []):
            hooks = group.get("hooks") if isinstance(group, dict) else None
            for hook_index, _hook in enumerate(hooks if isinstance(hooks, list) else []):
                state_key = f"{hooks_path}:permission_request:{group_index}:{hook_index}"
                state_entries.append(f"{json.dumps(state_key)} = {{ enabled = false }}")
        if not state_entries:
            return []
        return ["-c", "hooks.state={ " + ", ".join(state_entries) + " }"]

    @staticmethod
    def _normalize_sandbox(value: str | None) -> str:
        normalized = str(value or "workspace-write").strip().lower()
        return normalized if normalized in {"read-only", "workspace-write", "danger-full-access"} else "workspace-write"

    @staticmethod
    def _normalize_approval_policy(value: str | None) -> str:
        normalized = str(value or "on-request").strip().lower()
        return normalized if normalized in {"untrusted", "on-request", "never"} else "on-request"

    def close(self) -> None:
        self._initialized = False
        self._runtime.close()
        self._handle_runtime_exit()

    def probe_auth(self, timeout_sec: int = 15) -> dict[str, Any]:
        """Initialize Codex app-server and read account/auth state."""
        init: dict[str, Any] = {}
        account: dict[str, Any] = {}
        try:
            with self._runtime_generation_lock:
                init = self._ensure_started()
                account = self._request("account/read", {"refreshToken": False}, timeout=float(timeout_sec or 15))
            auth_ok, auth_status = self._account_status(account)
            return {
                "ok": auth_ok,
                "protocol": "app-server",
                "authOk": auth_ok,
                "authStatus": auth_status,
                "account": account.get("account") if isinstance(account, dict) else None,
                "requiresOpenaiAuth": account.get("requiresOpenaiAuth") if isinstance(account, dict) else None,
                "codexHome": init.get("codexHome") if isinstance(init, dict) else "",
                "error": "" if auth_ok else "Codex is installed but not authenticated. Run codex login or configure CODEX_API_KEY/CODEX_HOME for this environment.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "protocol": "app-server",
                "authOk": False,
                "authStatus": "",
                "error": str(exc),
            }

    def _ensure_started(self) -> dict[str, Any]:
        if self._runtime.is_running() and self._initialized:
            return {}
        with self._initialize_lock:
            if self._runtime.is_running() and self._initialized:
                return {}
            self._runtime.start()
            init = self._request("initialize", {
                "clientInfo": {
                    "name": "my_virtual_office",
                    "title": "My Virtual Office",
                    "version": "codex-live-bridge",
                },
                "capabilities": {"experimentalApi": True},
            }, timeout=15)
            self._send({"method": "initialized", "params": {}})
            self._initialized = True
            return init

    def _send(self, message: dict[str, Any]) -> None:
        self._runtime.send(message)

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        timeout: float = 30,
        on_late_response: Any = None,
    ) -> dict[str, Any]:
        return self._runtime.request(
            method,
            params,
            timeout=timeout,
            on_late_response=on_late_response,
        ).get("result") or {}

    def _restart_runtime(self) -> None:
        self._initialized = False
        try:
            self._runtime.close()
        except Exception:
            pass
        self._handle_runtime_exit()

    def _has_active_operations(self) -> bool:
        with self._operations_lock:
            return any(not operation.completed.is_set() for operation in self._operations.values())

    def _request_with_restart(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float = 30,
        retry: bool = True,
        on_late_response: Any = None,
    ) -> dict[str, Any]:
        try:
            return self._request(method, params, timeout=timeout, on_late_response=on_late_response)
        except TimeoutError:
            if not retry:
                raise
            with self._runtime_generation_lock:
                # The runtime is shared by all active native threads. Restarting
                # it to recover one startup request would fail unrelated turns.
                if self._has_active_operations():
                    raise
                self._restart_runtime()
                self._ensure_started()
                return self._request(method, params, timeout=timeout)

    @staticmethod
    def _account_status(account_result: dict[str, Any]) -> tuple[bool, str]:
        account_result = account_result if isinstance(account_result, dict) else {}
        account = account_result.get("account")
        auth_ok = bool(account) or account_result.get("requiresOpenaiAuth") is False
        if isinstance(account, dict):
            label = account.get("email") or account.get("id") or account.get("account_id") or "authenticated"
            plan = account.get("plan_type") or account.get("planType") or account.get("subscription")
            return True, f"{label} ({plan})" if plan else str(label)
        if account_result.get("requiresOpenaiAuth") is False:
            return True, "authenticated"
        error = account_result.get("error") or account_result.get("message") or ""
        return False, str(error or "not authenticated")

    def _allocate_id(self) -> int:
        return self._runtime.allocate_id()

    def _handle_runtime_exit(self) -> None:
        with self._recovery_admission_lock:
            self._initialized = False
            owned_thread_ids = getattr(self, "_owned_thread_ids", None)
            if owned_thread_ids is not None:
                owned_thread_ids.clear()
            with self._late_start_lock:
                for cleanup in self._late_start_cleanups.values():
                    cleanup.event.set()
                self._late_start_cleanups.clear()
            with self._operations_lock:
                operations = list(self._operations.values())
            detail = self._runtime.stderr_text()
            message = "Codex app-server stopped unexpectedly"
            if detail:
                message = f"{message}: {detail}"
            for operation in operations:
                if not operation.completed.is_set():
                    operation.result = _error_result("bridge_unavailable", message, threadId=operation.thread_id, turnId=operation.turn_id)
                    self._remember_terminal_operation(operation)
                    operation.finish_without_event()
            self._clear_pending_approvals()

    @staticmethod
    def _rejected_server_request_result(method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "item/tool/requestUserInput":
            return {"answers": {}}
        if method == "mcpServer/elicitation/request":
            return {"action": "decline"}
        return CodexAppServerClient._approval_response(method, params, "cancel")

    def _handle_server_request(self, message: dict[str, Any], *, defer_prestart: bool = True) -> None:
        method = message.get("method", "")
        params = message.get("params") or {}
        thread_id = str(params.get("threadId") or "")
        with self._operations_lock:
            operation = self._operations.get(thread_id) or self._terminal_operations.get(thread_id)
        if method in APPROVAL_METHODS:
            if operation and defer_prestart:
                prestart_state = operation.defer_native_message("server_request", message)
                if prestart_state == "deferred":
                    return
                if prestart_state in {"overflow", "closed"}:
                    self._send({
                        "id": message["id"],
                        "result": self._rejected_server_request_result(method, params),
                    })
                    return
            if operation and not operation.accept_turn_identity(params):
                result = self._rejected_server_request_result(method, params)
                self._send({"id": message["id"], "result": result})
                return
            if operation and operation.cancel_requested:
                result = self._rejected_server_request_result(method, params)
                self._send({"id": message["id"], "result": result})
                return
            if operation and operation.fence_diagnostics()["terminalObserved"]:
                operation.accept_native_notification(method)
                result = self._rejected_server_request_result(method, params)
                self._send({"id": message["id"], "result": result})
                return
            if operation and operation.allow_interaction:
                request_key = str(message["id"])
                interaction_type = "input" if method in {"item/tool/requestUserInput", "mcpServer/elicitation/request"} else "approval"
                approval = self._approval_from_request(message) if interaction_type == "approval" else None
                if not operation.register_pending_request(request_key, {
                    "id": message["id"],
                    "method": method,
                    "params": params,
                    "type": interaction_type,
                    "approval": approval,
                }):
                    self._send({
                        "id": message["id"],
                        "result": self._rejected_server_request_result(method, params),
                    })
                    return
                if approval:
                    if not self._store_pending_approval(operation, request_key, method, params, approval):
                        operation.pop_pending_request(request_key)
                        self._send({"id": message["id"], "result": self._approval_response(method, params, "cancel")})
                        operation.emit(
                            "interaction",
                            status="resolved",
                            interactionId=request_key,
                            interactionType=interaction_type,
                            method=method,
                            error="Codex approval capacity reached",
                        )
                        return
                    if not operation.has_pending_request(request_key):
                        with self._approval_lock:
                            self._pending_approvals.pop(str(approval.get("id") or approval.get("approval_id") or request_key), None)
                        return
                    operation.state.set_approval(approval)
                emitted = operation.emit(
                    "interaction",
                    status="pending",
                    interactionId=request_key,
                    interactionType=interaction_type,
                    method=method,
                    itemId=str(params.get("itemId") or ""),
                    input=params,
                )
                if not emitted:
                    unresolved = operation.pop_pending_request(request_key)
                    self._clear_pending_approvals(thread_id)
                    if unresolved:
                        failure_response = self._rejected_server_request_result(method, params)
                        self._send({"id": message["id"], "result": failure_response})
                    operation.result = _error_result(
                        "event_callback_failed",
                        "Codex event handling failed before approval could be exposed",
                        threadId=thread_id,
                        turnId=operation.turn_id or str(params.get("turnId") or ""),
                        errorCategory=operation.callback_error_category,
                    )
                    self._remember_terminal_operation(operation)
                    operation.finish_without_event()
                return
            if operation:
                operation.needs_human = True
                operation.human_reason = f"Codex requested approval: {method}"
            if method == "item/permissions/requestApproval":
                result = {"permissions": {}, "scope": "turn"}
            elif method == "item/tool/requestUserInput":
                result = {"answers": {}}
            elif method == "mcpServer/elicitation/request":
                result = {"action": "decline"}
            else:
                result = {"decision": "cancel"}
            self._send({"id": message["id"], "result": result})
            if operation:
                interrupt_id = self._allocate_id()
                self._send({
                    "id": interrupt_id,
                    "method": "turn/interrupt",
                    "params": {"threadId": thread_id, "turnId": operation.turn_id or params.get("turnId")},
                })
                operation.result = _error_result(
                    "needs_human_intervention",
                    operation.human_reason,
                    threadId=thread_id,
                    turnId=operation.turn_id or str(params.get("turnId") or ""),
                )
                self._remember_terminal_operation(operation)
                operation.finish_without_event()
            return
        self._send({"id": message["id"], "error": {"code": -32601, "message": f"Unsupported server request: {method}"}})

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        thread_id = str(params.get("threadId") or "")
        late_turn_id = _native_turn_id(params)
        if (
            method == "turn/completed"
            and thread_id
            and late_turn_id
            and self._handle_late_start_terminal(thread_id, late_turn_id)
        ):
            return
        with self._operations_lock:
            operation = self._operations.get(thread_id) or self._terminal_operations.get(thread_id)
        if not operation:
            return
        if operation.defer_native_notification(method, params):
            return
        self._handle_operation_notification(operation, method, params)

    def _handle_operation_notification(
        self,
        operation: _Operation,
        method: str,
        params: dict[str, Any],
    ) -> None:
        thread_id = operation.thread_id
        if not operation.accept_turn_identity(params):
            return
        if not operation.accept_native_notification(method):
            return
        operation.state.handle_notification(method, params)
        if method == "turn/started":
            turn = params.get("turn") or {}
            operation.turn_id = str(turn.get("id") or params.get("turnId") or operation.turn_id)
            operation.state.thread_id = operation.thread_id
            operation.state.turn_id = operation.turn_id
            operation.emit("turn", status="running")
        elif method in {"item/started", "item/updated"}:
            item = params.get("item") or {}
            if item.get("type") == "reasoning":
                operation.emit(
                    "reasoning",
                    status="running",
                    itemId=str(item.get("id") or params.get("itemId") or ""),
                    text=_reasoning_item_text(item),
                    replace=True,
                )
            elif item.get("type") not in {"agentMessage", "userMessage"}:
                operation.emit(
                    "activity",
                    status="running",
                    itemId=str(item.get("id") or params.get("itemId") or ""),
                    name=str(item.get("type") or method.split("/")[0] or "tool"),
                    input=item,
                )
        elif method in {
            "item/reasoning/summaryTextDelta",
            "item/reasoning/summaryPartAdded",
            "item/reasoning/textDelta",
        }:
            operation.emit(
                "reasoning",
                status="running",
                itemId=str(params.get("itemId") or ""),
                text=str(params.get("delta") or params.get("text") or ""),
                sectionIndex=params.get("summaryIndex"),
                boundary=method == "item/reasoning/summaryPartAdded",
                deltaKind="raw" if method.endswith("/textDelta") else "summary",
            )
        elif method in {
            "item/commandExecution/outputDelta",
            "item/fileChange/outputDelta",
            "item/mcpToolCall/progress",
        }:
            operation.emit(
                "activity",
                status="running",
                itemId=str(params.get("itemId") or ""),
                name=method.split("/")[1] if "/" in method else method,
                output=params.get("delta") or params.get("message") or params,
            )
        elif method == "item/completed":
            item = params.get("item") or {}
            if item.get("type") == "agentMessage" and item.get("text"):
                operation.reply = str(item["text"])
            elif item.get("type") == "fileChange":
                for change in item.get("changes") or []:
                    path = change.get("path") or change.get("file") or change.get("uri")
                    if path:
                        operation.modified_files.add(str(path))
            if item.get("type") == "reasoning":
                operation.emit(
                    "reasoning",
                    status="done",
                    itemId=str(item.get("id") or ""),
                    text=_reasoning_item_text(item),
                    replace=True,
                )
            elif item.get("type") not in {"agentMessage", "userMessage"}:
                operation.emit(
                    "activity",
                    status="error" if item.get("status") in {"failed", "error"} else "done",
                    itemId=str(item.get("id") or ""),
                    name=str(item.get("type") or "tool"),
                    input=item,
                    output=item.get("output") or item.get("aggregatedOutput") or item.get("text") or item.get("changes") or "",
                    error=item.get("error"),
                )
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            operation.turn_id = str(turn.get("id") or operation.turn_id)
            for item in turn.get("items") or []:
                if item.get("type") == "agentMessage" and item.get("text"):
                    operation.reply = str(item["text"])
                elif item.get("type") == "fileChange":
                    for change in item.get("changes") or []:
                        path = change.get("path") or change.get("file") or change.get("uri")
                        if path:
                            operation.modified_files.add(str(path))
            if operation.kind == "compact" and turn.get("status") == "completed":
                operation.result = {
                    "ok": True,
                    "status": "compacted",
                    "reply": "Codex context compressed.",
                    "threadId": thread_id,
                    "turnId": operation.turn_id,
                    "modifiedFiles": [],
                    "needsHumanIntervention": False,
                }
            elif operation.needs_human:
                operation.result = _error_result(
                    "needs_human_intervention",
                    operation.human_reason or "Codex requires user approval",
                    threadId=thread_id,
                    turnId=operation.turn_id,
                )
            elif operation.cancel_requested:
                operation.result = _error_result(
                    "cancelled",
                    "Codex turn cancelled",
                    threadId=thread_id,
                    turnId=operation.turn_id,
                )
            elif turn.get("status") == "completed":
                operation.result = {
                    "ok": True,
                    "status": "completed",
                    "reply": operation.state.reply_text() or operation.reply,
                    "threadId": thread_id,
                    "turnId": operation.turn_id,
                    "modifiedFiles": sorted(operation.modified_files),
                    "needsHumanIntervention": False,
                }
            else:
                error = turn.get("error") or {}
                operation.result = _error_result(
                    "execution_failed",
                    error.get("message") or f"Codex turn ended with status {turn.get('status') or 'unknown'}",
                    threadId=thread_id,
                    turnId=operation.turn_id,
                )
            self._remember_terminal_operation(operation)
            operation.emit(
                "turn",
                terminal=True,
                status=operation.result.get("status") if operation.result else str(turn.get("status") or "failed"),
                output={"reply": operation.state.reply_text() or operation.reply, "modifiedFiles": sorted(operation.modified_files)},
                error=(operation.result or {}).get("error"),
            )
        elif method == "thread/compacted":
            operation.result = {
                "ok": True,
                "status": "compacted",
                "reply": "Codex context compressed.",
                "threadId": thread_id,
                "turnId": "",
                "modifiedFiles": [],
                "needsHumanIntervention": False,
            }
            self._remember_terminal_operation(operation)
            operation.finish_without_event()

    def _replay_prestart_messages(self, operation: _Operation) -> bool:
        while True:
            pending = operation.take_prestart_messages()
            if operation.prestart_overflowed():
                self._reject_prestart_server_requests(pending or [])
                self._cancel_prestart_requests(operation)
                return False
            if pending is None:
                return True
            for index, (kind, payload) in enumerate(pending):
                if operation.prestart_overflowed():
                    self._reject_prestart_server_requests(pending[index:])
                    self._cancel_prestart_requests(operation)
                    return False
                if kind == "notification":
                    self._handle_operation_notification(
                        operation,
                        str(payload.get("method") or ""),
                        payload.get("params") if isinstance(payload.get("params"), dict) else {},
                    )
                elif kind == "server_request":
                    self._handle_server_request(payload, defer_prestart=False)

    def _reject_prestart_server_requests(self, messages: list[tuple[str, dict[str, Any]]]) -> None:
        for kind, payload in messages:
            if kind != "server_request":
                continue
            method = str(payload.get("method") or "")
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            try:
                self._send({
                    "id": payload["id"],
                    "result": self._rejected_server_request_result(method, params),
                })
            except Exception:
                pass

    def _cancel_prestart_requests(self, operation: _Operation) -> None:
        messages = operation.discard_prestart_messages()
        for kind, payload in messages:
            if kind != "notification" or payload.get("method") != "turn/completed":
                continue
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            turn_id = _native_turn_id(params)
            if turn_id:
                self._handle_late_start_terminal(operation.thread_id, turn_id)
        self._reject_prestart_server_requests(messages)

    def _cancel_operation_requests(self, operation: _Operation) -> None:
        for _interaction_id, pending in operation.drain_pending_requests():
            method = str(pending.get("method") or "")
            params = pending.get("params") if isinstance(pending.get("params"), dict) else {}
            try:
                self._send({
                    "id": pending["id"],
                    "result": self._rejected_server_request_result(method, params),
                })
            except Exception:
                pass
        self._clear_pending_approvals(operation.thread_id)

    def _interrupt_turn(self, thread_id: str, turn_id: str) -> bool:
        if not thread_id or not turn_id:
            return False
        try:
            self._send({
                "id": self._allocate_id(),
                "method": "turn/interrupt",
                "params": {"threadId": thread_id, "turnId": turn_id},
            })
            return True
        except Exception:
            return False

    def _register_late_start_cleanup(self, thread_id: str, cleanup: _LateStartCleanup) -> bool:
        with self._late_start_lock:
            existing = self._late_start_cleanups.get(thread_id)
            if existing:
                return existing is cleanup
            if len(self._late_start_cleanups) >= MAX_LATE_START_CLEANUPS + 4:
                return False
            self._late_start_cleanups[thread_id] = cleanup
            return True

    def _late_start_cleanup_pending(self, thread_id: str) -> bool:
        with self._late_start_lock:
            return bool(thread_id and thread_id in self._late_start_cleanups)

    def _late_start_cleanup_capacity_exhausted(self) -> bool:
        with self._late_start_lock:
            return len(self._late_start_cleanups) >= MAX_LATE_START_CLEANUPS

    def _late_start_recycle_required(self) -> bool:
        with self._late_start_lock:
            return any(cleanup.force_recycle for cleanup in self._late_start_cleanups.values())

    def _execute_cleanup_guard(self, thread_id: str) -> dict[str, Any] | None:
        if thread_id and self._late_start_cleanup_pending(thread_id):
            return _error_result(
                "busy",
                "Codex is still stopping a timed-out turn for this thread",
                threadId=thread_id,
                busyReason="late_turn_cleanup",
                busyCode="busy_by_late_turn_cleanup",
            )
        if self._late_start_recycle_required():
            return _error_result(
                "busy",
                "Codex is draining active turns before runtime recovery",
                threadId=thread_id,
                busyReason="late_turn_runtime_recovery",
                busyCode="busy_by_late_turn_runtime_recovery",
            )
        if self._late_start_cleanup_capacity_exhausted():
            return _error_result(
                "busy",
                "Codex late-turn cleanup capacity is exhausted",
                threadId=thread_id,
                busyReason="late_turn_cleanup_capacity",
                busyCode="busy_by_late_turn_cleanup_capacity",
            )
        return None

    def _register_late_start_cleanup_for_generation(
        self,
        thread_id: str,
        cleanup: _LateStartCleanup,
        runtime_generation: int,
    ) -> str:
        """Register cleanup only while the originating runtime is still current."""
        with self._recovery_admission_lock:
            with self._runtime.lifecycle_fence() as current_generation:
                if current_generation != runtime_generation:
                    return "runtime_changed"
                if not self._register_late_start_cleanup(thread_id, cleanup):
                    return "capacity"
                return "registered"

    def _complete_late_start_cleanup(
        self,
        thread_id: str,
        cleanup: _LateStartCleanup,
    ) -> bool:
        with self._late_start_lock:
            active_cleanup = self._late_start_cleanups.get(thread_id)
            if active_cleanup is not cleanup:
                return False
            if self._late_start_cleanups.get(thread_id) is cleanup:
                self._late_start_cleanups.pop(thread_id, None)
                cleanup.event.set()
        return True

    def _bind_late_start_turn(
        self,
        thread_id: str,
        turn_id: str,
        cleanup: _LateStartCleanup,
        operation: _Operation | None = None,
    ) -> bool:
        with self._late_start_lock:
            active_cleanup = self._late_start_cleanups.get(thread_id)
            if active_cleanup is not cleanup:
                return False
            if cleanup.turn_id and cleanup.turn_id != turn_id:
                return False
            cleanup.turn_id = turn_id
            already_terminal = turn_id in cleanup.observed_terminal_turn_ids
            should_interrupt = not cleanup.interrupt_sent and not already_terminal
        if operation is not None and operation.turn_id == turn_id and operation.terminal_observed():
            return self._complete_late_start_cleanup(thread_id, cleanup)
        if already_terminal:
            return self._complete_late_start_cleanup(thread_id, cleanup)
        if should_interrupt and self._interrupt_turn(thread_id, turn_id):
            with self._late_start_lock:
                if self._late_start_cleanups.get(thread_id) is cleanup:
                    cleanup.interrupt_sent = True
        self._schedule_late_start_recovery(thread_id, cleanup)
        return True

    def _handle_late_start_terminal(self, thread_id: str, turn_id: str) -> bool:
        with self._late_start_lock:
            cleanup = self._late_start_cleanups.get(thread_id)
            if cleanup is None:
                return False
            if not cleanup.turn_id:
                if len(cleanup.observed_terminal_turn_ids) >= MAX_OBSERVED_TERMINAL_TURNS:
                    cleanup.observed_terminal_turn_ids.pop()
                cleanup.observed_terminal_turn_ids.add(turn_id)
                return True
            if cleanup.turn_id != turn_id:
                return False
        return self._complete_late_start_cleanup(thread_id, cleanup)

    def _schedule_late_start_recovery(self, thread_id: str, cleanup: _LateStartCleanup) -> None:
        with self._late_start_lock:
            if self._late_start_cleanups.get(thread_id) is not cleanup or cleanup.recovery_scheduled:
                return
            cleanup.recovery_scheduled = True

        def recover_when_idle() -> None:
            with self._runtime_generation_lock:
                with self._recovery_admission_lock:
                    with self._late_start_lock:
                        if self._late_start_cleanups.get(thread_id) is not cleanup:
                            return
                        cleanup.recovery_scheduled = False
                        cleanup.recovery_attempts += 1
                        if cleanup.recovery_attempts >= LATE_START_RECOVERY_MAX_ATTEMPTS:
                            cleanup.force_recycle = True
                    if self._has_active_operations():
                        self._schedule_late_start_recovery(thread_id, cleanup)
                        return
                    self._restart_runtime()

        timer = threading.Timer(LATE_START_RECOVERY_DELAY_SEC, recover_when_idle)
        timer.daemon = True
        timer.start()

    def _handle_late_turn_start_response(
        self,
        thread_id: str,
        cleanup: _LateStartCleanup,
        response: dict[str, Any],
    ) -> None:
        if response.get("error"):
            with self._late_start_lock:
                if self._late_start_cleanups.get(thread_id) is cleanup:
                    self._late_start_cleanups.pop(thread_id, None)
                    cleanup.event.set()
            return
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        turn_id = str((result.get("turn") or {}).get("id") or "")
        if turn_id:
            self._bind_late_start_turn(thread_id, turn_id, cleanup)

    def _fail_prestart_operation(
        self,
        operation: _Operation,
        result: dict[str, Any],
        candidate_turn_ids: list[str],
    ) -> dict[str, Any]:
        operation.result = result
        self._remember_terminal_operation(operation)
        operation.cancel_prestart_visibility()
        terminal_status = "cancelled" if str(result.get("status") or "").lower() in {"cancelled", "canceled"} else "failed"
        operation.emit(
            "turn",
            terminal=True,
            status=terminal_status,
            resultStatus=str(result.get("status") or "failed"),
            error=result.get("error"),
        )
        self._cancel_operation_requests(operation)
        self._cancel_prestart_requests(operation)
        for candidate_turn_id in dict.fromkeys(candidate_turn_ids):
            self._interrupt_turn(operation.thread_id, candidate_turn_id)
        return self._augment_result(operation, result)

    def _remember_terminal_operation(self, operation: _Operation) -> None:
        with self._operations_lock:
            self._terminal_operations[operation.thread_id] = operation
            self._terminal_operations.move_to_end(operation.thread_id)
            while len(self._terminal_operations) > MAX_TERMINAL_DIAGNOSTICS:
                self._terminal_operations.popitem(last=False)

    def terminal_diagnostics(self, thread_id: str) -> dict[str, int | bool]:
        with self._operations_lock:
            operation = self._operations.get(str(thread_id or "")) or self._terminal_operations.get(str(thread_id or ""))
        return operation.fence_diagnostics() if operation else {
            "terminalObserved": False,
            "activeCallbacks": 0,
            "terminalFenceFallbacks": 0,
            "lateNotifications": 0,
            "postTerminalMetrics": 0,
            "callbackErrors": 0,
            "prestartMessageOverflows": 0,
        }

    def wait_for_terminal_callbacks(self, thread_id: str, turn_id: str = "", timeout: float | None = None) -> bool:
        with self._operations_lock:
            operation = self._operations.get(str(thread_id or "")) or self._terminal_operations.get(str(thread_id or ""))
        if operation is None:
            return True
        expected_turn_id = str(turn_id or "")
        if expected_turn_id and operation.turn_id and operation.turn_id != expected_turn_id:
            return True
        return operation.wait_for_callbacks(timeout=timeout)

    def _augment_result(self, operation: _Operation, result: dict[str, Any]) -> dict[str, Any]:
        snapshot = operation.state.snapshot()
        result = dict(result)
        if snapshot.get("reply") and (result.get("ok") or not result.get("reply")):
            result["reply"] = snapshot["reply"]
        result.setdefault("threadId", operation.thread_id)
        result.setdefault("turnId", operation.turn_id)
        result.setdefault("modifiedFiles", sorted(operation.modified_files))
        result["sessionId"] = result.get("threadId") or snapshot.get("sessionId") or ""
        result["runId"] = result.get("turnId") or snapshot.get("runId") or ""
        result["tools"] = result.get("tools") or snapshot.get("tools") or []
        result["thinking"] = result.get("thinking") or snapshot.get("thinking") or ""
        result["approval"] = result.get("approval") or snapshot.get("approval")
        result["tokenUsage"] = result.get("tokenUsage") or snapshot.get("tokenUsage") or {}
        result["terminalFence"] = operation.fence_diagnostics()
        if snapshot.get("error") and not result.get("error"):
            result["error"] = snapshot["error"]
        return result

    def _store_pending_approval(
        self,
        operation: _Operation,
        interaction_id: str,
        method: str,
        params: dict[str, Any],
        approval: dict[str, Any],
    ) -> bool:
        entry = {
            "operation": operation,
            "interactionId": str(interaction_id),
            "method": method,
            "params": params,
            "approval": approval,
        }
        with self._approval_lock:
            if len(self._pending_approvals) >= MAX_PENDING_APPROVALS:
                return False
            self._pending_approvals[str(approval.get("id") or approval.get("approval_id") or interaction_id)] = entry
            self._approval_lock.notify_all()
            return True

    def _clear_pending_approvals(self, thread_id: str = "") -> None:
        with self._approval_lock:
            if thread_id:
                for key, entry in list(self._pending_approvals.items()):
                    approval = entry.get("approval") if isinstance(entry.get("approval"), dict) else {}
                    if str(approval.get("threadId") or "") == thread_id:
                        self._pending_approvals.pop(key, None)
            else:
                self._pending_approvals.clear()

    def pending_approval(self, thread_id: str = "", approval_id: str = "") -> dict[str, Any]:
        approval_id = str(approval_id or "").strip()
        with self._approval_lock:
            pending = [
                dict(item["approval"])
                for item in self._pending_approvals.values()
                if isinstance(item.get("approval"), dict) and item["approval"].get("status") == "pending"
                and (not thread_id or str(item["approval"].get("threadId") or "") == str(thread_id))
            ]
        selected = None
        if approval_id:
            for approval in pending:
                if approval_id in {
                    str(approval.get("id") or ""),
                    str(approval.get("approval_id") or ""),
                    str(approval.get("requestId") or ""),
                    str(approval.get("itemId") or ""),
                    str(approval.get("callbackId") or ""),
                }:
                    selected = approval
                    break
        else:
            selected = pending[0] if pending else None
        return {"ok": True, "pending": selected, "pending_count": len(pending)}

    def respond_approval(self, approval_id: str, choice: str = "cancel") -> dict[str, Any]:
        approval_id = str(approval_id or "").strip()
        normalized_choice = self._normalize_approval_choice(choice)
        response_choice = "acceptForSession" if str(choice or "").strip().lower() == "acceptforsession" else normalized_choice
        if not approval_id:
            return {"ok": False, "error": "approval_id is required"}
        with self._approval_lock:
            entry = self._pending_approvals.get(approval_id)
            if not entry:
                for candidate in self._pending_approvals.values():
                    approval = candidate.get("approval") if isinstance(candidate.get("approval"), dict) else {}
                    if approval_id in {
                        str(approval.get("requestId") or ""),
                        str(approval.get("itemId") or ""),
                        str(approval.get("callbackId") or ""),
                    }:
                        entry = candidate
                        break
            if not entry:
                return {"ok": False, "error": "Codex approval request is no longer pending"}
        operation = entry.get("operation")
        if not isinstance(operation, _Operation):
            return {"ok": False, "error": "Codex approval request is detached from an active turn"}
        interaction_id = str(entry.get("interactionId") or "")
        entry_params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
        entry_turn_id = _native_turn_id(entry_params)
        with self._operations_lock:
            active_operation = self._operations.get(operation.thread_id)
        if active_operation is not operation or (
            entry_turn_id and operation.turn_id and entry_turn_id != operation.turn_id
        ):
            self._reject_pending_approval_entry(operation, interaction_id, entry)
            return {"ok": False, "error": "Codex approval request belongs to a different turn"}
        ok = self.respond(
            operation.thread_id,
            interaction_id,
            response_choice,
            {},
            _expected_operation=operation,
        )
        if not ok:
            if self._reject_pending_approval_entry(operation, interaction_id, entry):
                return {"ok": False, "error": "Codex approval request belongs to a different turn"}
            return {"ok": False, "error": "Codex approval request is no longer pending"}
        resolved = {
            **dict(entry.get("approval") or {}),
            "status": "approved" if normalized_choice == "approve" else "cancelled",
            "resolvedAt": int(time.time() * 1000),
            "choice": response_choice,
        }
        operation.state.set_approval(resolved)
        return {
            "ok": True,
            "approval": resolved,
            "choice": response_choice,
            "response": self._approval_response(entry.get("method") or "", entry.get("params") or {}, response_choice),
        }

    def _reject_pending_approval_entry(
        self,
        operation: _Operation,
        interaction_id: str,
        entry: dict[str, Any],
    ) -> bool:
        pending = operation.pop_pending_request(interaction_id)
        if pending:
            pending_method = str(pending.get("method") or "")
            pending_params = pending.get("params") if isinstance(pending.get("params"), dict) else {}
            self._send({
                "id": pending["id"],
                "result": self._rejected_server_request_result(pending_method, pending_params),
            })
        with self._approval_lock:
            for key, candidate in list(self._pending_approvals.items()):
                if candidate is entry:
                    self._pending_approvals.pop(key, None)
        return pending is not None

    def _approval_from_request(self, message: dict[str, Any]) -> dict[str, Any]:
        method = str(message.get("method") or "")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        request_id = message.get("id")
        thread_id = str(params.get("threadId") or params.get("conversationId") or "")
        turn_id = str(params.get("turnId") or "")
        item_id = str(params.get("itemId") or params.get("callId") or "")
        callback_id = str(params.get("approvalId") or "")
        seed = json.dumps(
            {
                "profile": self.profile,
                "method": method,
                "requestId": request_id,
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": item_id,
                "callbackId": callback_id,
            },
            sort_keys=True,
        )
        approval_id = "codex-approval-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        reason = str(params.get("reason") or "").strip()
        kind = "command"
        title = "Codex approval required"
        description = reason or "Codex needs approval before it can continue."
        if method in {"item/commandExecution/requestApproval", "execCommandApproval"}:
            kind = "command"
            title = "Codex command approval required"
            description = reason or "Codex wants to run a command that needs approval."
        elif method in {"item/fileChange/requestApproval", "applyPatchApproval"}:
            kind = "file_change"
            title = "Codex file-change approval required"
            description = reason or "Codex wants to apply file changes that need approval."
        elif method == "item/permissions/requestApproval":
            kind = "permissions"
            title = "Codex permissions approval required"
            description = reason or "Codex is requesting additional permissions for this turn."
        return {
            "id": approval_id,
            "approval_id": approval_id,
            "provider": "codex-app-server",
            "kind": kind,
            "title": title,
            "description": description,
            "command": self._approval_command_preview(method, params),
            "agentId": f"codex-{self.profile}" if self.profile else "codex-default",
            "profile": self.profile,
            "threadId": thread_id,
            "session_id": thread_id,
            "turnId": turn_id,
            "runId": turn_id,
            "itemId": item_id,
            "callbackId": callback_id,
            "requestId": str(request_id),
            "method": method,
            "status": "pending",
            "choices": ["approve", "cancel"],
            "createdAt": int(time.time() * 1000),
        }

    @staticmethod
    def _approval_command_preview(method: str, params: dict[str, Any]) -> str:
        if method in {"item/commandExecution/requestApproval", "execCommandApproval"}:
            command = params.get("command")
            if isinstance(command, list):
                return " ".join(str(x) for x in command)
            if command:
                return str(command)
            actions = params.get("commandActions") or params.get("parsedCmd") or []
            if isinstance(actions, list) and actions:
                return "\n".join(_limit_text(action) for action in actions[:5])
            return "Codex command"
        if method in {"item/fileChange/requestApproval", "applyPatchApproval"}:
            if isinstance(params.get("fileChanges"), dict):
                files = list(params["fileChanges"].keys())
                return "\n".join(str(f) for f in files[:40]) or "File changes"
            grant_root = params.get("grantRoot")
            return f"Grant write access under: {grant_root}" if grant_root else "File changes"
        if method == "item/permissions/requestApproval":
            return _limit_text(params.get("permissions") or {})
        return "Codex approval request"

    @staticmethod
    def _is_approval_request(method: str) -> bool:
        return method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
            "execCommandApproval",
            "applyPatchApproval",
        }

    @staticmethod
    def _normalize_approval_choice(choice: str) -> str:
        raw = str(choice or "").strip().lower()
        if raw in {"approve", "approved", "accept", "allow", "allow_once", "approve_once", "yes", "acceptforsession"}:
            return "approve"
        return "cancel"

    @classmethod
    def _approval_response(cls, method: str, params: dict[str, Any], choice: str) -> dict[str, Any]:
        approved = cls._normalize_approval_choice(choice) == "approve"
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            decision = "acceptForSession" if approved and choice == "acceptForSession" else "accept"
            return {"decision": decision if approved else "cancel"}
        if method == "item/permissions/requestApproval":
            if approved:
                requested = params.get("permissions") if isinstance(params.get("permissions"), dict) else {}
                granted = {}
                if requested.get("fileSystem") is not None:
                    granted["fileSystem"] = requested.get("fileSystem")
                if requested.get("network") is not None:
                    granted["network"] = requested.get("network")
                return {"permissions": granted, "scope": "session" if choice == "acceptForSession" else "turn"}
            return {"permissions": {"fileSystem": None, "network": None}, "scope": "turn"}
        if method in {"execCommandApproval", "applyPatchApproval"}:
            return {"decision": "approved" if approved else "abort"}
        return {"decision": "cancel"}

    def _approval_policy(self) -> str:
        return "untrusted" if self.route_approvals_through_vo else self.configured_approval_policy

    def _sandbox_policy(self) -> dict[str, Any]:
        if self.sandbox == "danger-full-access":
            return {"type": "dangerFullAccess"}
        if self.sandbox == "read-only":
            return {"type": "readOnly", "networkAccess": False}
        return {
            "type": "workspaceWrite",
            "writableRoots": [self.workspace],
            "networkAccess": False,
        }

    def _thread_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": self.workspace,
            "approvalPolicy": self._approval_policy(),
            # A resumed thread may have been created by Codex Desktop. Override
            # its persisted reviewer so approvals are routed back to this
            # app-server client, where VO can expose them on the source surface.
            "approvalsReviewer": "user",
            "sandbox": self.sandbox,
            "ephemeral": False,
        }
        if self.model:
            params["model"] = self.model
        return params

    def execute(
        self,
        message: str,
        thread_id: str = "",
        timeout_sec: int = 600,
        event_callback: Any = None,
        allow_interaction: bool = False,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        order_key = str(thread_id or f"new:{uuid.uuid4().hex}")
        thread_lock = self._acquire_thread_lock(order_key)
        if not self._turn_capacity.acquire(blocking=False):
            self._release_thread_lock(order_key, thread_lock)
            with self._admission_lock:
                self._admission_counters["busyByCapacity"] += 1
            return _error_result(
                "busy",
                "Codex app-server turn capacity is exhausted",
                busyReason="capacity",
                busyCode="busy_by_capacity",
                maxConcurrentTurns=self.max_concurrent_turns,
            )
        with self._admission_lock:
            self._admission_counters["acceptedTurns"] += 1
            self._admission_counters["activeTurns"] += 1
            self._admission_counters["peakActiveTurns"] = max(
                self._admission_counters["peakActiveTurns"], self._admission_counters["activeTurns"]
            )
        try:
            return self._execute_locked(
                message,
                thread_id=thread_id,
                timeout_sec=timeout_sec,
                event_callback=event_callback,
                allow_interaction=allow_interaction,
                attachments=attachments,
            )
        finally:
            with self._admission_lock:
                self._admission_counters["activeTurns"] = max(0, self._admission_counters["activeTurns"] - 1)
            self._turn_capacity.release()
            self._release_thread_lock(order_key, thread_lock)

    def _acquire_thread_lock(self, key: str) -> threading.Lock:
        with self._thread_locks_guard:
            entry = self._thread_locks.get(key)
            if entry is None:
                entry = {"lock": threading.Lock(), "references": 0}
                self._thread_locks[key] = entry
            entry["references"] += 1
            lock = entry["lock"]
        lock.acquire()
        return lock

    def _release_thread_lock(self, key: str, lock: threading.Lock) -> None:
        lock.release()
        with self._thread_locks_guard:
            entry = self._thread_locks.get(key)
            if not entry or entry.get("lock") is not lock:
                return
            entry["references"] = max(0, int(entry.get("references") or 0) - 1)
            if entry["references"] == 0:
                self._thread_locks.pop(key, None)

    def admission_diagnostics(self) -> dict[str, int]:
        with self._admission_lock:
            counters = dict(self._admission_counters)
        with self._thread_locks_guard:
            ordered_threads = len(self._thread_locks)
        return {**counters, "maxConcurrentTurns": self.max_concurrent_turns, "orderedThreads": ordered_threads}

    def protocol_diagnostics(self) -> dict[str, Any]:
        diagnostics = self._runtime.diagnostics()
        with self._operations_lock:
            diagnostics["activeThreadIds"] = sorted(self._operations.keys())
        diagnostics["pendingApprovalCount"] = self.pending_approval().get("pending_count", 0)
        return diagnostics

    def _execute_locked(
        self,
        message: str,
        thread_id: str = "",
        timeout_sec: int = 600,
        event_callback: Any = None,
        allow_interaction: bool = False,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        guard = self._execute_cleanup_guard(thread_id)
        if guard:
            return guard
        try:
            # Serialize only runtime generation/startup and operation
            # registration. Turns remain concurrent after this short fence.
            with self._runtime_generation_lock:
                with self._recovery_admission_lock:
                    guard = self._execute_cleanup_guard(thread_id)
                    if guard:
                        return guard
                    self._ensure_started()
                    created_or_forked = False
                    if thread_id and allow_interaction and thread_id not in self._owned_thread_ids:
                        result = self._request_with_restart("thread/fork", {"threadId": thread_id, **self._thread_params()}, timeout=self.start_timeout_sec)
                        created_or_forked = True
                    elif thread_id:
                        result = self._request_with_restart("thread/resume", {"threadId": thread_id, **self._thread_params()}, timeout=self.start_timeout_sec)
                    else:
                        result = self._request_with_restart("thread/start", self._thread_params(), timeout=self.start_timeout_sec)
                        created_or_forked = True
                    thread = result.get("thread") or {}
                    active_thread_id = str(thread.get("id") or thread_id)
                    if not active_thread_id:
                        return _error_result("protocol_error", "Codex did not return a thread id")
                    if created_or_forked:
                        self._owned_thread_ids.add(active_thread_id)
                    operation = _Operation(
                        thread_id=active_thread_id,
                        event_callback=event_callback,
                        allow_interaction=allow_interaction,
                    )
                    with self._operations_lock:
                        previous = self._terminal_operations.pop(active_thread_id, None)
                        operation.inherit_turn_history(previous)
                        self._operations[active_thread_id] = operation
            try:
                visibility_timer = None
                late_response = {}
                late_response_ready = threading.Event()
                late_start_cleanup = _LateStartCleanup()
                turn_start_generation = self._runtime.generation

                def handle_late_response(response: dict[str, Any]) -> None:
                    late_response["value"] = response
                    late_response_ready.set()
                    self._handle_late_turn_start_response(active_thread_id, late_start_cleanup, response)

                if operation.event_callback:
                    visibility_timer = threading.Timer(
                        PRESTART_VISIBILITY_DELAY_SEC,
                        operation.emit_prestart_starting,
                    )
                    visibility_timer.daemon = True
                    operation.set_prestart_visibility_timer(visibility_timer)
                    visibility_timer.start()
                turn_params = {
                    "threadId": active_thread_id,
                    "input": _turn_user_input(message, attachments),
                    "summary": self.reasoning_summary,
                    "cwd": self.workspace,
                    "approvalPolicy": self._approval_policy(),
                    "approvalsReviewer": "user",
                    "sandboxPolicy": self._sandbox_policy(),
                }
                turn_result = self._request_with_restart("turn/start", turn_params, timeout=TURN_START_RESPONSE_TIMEOUT_SEC, retry=False, on_late_response=handle_late_response)
            except TimeoutError:
                late_start_cleanup.observed_terminal_turn_ids = operation.prestart_terminal_turn_ids()
                cleanup_status = self._register_late_start_cleanup_for_generation(
                    active_thread_id,
                    late_start_cleanup,
                    turn_start_generation,
                )
                if cleanup_status == "runtime_changed":
                    operation.completed.wait(timeout=1)
                    existing = operation.result or _error_result(
                        "bridge_unavailable",
                        "Codex app-server stopped while starting the turn",
                        threadId=active_thread_id,
                    )
                    return self._augment_result(operation, existing)
                if cleanup_status == "capacity":
                    return self._fail_prestart_operation(operation, _error_result(
                        "bridge_unavailable",
                        "Codex could not reserve late-turn cleanup capacity",
                        threadId=active_thread_id,
                    ), operation.prestart_turn_ids())
                if late_response_ready.is_set():
                    self._handle_late_turn_start_response(
                        active_thread_id,
                        late_start_cleanup,
                        late_response.get("value") or {},
                    )
                self._schedule_late_start_recovery(active_thread_id, late_start_cleanup)
                candidate_turn_ids = operation.prestart_turn_ids()
                if operation.cancel_requested:
                    failure = _error_result(
                        "cancelled",
                        "Codex turn was cancelled before turn/start completed",
                        threadId=active_thread_id,
                        turnId="",
                    )
                else:
                    failure = _error_result(
                        "timeout",
                        "Codex turn/start did not confirm the active turn before the request timeout",
                        threadId=active_thread_id,
                        turnId="",
                    )
                result = self._fail_prestart_operation(operation, failure, candidate_turn_ids)
                return result
            except AppServerResponseError as exc:
                candidate_turn_ids = operation.prestart_turn_ids()
                return self._fail_prestart_operation(operation, _error_result(
                    "execution_failed",
                    str(exc),
                    threadId=active_thread_id,
                    turnId="",
                ), candidate_turn_ids)
            except Exception as exc:
                late_start_cleanup.observed_terminal_turn_ids = operation.prestart_terminal_turn_ids()
                cleanup_status = self._register_late_start_cleanup_for_generation(
                    active_thread_id,
                    late_start_cleanup,
                    turn_start_generation,
                )
                if cleanup_status == "runtime_changed":
                    operation.completed.wait(timeout=1)
                    existing = operation.result or _error_result(
                        "bridge_unavailable",
                        "Codex app-server stopped while starting the turn",
                        threadId=active_thread_id,
                    )
                    return self._augment_result(operation, existing)
                if cleanup_status == "capacity":
                    return self._fail_prestart_operation(operation, _error_result(
                        "bridge_unavailable",
                        "Codex could not reserve late-turn cleanup capacity",
                        threadId=active_thread_id,
                    ), operation.prestart_turn_ids())
                self._schedule_late_start_recovery(active_thread_id, late_start_cleanup)
                candidate_turn_ids = operation.prestart_turn_ids()
                return self._fail_prestart_operation(operation, _error_result(
                    "execution_failed",
                    str(exc),
                    threadId=active_thread_id,
                    turnId="",
                ), candidate_turn_ids)
            finally:
                operation.cancel_prestart_visibility()
            returned_turn_id = str((turn_result.get("turn") or {}).get("id") or "")
            if not returned_turn_id or not operation.confirm_turn_identity(returned_turn_id):
                candidate_turn_ids = operation.prestart_turn_ids()
                if returned_turn_id:
                    candidate_turn_ids.append(returned_turn_id)
                late_start_cleanup.observed_terminal_turn_ids = operation.prestart_terminal_turn_ids()
                self._register_late_start_cleanup(active_thread_id, late_start_cleanup)
                if returned_turn_id:
                    self._bind_late_start_turn(active_thread_id, returned_turn_id, late_start_cleanup, operation)
                else:
                    self._schedule_late_start_recovery(active_thread_id, late_start_cleanup)
                result = self._fail_prestart_operation(operation, _error_result(
                    "protocol_error",
                    "Codex turn/start did not return a valid turn id" if not returned_turn_id
                    else "Codex emitted too many messages before the turn/start response",
                    threadId=active_thread_id,
                    turnId=returned_turn_id,
                ), candidate_turn_ids)
                return result
            if operation.cancel_requested:
                self._interrupt_turn(active_thread_id, returned_turn_id)
            if not self._replay_prestart_messages(operation):
                cleanup = _LateStartCleanup(
                    observed_terminal_turn_ids=operation.prestart_terminal_turn_ids(),
                )
                self._register_late_start_cleanup(active_thread_id, cleanup)
                self._bind_late_start_turn(active_thread_id, returned_turn_id, cleanup, operation)
                return self._fail_prestart_operation(operation, _error_result(
                    "protocol_error",
                    "Codex emitted too many messages while replaying pre-start events",
                    threadId=active_thread_id,
                    turnId=returned_turn_id,
                ), [returned_turn_id])
            if not operation.completed.wait(timeout=max(1, int(timeout_sec))):
                cleanup = _LateStartCleanup()
                if self._register_late_start_cleanup(active_thread_id, cleanup):
                    self._bind_late_start_turn(active_thread_id, operation.turn_id, cleanup, operation)
                else:
                    self._interrupt_turn(active_thread_id, operation.turn_id)
                return _error_result("timeout", "Codex call timed out", threadId=active_thread_id, turnId=operation.turn_id)
            result = operation.result or _error_result("execution_failed", "Codex turn ended without a result", threadId=active_thread_id, turnId=operation.turn_id)
            result = self._augment_result(operation, result)
            result["durationMs"] = int((time.monotonic() - started) * 1000)
            return result
        except FileNotFoundError:
            return _error_result("bridge_unavailable", f"Codex CLI not found at {self.binary}")
        except TimeoutError as exc:
            return _error_result("timeout", str(exc), threadId=thread_id)
        except Exception as exc:
            return _error_result("bridge_unavailable", str(exc), threadId=thread_id)
        finally:
            if 'active_thread_id' in locals():
                self._clear_pending_approvals(active_thread_id)
                with self._operations_lock:
                    self._operations.pop(active_thread_id, None)

    def send_chat_message(
        self,
        message: str,
        *,
        session_id: str = "",
        timeout_sec: int = 600,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        def event_callback(event: dict[str, Any]) -> None:
            if not callable(on_progress):
                return
            thread_id = str(event.get("threadId") or session_id or "")
            with self._operations_lock:
                operation = self._operations.get(thread_id)
            if operation:
                on_progress(operation.state.snapshot())
            else:
                on_progress({
                    "reply": "",
                    "sessionId": thread_id,
                    "threadId": thread_id,
                    "runId": str(event.get("turnId") or ""),
                    "turnId": str(event.get("turnId") or ""),
                    "status": event.get("status") or "running",
                    "tools": [event] if event.get("type") == "activity" else [],
                    "thinking": event.get("text") if event.get("type") == "reasoning" else "",
                    "approval": event if event.get("type") == "interaction" and event.get("status") == "pending" else None,
                    "tokenUsage": {},
                })

        return self.execute(
            message,
            thread_id=session_id,
            timeout_sec=timeout_sec,
            event_callback=event_callback,
            allow_interaction=True,
        )

    def respond(
        self,
        thread_id: str,
        interaction_id: str,
        action: str,
        answers: dict[str, Any] | None = None,
        *,
        _expected_operation: _Operation | None = None,
    ) -> bool:
        with self._operations_lock:
            operation = self._operations.get(thread_id)
            if not operation or (_expected_operation is not None and operation is not _expected_operation):
                return False
        pending = operation.pop_pending_request(str(interaction_id))
        if not pending:
            return False
        method = pending["method"]
        if method == "item/tool/requestUserInput":
            normalized_answers = {}
            for key, value in (answers or {}).items():
                if isinstance(value, dict) and isinstance(value.get("answers"), list):
                    normalized_answers[str(key)] = value
                elif isinstance(value, list):
                    normalized_answers[str(key)] = {"answers": [str(item) for item in value]}
                else:
                    normalized_answers[str(key)] = {"answers": [str(value)]}
            result = {"answers": normalized_answers}
        elif method == "mcpServer/elicitation/request":
            result = {"action": "accept" if action == "accept" else "decline", "content": answers or {}}
        elif self._is_approval_request(method):
            result = self._approval_response(method, pending.get("params") or {}, action)
        else:
            decisions = {
                "accept": "accept",
                "acceptForSession": "acceptForSession",
                "approve": "accept",
                "approved": "accept",
                "allow": "accept",
                "decline": "decline",
                "cancel": "cancel",
            }
            result = {"decision": decisions.get(action, "decline")}
        self._send({"id": pending["id"], "result": result})
        approval = pending.get("approval") if isinstance(pending.get("approval"), dict) else None
        if approval:
            resolved = {
                **approval,
                "status": "approved" if action in {"accept", "acceptForSession", "approve", "approved", "allow"} else "cancelled",
                "resolvedAt": int(time.time() * 1000),
                "choice": action,
            }
            operation.state.set_approval(resolved)
            with self._approval_lock:
                self._pending_approvals.pop(str(approval.get("id") or approval.get("approval_id") or interaction_id), None)
        operation.emit(
            "interaction",
            status="resolved",
            interactionId=str(interaction_id),
            interactionType=pending["type"],
            method=method,
            output={"action": action},
        )
        return True

    def cancel(self, thread_id: str) -> bool:
        with self._operations_lock:
            operation = self._operations.get(thread_id)
        if not operation:
            return False
        operation.cancel_prestart_visibility(mark_cancelled=True)
        for _interaction_id, pending in operation.drain_pending_requests():
            method = pending["method"]
            if method == "item/tool/requestUserInput":
                result = {"answers": {}}
            elif method == "mcpServer/elicitation/request":
                result = {"action": "decline"}
            elif self._is_approval_request(method):
                result = self._approval_response(method, pending.get("params") or {}, "cancel")
            else:
                result = {"decision": "cancel"}
            self._send({"id": pending["id"], "result": result})
        self._clear_pending_approvals(thread_id)
        if operation.turn_id:
            request_id = self._allocate_id()
            self._send({"id": request_id, "method": "turn/interrupt", "params": {"threadId": thread_id, "turnId": operation.turn_id}})
        operation.emit("turn", status="cancelling")
        return True

    def _compact_cleanup_guard(self, thread_id: str) -> dict[str, Any] | None:
        if self._late_start_cleanup_pending(thread_id):
            return _error_result(
                "busy",
                "Codex is still stopping a timed-out turn for this thread",
                threadId=thread_id,
                busyReason="late_turn_cleanup",
                busyCode="busy_by_late_turn_cleanup",
            )
        if self._late_start_recycle_required() or self._late_start_cleanup_capacity_exhausted():
            return _error_result(
                "busy",
                "Codex runtime recovery must complete before context compression",
                threadId=thread_id,
                busyReason="late_turn_runtime_recovery",
                busyCode="busy_by_late_turn_runtime_recovery",
            )
        return None

    def compact(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        if not thread_id:
            return _error_result("not_found", "No Codex context exists for this conversation")
        guard = self._compact_cleanup_guard(thread_id)
        if guard:
            return guard
        thread_lock = self._acquire_thread_lock(thread_id)
        guard = self._compact_cleanup_guard(thread_id)
        if guard:
            self._release_thread_lock(thread_id, thread_lock)
            return guard
        if not self._turn_capacity.acquire(blocking=False):
            self._release_thread_lock(thread_id, thread_lock)
            with self._admission_lock:
                self._admission_counters["busyByCapacity"] += 1
            return _error_result("busy", "Codex app-server turn capacity is exhausted", busyReason="capacity", busyCode="busy_by_capacity")
        try:
            return self._compact_locked(thread_id, timeout_sec=timeout_sec)
        finally:
            self._turn_capacity.release()
            self._release_thread_lock(thread_id, thread_lock)

    def _compact_locked(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        started = time.monotonic()
        try:
            with self._runtime_generation_lock:
                with self._recovery_admission_lock:
                    guard = self._compact_cleanup_guard(thread_id)
                    if guard:
                        return guard
                    self._ensure_started()
                    self._request_with_restart("thread/resume", {"threadId": thread_id, **self._thread_params()}, timeout=30)
                    operation = _Operation(thread_id=thread_id, kind="compact")
                    with self._operations_lock:
                        previous = self._terminal_operations.pop(thread_id, None)
                        operation.inherit_turn_history(previous)
                        self._operations[thread_id] = operation
            self._request("thread/compact/start", {"threadId": thread_id}, timeout=30)
            if not operation.completed.wait(timeout=max(1, int(timeout_sec))):
                return _error_result("timeout", "Codex context compression timed out", threadId=thread_id)
            result = operation.result or {
                "ok": True,
                "status": "compacted",
                "reply": "Codex context compressed.",
                "threadId": thread_id,
                "turnId": "",
                "modifiedFiles": [],
                "needsHumanIntervention": False,
            }
            result["durationMs"] = int((time.monotonic() - started) * 1000)
            return result
        except Exception as exc:
            return _error_result("execution_failed", str(exc), threadId=thread_id)
        finally:
            self._clear_pending_approvals(thread_id)
            with self._operations_lock:
                self._operations.pop(thread_id, None)


class CodexHttpBridgeClient:
    """External bridge adapter using the same normalized result contract."""

    def __init__(self, base_url: str, workspace: str, model: str = ""):
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.model = model

    def _post(self, path: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                data = json.loads(response.read().decode())
            return data if isinstance(data, dict) else _error_result("protocol_error", "External Codex bridge returned a non-object response")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:2000]
            return _error_result("execution_failed", body or f"External Codex bridge returned HTTP {exc.code}")
        except Exception as exc:
            return _error_result("bridge_unavailable", str(exc))

    def execute(self, message: str, thread_id: str = "", timeout_sec: int = 600, attachments: list[dict[str, Any]] | None = None, **_kwargs: Any) -> dict[str, Any]:
        return self._post("/execute", {"message": message, "threadId": thread_id, "workspace": self.workspace, "model": self.model, "timeoutSec": timeout_sec, "attachments": attachments or []}, timeout_sec + 10)

    def compact(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        return self._post("/compact", {"threadId": thread_id, "workspace": self.workspace, "timeoutSec": timeout_sec}, timeout_sec + 10)


_CLIENTS: dict[tuple[str, str, str, str, int, bool, str, str], CodexAppServerClient | CodexHttpBridgeClient] = {}
_CLIENTS_LOCK = threading.Lock()


def get_codex_bridge(workspace: str, model: str = "", bridge_url: str = "", *, max_concurrent_turns: int = 1, route_approvals_through_vo: bool = False, home_path: str = "", sandbox: str = "workspace-write", approval_policy: str = "on-request") -> CodexAppServerClient | CodexHttpBridgeClient:
    try:
        capacity = max(1, min(int(max_concurrent_turns or 1), 4))
    except (TypeError, ValueError):
        capacity = 1
    route_in_vo = bool(route_approvals_through_vo)
    resolved_sandbox = CodexAppServerClient._normalize_sandbox(sandbox)
    resolved_approval_policy = CodexAppServerClient._normalize_approval_policy(approval_policy)
    resolved_home = os.path.abspath(os.path.expanduser(home_path or os.environ.get("VO_CODEX_HOME") or os.environ.get("CODEX_HOME") or "~/.codex"))
    key = (os.path.abspath(workspace), resolved_home, model or "", bridge_url or "", capacity, route_in_vo, resolved_sandbox, resolved_approval_policy)
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            client = CodexHttpBridgeClient(bridge_url, workspace, model) if bridge_url else CodexAppServerClient(
                workspace,
                model,
                max_concurrent_turns=capacity,
                route_approvals_through_vo=route_in_vo,
                home_path=resolved_home,
                sandbox=resolved_sandbox,
                approval_policy=resolved_approval_policy,
            )
            _CLIENTS[key] = client
        return client
