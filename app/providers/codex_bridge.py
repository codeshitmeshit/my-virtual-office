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
from dataclasses import dataclass, field
from typing import Any


APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "execCommandApproval",
    "applyPatchApproval",
    "item/tool/requestUserInput",
    "mcpServer/elicitation/request",
}


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
        summary = str(os.environ.get("VO_CODEX_REASONING_SUMMARY") or "detailed").strip().lower()
        self.reasoning_summary = summary if summary in {"auto", "concise", "detailed", "none"} else "detailed"
        self._proc: subprocess.Popen[str] | None = None
        self._write_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._operations: dict[str, _Operation] = {}
        self._operations_lock = threading.Lock()
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._reader: threading.Thread | None = None

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _ensure_started(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        with self._start_lock:
            if self._proc and self._proc.poll() is None:
                return
            self._proc = subprocess.Popen(
                [self.binary, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # App-server protocol data is on stdout. Leaving stderr as an
                # unread pipe can deadlock long tool/file turns when it fills.
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=self.workspace,
            )
            self._reader = threading.Thread(target=self._read_loop, name="codex-app-server", daemon=True)
            self._reader.start()
            self._request("initialize", {
                "clientInfo": {
                    "name": "my_virtual_office",
                    "title": "My Virtual Office",
                    "version": "codex-live-bridge",
                }
            }, timeout=15)
            self._send({"method": "initialized", "params": {}})

    def _send(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if not proc or proc.poll() is not None or not proc.stdin:
            raise RuntimeError("Codex app-server is not running")
        with self._write_lock:
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            proc.stdin.flush()

    def _request(self, method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        request_id = self._allocate_id()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue
        try:
            self._send({"id": request_id, "method": method, "params": params})
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError(f"Codex app-server request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if response.get("error"):
            error = response["error"]
            raise RuntimeError(error.get("message") if isinstance(error, dict) else str(error))
        return response.get("result") or {}

    def _allocate_id(self) -> int:
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def _read_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        try:
            for raw in proc.stdout:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "id" in message and ("result" in message or "error" in message):
                    with self._pending_lock:
                        target = self._pending.get(message["id"])
                    if target:
                        target.put(message)
                    continue
                if "id" in message and message.get("method"):
                    self._handle_server_request(message)
                    continue
                self._handle_notification(message.get("method", ""), message.get("params") or {})
        finally:
            with self._operations_lock:
                operations = list(self._operations.values())
            for operation in operations:
                if not operation.completed.is_set():
                    operation.result = _error_result("bridge_unavailable", "Codex app-server stopped unexpectedly", threadId=operation.thread_id, turnId=operation.turn_id)
                    operation.completed.set()

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message.get("method", "")
        params = message.get("params") or {}
        thread_id = str(params.get("threadId") or "")
        with self._operations_lock:
            operation = self._operations.get(thread_id)
        if method in APPROVAL_METHODS:
            if operation and operation.allow_interaction and method != "item/permissions/requestApproval":
                request_key = str(message["id"])
                interaction_type = "input" if method in {"item/tool/requestUserInput", "mcpServer/elicitation/request"} else "approval"
                operation.pending_requests[request_key] = {
                    "id": message["id"],
                    "method": method,
                    "params": params,
                    "type": interaction_type,
                }
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
        if method == "turn/started":
            turn = params.get("turn") or {}
            operation.turn_id = str(turn.get("id") or params.get("turnId") or operation.turn_id)
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
                    if change.get("path"):
                        operation.modified_files.add(str(change["path"]))
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
                        if change.get("path"):
                            operation.modified_files.add(str(change["path"]))
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
                    "reply": operation.reply,
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
                output={"reply": operation.reply, "modifiedFiles": sorted(operation.modified_files)},
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
        started = time.monotonic()
        try:
            self._ensure_started()
            if thread_id:
                result = self._request("thread/resume", {"threadId": thread_id, **self._thread_params()}, timeout=30)
            else:
                result = self._request("thread/start", self._thread_params(), timeout=30)
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
            turn_result = self._request("turn/start", {
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
            }, timeout=30)
            operation.turn_id = str((turn_result.get("turn") or {}).get("id") or "")
            if not operation.completed.wait(timeout=max(1, int(timeout_sec))):
                try:
                    self._request("turn/interrupt", {"threadId": active_thread_id, "turnId": operation.turn_id}, timeout=5)
                except Exception:
                    pass
                return _error_result("timeout", "Codex call timed out", threadId=active_thread_id, turnId=operation.turn_id)
            result = operation.result or _error_result("execution_failed", "Codex turn ended without a result", threadId=active_thread_id, turnId=operation.turn_id)
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
                with self._operations_lock:
                    self._operations.pop(active_thread_id, None)

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
        elif method == "item/permissions/requestApproval":
            result = {"permissions": (answers or {}).get("permissions", {}), "scope": "turn"}
        else:
            decisions = {"accept": "accept", "acceptForSession": "acceptForSession", "decline": "decline", "cancel": "cancel"}
            result = {"decision": decisions.get(action, "decline")}
        self._send({"id": pending["id"], "result": result})
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
            else:
                result = {"decision": "cancel"}
            self._send({"id": pending["id"], "result": result})
            operation.pending_requests.pop(interaction_id, None)
        if operation.turn_id:
            request_id = self._allocate_id()
            self._send({"id": request_id, "method": "turn/interrupt", "params": {"threadId": thread_id, "turnId": operation.turn_id}})
        operation.emit("turn", status="cancelling")
        return True

    def compact(self, thread_id: str, timeout_sec: int = 120) -> dict[str, Any]:
        if not thread_id:
            return _error_result("not_found", "No Codex context exists for this conversation")
        started = time.monotonic()
        try:
            self._ensure_started()
            self._request("thread/resume", {"threadId": thread_id, **self._thread_params()}, timeout=30)
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
