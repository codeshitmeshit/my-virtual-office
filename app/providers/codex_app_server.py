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
from dataclasses import dataclass, field
from typing import Any

from provider_app_server import JsonlAppServerRuntime


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

    def emit(self, event_type: str, **data: Any) -> None:
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
        if self.event_callback:
            self.event_callback(event)


class CodexAppServerClient:
    """Small synchronous facade over app-server's bidirectional JSONL RPC."""

    def __init__(self, workspace: str, model: str = "", binary: str | None = None):
        self.workspace = os.path.abspath(workspace)
        self.model = model or ""
        self.binary = binary or os.environ.get("VO_CODEX_BIN") or shutil.which("codex") or "codex"
        self.profile = str(os.environ.get("VO_CODEX_PROFILE") or "").strip()
        try:
            self.start_timeout_sec = max(0.1, float(os.environ.get("VO_CODEX_START_TIMEOUT_SEC") or 30))
        except (TypeError, ValueError):
            self.start_timeout_sec = 30.0
        summary = str(os.environ.get("VO_CODEX_REASONING_SUMMARY") or "detailed").strip().lower()
        self.reasoning_summary = summary if summary in {"auto", "concise", "detailed", "none"} else "detailed"
        self._runtime = JsonlAppServerRuntime(
            [self.binary, "app-server", "--stdio"],
            cwd=self.workspace,
            name="codex-app-server",
            stderr=subprocess.PIPE,
        )
        self._runtime.on_server_request = self._handle_server_request
        self._runtime.on_notification = self._handle_notification
        self._runtime.on_exit = self._handle_runtime_exit
        self._operations: dict[str, _Operation] = {}
        self._operations_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._approval_lock = threading.Condition()
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self._runtime.close()

    def probe_auth(self, timeout_sec: int = 15) -> dict[str, Any]:
        """Initialize Codex app-server and read account/auth state."""
        init: dict[str, Any] = {}
        account: dict[str, Any] = {}
        try:
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
        if self._runtime.is_running():
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
        return init

    def _send(self, message: dict[str, Any]) -> None:
        self._runtime.send(message)

    def _request(self, method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        return self._runtime.request(method, params, timeout=timeout).get("result") or {}

    def _restart_runtime(self) -> None:
        try:
            self._runtime.close()
        except Exception:
            pass

    def _request_with_restart(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float = 30,
        retry: bool = True,
    ) -> dict[str, Any]:
        try:
            return self._request(method, params, timeout=timeout)
        except TimeoutError:
            if not retry:
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
        with self._operations_lock:
            operations = list(self._operations.values())
        detail = self._runtime.stderr_text()
        message = "Codex app-server stopped unexpectedly"
        if detail:
            message = f"{message}: {detail}"
        for operation in operations:
            if not operation.completed.is_set():
                operation.result = _error_result("bridge_unavailable", message, threadId=operation.thread_id, turnId=operation.turn_id)
                operation.completed.set()
        self._clear_pending_approvals()

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message.get("method", "")
        params = message.get("params") or {}
        thread_id = str(params.get("threadId") or "")
        with self._operations_lock:
            operation = self._operations.get(thread_id)
        if method in APPROVAL_METHODS:
            if operation and operation.allow_interaction:
                request_key = str(message["id"])
                interaction_type = "input" if method in {"item/tool/requestUserInput", "mcpServer/elicitation/request"} else "approval"
                approval = self._approval_from_request(message) if interaction_type == "approval" else None
                operation.pending_requests[request_key] = {
                    "id": message["id"],
                    "method": method,
                    "params": params,
                    "type": interaction_type,
                    "approval": approval,
                }
                if approval:
                    if not self._store_pending_approval(operation, request_key, method, params, approval):
                        operation.pending_requests.pop(request_key, None)
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
                    operation.state.set_approval(approval)
                operation.emit(
                    "interaction",
                    status="pending",
                    interactionId=request_key,
                    interactionType=interaction_type,
                    method=method,
                    itemId=str(params.get("itemId") or ""),
                    input=params,
                )
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
                operation.completed.set()
            return
        self._send({"id": message["id"], "error": {"code": -32601, "message": f"Unsupported server request: {method}"}})

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        thread_id = str(params.get("threadId") or "")
        with self._operations_lock:
            operation = self._operations.get(thread_id)
        if not operation:
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
            operation.emit(
                "turn",
                status=operation.result.get("status") if operation.result else str(turn.get("status") or "failed"),
                output={"reply": operation.state.reply_text() or operation.reply, "modifiedFiles": sorted(operation.modified_files)},
                error=(operation.result or {}).get("error"),
            )
            operation.completed.set()
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
            operation.completed.set()

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

    def pending_approval(self) -> dict[str, Any]:
        with self._approval_lock:
            pending = [
                dict(item["approval"])
                for item in self._pending_approvals.values()
                if isinstance(item.get("approval"), dict) and item["approval"].get("status") == "pending"
            ]
        return {"ok": True, "pending": pending[0] if pending else None, "pending_count": len(pending)}

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
        ok = self.respond(operation.thread_id, interaction_id, response_choice, {})
        if not ok:
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

    def _thread_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": self.workspace,
            "approvalPolicy": "on-request",
            "sandbox": "workspace-write",
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
    ) -> dict[str, Any]:
        with self._run_lock:
            return self._execute_locked(
                message,
                thread_id=thread_id,
                timeout_sec=timeout_sec,
                event_callback=event_callback,
                allow_interaction=allow_interaction,
            )

    def _execute_locked(
        self,
        message: str,
        thread_id: str = "",
        timeout_sec: int = 600,
        event_callback: Any = None,
        allow_interaction: bool = False,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            self._ensure_started()
            if thread_id:
                result = self._request_with_restart("thread/resume", {"threadId": thread_id, **self._thread_params()}, timeout=self.start_timeout_sec)
            else:
                result = self._request_with_restart("thread/start", self._thread_params(), timeout=self.start_timeout_sec)
            thread = result.get("thread") or {}
            active_thread_id = str(thread.get("id") or thread_id)
            if not active_thread_id:
                return _error_result("protocol_error", "Codex did not return a thread id")
            operation = _Operation(
                thread_id=active_thread_id,
                event_callback=event_callback,
                allow_interaction=allow_interaction,
            )
            with self._operations_lock:
                self._operations[active_thread_id] = operation
            turn_result = self._request_with_restart("turn/start", {
                "threadId": active_thread_id,
                "input": [{"type": "text", "text": message}],
                "summary": self.reasoning_summary,
                "cwd": self.workspace,
                "approvalPolicy": "on-request",
                "sandboxPolicy": {
                    "type": "workspaceWrite",
                    "writableRoots": [self.workspace],
                    "networkAccess": False,
                },
            }, timeout=30, retry=False)
            operation.turn_id = str((turn_result.get("turn") or {}).get("id") or "")
            if not operation.completed.wait(timeout=max(1, int(timeout_sec))):
                try:
                    self._request("turn/interrupt", {"threadId": active_thread_id, "turnId": operation.turn_id}, timeout=5)
                except Exception:
                    pass
                return _error_result("timeout", "Codex call timed out", threadId=active_thread_id, turnId=operation.turn_id)
            result = operation.result or _error_result("execution_failed", "Codex turn ended without a result", threadId=active_thread_id, turnId=operation.turn_id)
            time.sleep(0.2)
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

    def respond(self, thread_id: str, interaction_id: str, action: str, answers: dict[str, Any] | None = None) -> bool:
        with self._operations_lock:
            operation = self._operations.get(thread_id)
        if not operation:
            return False
        pending = operation.pending_requests.pop(str(interaction_id), None)
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
        operation.cancel_requested = True
        for interaction_id, pending in list(operation.pending_requests.items()):
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
            operation.pending_requests.pop(interaction_id, None)
        self._clear_pending_approvals(thread_id)
        if operation.turn_id:
            request_id = self._allocate_id()
            self._send({"id": request_id, "method": "turn/interrupt", "params": {"threadId": thread_id, "turnId": operation.turn_id}})
        operation.emit("turn", status="cancelling")
        return True

    def compact(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        if not thread_id:
            return _error_result("not_found", "No Codex context exists for this conversation")
        with self._run_lock:
            return self._compact_locked(thread_id, timeout_sec=timeout_sec)

    def _compact_locked(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        started = time.monotonic()
        try:
            self._ensure_started()
            self._request_with_restart("thread/resume", {"threadId": thread_id, **self._thread_params()}, timeout=30)
            operation = _Operation(thread_id=thread_id, kind="compact")
            with self._operations_lock:
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

    def execute(self, message: str, thread_id: str = "", timeout_sec: int = 600) -> dict[str, Any]:
        return self._post("/execute", {"message": message, "threadId": thread_id, "workspace": self.workspace, "model": self.model, "timeoutSec": timeout_sec}, timeout_sec + 10)

    def compact(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        return self._post("/compact", {"threadId": thread_id, "workspace": self.workspace, "timeoutSec": timeout_sec}, timeout_sec + 10)


_CLIENTS: dict[tuple[str, str, str], CodexAppServerClient | CodexHttpBridgeClient] = {}
_CLIENTS_LOCK = threading.Lock()


def get_codex_bridge(workspace: str, model: str = "", bridge_url: str = "") -> CodexAppServerClient | CodexHttpBridgeClient:
    key = (os.path.abspath(workspace), model or "", bridge_url or "")
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            client = CodexHttpBridgeClient(bridge_url, workspace, model) if bridge_url else CodexAppServerClient(workspace, model)
            _CLIENTS[key] = client
        return client
