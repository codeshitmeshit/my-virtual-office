"""Generic JSONL app-server runtime for provider protocol adapters."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from typing import Any, Callable


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
        self._write_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._stderr_lock = threading.Lock()
        self.on_server_request: Callable[[dict[str, Any]], None] | None = None
        self.on_notification: Callable[[str, dict[str, Any]], None] | None = None
        self.on_exit: Callable[[], None] | None = None

    @property
    def process(self) -> Any:
        return self._proc

    def is_running(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    def start(self) -> None:
        if self.is_running():
            return
        with self._start_lock:
            if self.is_running():
                return
            self._proc = self.popen_factory(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                text=True,
                bufsize=1,
                cwd=self.cwd,
                env=self.env,
            )
            self._reader = threading.Thread(target=self._read_loop, name=self.name, daemon=True)
            self._reader.start()
            if getattr(self._proc, "stderr", None):
                self._stderr_reader = threading.Thread(target=self._read_stderr_loop, name=f"{self.name}-stderr", daemon=True)
                self._stderr_reader.start()

    def close(self) -> None:
        proc = self._proc
        self._proc = None
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

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30) -> dict[str, Any]:
        self.start()
        request_id = self.allocate_id()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = response_queue
        try:
            self.send({"id": request_id, "method": method, "params": params or {}})
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError(f"App-server request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if response.get("error"):
            error = response["error"]
            raise RuntimeError(error.get("message") if isinstance(error, dict) else str(error))
        return response

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
                if "id" in message and ("result" in message or "error" in message) and not message.get("method"):
                    with self._pending_lock:
                        target = self._pending.get(message["id"])
                    if target:
                        target.put(message)
                    continue
                if "id" in message and message.get("method"):
                    if self.on_server_request:
                        self.on_server_request(message)
                    continue
                if self.on_notification:
                    self.on_notification(str(message.get("method") or ""), message.get("params") or {})
        finally:
            reason = self.stderr_text()
            self._fail_pending(f"App-server stopped{': ' + reason if reason else ''}")
            if self.on_exit:
                self.on_exit()

    def _read_stderr_loop(self) -> None:
        proc = self._proc
        stderr = getattr(proc, "stderr", None)
        if not stderr:
            return
        for line in stderr:
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
        for request_id, target in pending:
            try:
                target.put_nowait({"id": request_id, "error": {"message": message}})
            except Exception:
                pass
