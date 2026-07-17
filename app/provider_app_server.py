"""Generic JSONL app-server runtime for provider protocol adapters."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Callable


MAX_PENDING_REQUESTS = 1000
READER_DRAIN_WAIT_SEC = 0.25
MAX_PROTOCOL_DIAGNOSTICS = 100


class AppServerResponseError(RuntimeError):
    """The app-server returned an explicit JSON-RPC error response."""


class JsonlAppServerRuntime:
    """Provider-neutral subprocess JSONL-RPC runtime.

    Protocol adapters own method names and payload semantics. This runtime only
    owns process lifecycle, request/response routing, reader-loop dispatch, and
    deterministic cleanup of pending requests.
    """

    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        name: str = "provider-app-server",
        stderr: Any = subprocess.DEVNULL,
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ):
        self.command = command
        self.cwd = cwd
        self.env = env
        self.name = name
        self.stderr = stderr
        self.popen_factory = popen_factory
        self._proc: Any = None
        self._generation = 0
        self._write_lock = threading.Lock()
        self._start_lock = threading.RLock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._late_response_callbacks: OrderedDict[int, Callable[[dict[str, Any]], None]] = OrderedDict()
        self._pending_lock = threading.Lock()
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._reader_drained: threading.Event | None = None
        self._exit_notification_generation: int | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._stderr_lock = threading.Lock()
        self._diagnostic_lock = threading.Lock()
        self._inbound_counts: dict[str, int] = {}
        self._recent_inbound: list[dict[str, Any]] = []
        self.on_server_request: Callable[[dict[str, Any]], None] | None = None
        self.on_notification: Callable[[str, dict[str, Any]], None] | None = None
        self.on_exit: Callable[[], None] | None = None

    @property
    def process(self) -> Any:
        return self._proc

    @property
    def generation(self) -> int:
        return self._generation

    @contextmanager
    def lifecycle_fence(self):
        """Keep process generation stable across adapter admission decisions."""
        with self._start_lock:
            yield self._generation

    def is_running(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    def start(self) -> None:
        if self.is_running():
            return
        reader_drained = None
        with self._start_lock:
            if self.is_running():
                return
            if self._exit_notification_generation is not None:
                raise RuntimeError("App-server exit cleanup is still in progress")
            if self._proc is not None:
                reader_drained = self._reader_drained
        if reader_drained is not None:
            # A terminated process may still have responses buffered in stdout.
            # Let its reader drain and own exit finalization before replacement.
            reader_drained.wait(timeout=READER_DRAIN_WAIT_SEC)
        with self._start_lock:
            if self.is_running():
                return
            if self._exit_notification_generation is not None:
                raise RuntimeError("App-server exit cleanup is still in progress")
            if self._proc is not None:
                raise RuntimeError("Previous app-server reader is still draining")
            self._generation += 1
            generation = self._generation
            reader_drained = threading.Event()
            proc = self.popen_factory(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                text=True,
                bufsize=1,
                cwd=self.cwd,
                env=self.env,
            )
            self._proc = proc
            self._reader_drained = reader_drained
            self._reader = threading.Thread(
                target=self._read_loop,
                args=(proc, generation, reader_drained),
                name=self.name,
                daemon=True,
            )
            self._reader.start()
            if getattr(proc, "stderr", None):
                self._stderr_reader = threading.Thread(
                    target=self._read_stderr_loop,
                    args=(proc.stderr, generation),
                    name=f"{self.name}-stderr",
                    daemon=True,
                )
                self._stderr_reader.start()

    def close(self) -> None:
        with self._start_lock:
            proc = self._proc
            self._proc = None
            self._generation += 1
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            self._fail_pending("App-server closed")

    def allocate_id(self) -> int:
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def send(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if not proc or proc.poll() is not None or not proc.stdin:
            detail = self.stderr_text()
            raise RuntimeError(f"App-server is not running{': ' + detail if detail else ''}")
        with self._write_lock:
            proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            proc.stdin.flush()

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30,
        on_late_response: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        self.start()
        request_id = self.allocate_id()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            if len(self._pending) + len(self._late_response_callbacks) >= MAX_PENDING_REQUESTS:
                raise RuntimeError("App-server pending request capacity reached")
            self._pending[request_id] = response_queue
        response: dict[str, Any] | None = None
        try:
            self.send({"id": request_id, "method": method, "params": params or {}})
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
                try:
                    response = response_queue.get_nowait()
                except queue.Empty:
                    if on_late_response:
                        self._late_response_callbacks[request_id] = on_late_response
                        self._late_response_callbacks.move_to_end(request_id)
            if response is None:
                raise TimeoutError(f"App-server request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        assert response is not None
        if response.get("error"):
            error = response["error"]
            error_type = RuntimeError if response.get("_transportError") else AppServerResponseError
            raise error_type(error.get("message") if isinstance(error, dict) else str(error))
        return response

    def _finalize_generation_exit_locked(self, generation: int) -> tuple[Callable[[], None] | None, int]:
        """Finish one natural process exit before a replacement can start."""
        if generation != self._generation:
            return None, 0
        self._proc = None
        self._generation += 1
        exit_generation = self._generation
        reason = self.stderr_text()
        self._fail_pending(f"App-server stopped{': ' + reason if reason else ''}")
        callback = self.on_exit
        if callback:
            self._exit_notification_generation = exit_generation
        return callback, exit_generation

    def _notify_exit(self, callback: Callable[[], None] | None, exit_generation: int) -> None:
        if not callback:
            return
        try:
            callback()
        finally:
            with self._start_lock:
                if self._exit_notification_generation == exit_generation:
                    self._exit_notification_generation = None

    def _read_loop(self, proc: Any, generation: int, reader_drained: threading.Event) -> None:
        if not proc or not proc.stdout:
            return
        try:
            for raw in proc.stdout:
                if generation != self._generation:
                    return
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._record_inbound(message, generation)
                if "id" in message and ("result" in message or "error" in message) and not message.get("method"):
                    late_callback = None
                    with self._pending_lock:
                        target = self._pending.pop(message["id"], None)
                        if target:
                            target.put_nowait(message)
                        else:
                            late_callback = self._late_response_callbacks.pop(message["id"], None)
                    if late_callback:
                        try:
                            late_callback(message)
                        except Exception:
                            pass
                    continue
                if "id" in message and message.get("method"):
                    if self.on_server_request:
                        self.on_server_request(message)
                    continue
                if self.on_notification:
                    self.on_notification(str(message.get("method") or ""), message.get("params") or {})
        finally:
            callback = None
            exit_generation = 0
            with self._start_lock:
                callback, exit_generation = self._finalize_generation_exit_locked(generation)
            try:
                self._notify_exit(callback, exit_generation)
            finally:
                reader_drained.set()

    def _record_inbound(self, message: dict[str, Any], generation: int) -> None:
        """Keep bounded, content-free protocol evidence for live diagnostics."""
        method = str(message.get("method") or "")
        if method:
            kind = "server_request" if "id" in message else "notification"
            label = method
        else:
            kind = "response"
            label = "error" if message.get("error") else "result"
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        entry = {
            "at": int(time.time() * 1000),
            "generation": generation,
            "kind": kind,
            "method": method,
            "label": label,
            "threadId": str(params.get("threadId") or ""),
            "turnId": str(params.get("turnId") or ""),
        }
        with self._diagnostic_lock:
            key = f"{kind}:{label}"
            self._inbound_counts[key] = self._inbound_counts.get(key, 0) + 1
            self._recent_inbound.append(entry)
            if len(self._recent_inbound) > MAX_PROTOCOL_DIAGNOSTICS:
                self._recent_inbound = self._recent_inbound[-MAX_PROTOCOL_DIAGNOSTICS:]

    def diagnostics(self) -> dict[str, Any]:
        with self._diagnostic_lock:
            counts = dict(self._inbound_counts)
            recent = [dict(item) for item in self._recent_inbound]
        proc = self._proc
        return {
            "running": bool(proc and proc.poll() is None),
            "pid": int(proc.pid) if proc and getattr(proc, "pid", None) else 0,
            "generation": self._generation,
            "inboundCounts": counts,
            "recentInbound": recent,
        }

    def _read_stderr_loop(self, stderr: Any, generation: int) -> None:
        if not stderr:
            return
        for line in stderr:
            if generation != self._generation:
                return
            text = str(line).rstrip("\n")
            if not text:
                continue
            with self._stderr_lock:
                self._stderr_lines.append(text)
                if len(self._stderr_lines) > 200:
                    self._stderr_lines = self._stderr_lines[-200:]

    def stderr_text(self, limit: int = 4000) -> str:
        with self._stderr_lock:
            text = "\n".join(self._stderr_lines[-80:])
        return text[-limit:]

    def _fail_pending(self, message: str) -> None:
        with self._pending_lock:
            pending = list(self._pending.items())
            self._pending.clear()
            self._late_response_callbacks.clear()
        for request_id, target in pending:
            try:
                target.put_nowait({"id": request_id, "error": {"message": message}, "_transportError": True})
            except Exception:
                pass
